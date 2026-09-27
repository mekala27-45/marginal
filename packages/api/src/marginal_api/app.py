"""The marginal API: the plan and experiment registry, the live optimizer, the model list and
the audit log.

Every write goes: the row, then its audit row, then commit, then the response, so a response
can never exist without its audit record. Writes need the token; this is a demonstration and
the README says so. Every response body carries the statement.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from marginal_budget import Constraints, Plan, optimize
from marginal_core.config import CHANNELS
from marginal_core.statements import STATEMENT
from marginal_mmm import ModelExport
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException

from marginal_api.db import AuditEntry, Experiment, ExperimentResult, PlanRow, make_async_engine
from marginal_api.settings import Settings, load_settings


def envelope(data: dict[str, Any]) -> dict[str, Any]:
    return {**data, "statement": STATEMENT, "served_at": datetime.now(UTC).isoformat()}


class ExperimentIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(pattern="^(geo_lift|email)$")
    plan_hash: str = Field(min_length=16, max_length=16)
    design: dict[str, Any]


class ResultIn(BaseModel):
    plan_hash: str = Field(min_length=16, max_length=16)
    method: str = Field(min_length=1, max_length=60)
    channel: str
    incremental_revenue: float
    standard_error: float = Field(ge=0)
    lower: float
    upper: float
    level: float = Field(gt=0, lt=1)
    geos: list[int] = Field(default_factory=list)
    start_week: int
    end_week: int
    truth: float | None = None
    experiment_id: str | None = None
    posted_at: str | None = None


class OptimizeIn(BaseModel):
    total_budget: float = Field(gt=0)
    floor_share: float | None = Field(default=None, ge=0, le=1)
    ceiling_share: float | None = Field(default=None, ge=1)
    max_change_share: float | None = Field(default=None, ge=0, le=1)
    floors: dict[str, float] | None = None
    ceilings: dict[str, float] | None = None
    apply_allowance: bool = True
    note: str = Field(default="", max_length=400)


class AppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine: AsyncEngine = make_async_engine(settings.database_url)
        self.model: ModelExport | None = None
        self.allowance: dict[str, float] | None = None
        self.revenue_per_acquisition: float | None = None
        self.load_model()

    def load_model(self) -> None:
        for path in self.settings.model_paths:
            if path.exists():
                self.model = ModelExport.model_validate(json.loads(path.read_text(encoding="utf-8")))
                break
        allowance_path = self.settings.results / "clv" / "allowance.json"
        if allowance_path.exists():
            payload = json.loads(allowance_path.read_text(encoding="utf-8"))
            self.allowance = {str(k): float(v) for k, v in payload["allowance_by_channel"].items()}
            self.revenue_per_acquisition = float(payload["revenue_per_acquisition"])


def state_of(request: Request) -> AppState:
    state: AppState = request.app.state.marginal
    return state


async def session_of(request: Request) -> AsyncIterator[AsyncSession]:
    async with AsyncSession(state_of(request).engine, expire_on_commit=False) as session:
        yield session


def actor_of(request: Request, authorization: Annotated[str | None, Header()] = None) -> str:
    settings = state_of(request).settings
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        if settings.token_required and token == settings.write_token:
            return "token"
    return "anonymous"


SessionDep = Annotated[AsyncSession, Depends(session_of)]
ActorDep = Annotated[str, Depends(actor_of)]


def require_writer(actor: str) -> None:
    if actor != "token":
        raise HTTPException(status_code=401, detail="writes need the token")


async def audit(
    session: AsyncSession,
    actor: str,
    action: str,
    resource: str,
    resource_id: str = "",
    detail: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEntry(
            actor=actor, action=action, resource=resource, resource_id=resource_id, detail=detail or {}
        )
    )
    await session.commit()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.marginal = AppState(settings)
        yield
        await app.state.marginal.engine.dispose()

    app = FastAPI(title="marginal", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins) or ["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=envelope({"error": str(exc.detail)}))

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422, content=envelope({"error": "invalid request", "detail": exc.errors()})
        )

    @app.get("/v1/health")
    async def health(request: Request, session: SessionDep) -> dict[str, Any]:
        state = state_of(request)
        database = "ok"
        try:
            await session.exec(select(Experiment.id).limit(1))
        except Exception:
            database = "unreachable"
        return envelope(
            {
                "status": "ok",
                "environment": state.settings.environment,
                "database": database,
                "model_version": state.model.version if state.model else None,
                "writes": "token gated",
            }
        )

    @app.get("/v1/models")
    async def models(request: Request) -> dict[str, Any]:
        state = state_of(request)
        found: list[dict[str, Any]] = []
        for folder, pattern in (("mmm", "*_model.json"), ("calibrate", "*_model.json")):
            for path in sorted((state.settings.results / folder).glob(pattern)):
                payload = json.loads(path.read_text(encoding="utf-8"))
                found.append(
                    {
                        "version": payload["version"],
                        "backend": payload["backend"],
                        "spec_hash": payload["spec_hash"],
                        "calibrated": payload["calibrated"],
                        "data_source": payload["data_source"],
                        "file": f"results/{folder}/{path.name}",
                    }
                )
        return envelope({"models": found, "serving": state.model.version if state.model else None})

    @app.post("/v1/experiments", status_code=201)
    async def register(body: ExperimentIn, session: SessionDep, actor: ActorDep) -> dict[str, Any]:
        require_writer(actor)
        existing = (
            await session.exec(select(Experiment).where(Experiment.plan_hash == body.plan_hash))
        ).first()
        if existing is not None:
            return envelope(
                {
                    "experiment_id": existing.experiment_id,
                    "plan_hash": existing.plan_hash,
                    "registered_at": existing.registered_at.isoformat(),
                    "already_registered": True,
                }
            )
        row = Experiment(
            experiment_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"marginal:{body.kind}:{body.plan_hash}")),
            name=body.name,
            kind=body.kind,
            plan_hash=body.plan_hash,
            design=body.design,
        )
        session.add(row)
        await session.flush()
        await audit(
            session, actor, "register", "experiment", row.experiment_id, {"plan_hash": body.plan_hash}
        )
        return envelope(
            {
                "experiment_id": row.experiment_id,
                "plan_hash": row.plan_hash,
                "registered_at": row.registered_at.isoformat(),
                "already_registered": False,
            }
        )

    @app.post("/v1/experiments/{experiment_id}/result", status_code=201)
    async def post_result(
        experiment_id: str, body: ResultIn, session: SessionDep, actor: ActorDep
    ) -> dict[str, Any]:
        require_writer(actor)
        experiment = (
            await session.exec(select(Experiment).where(Experiment.experiment_id == experiment_id))
        ).first()
        if experiment is None:
            raise HTTPException(status_code=404, detail="no experiment with that id; register the plan first")
        if not experiment.plan_hash:
            raise HTTPException(
                status_code=409, detail="the experiment has no plan hash; a result cannot be posted"
            )
        if body.plan_hash != experiment.plan_hash:
            raise HTTPException(status_code=409, detail="the plan hash does not match the registered design")
        if body.channel not in CHANNELS:
            raise HTTPException(status_code=422, detail="unknown channel")
        row = ExperimentResult(
            experiment_id=experiment_id,
            plan_hash=body.plan_hash,
            method=body.method,
            channel=body.channel,
            incremental_revenue=body.incremental_revenue,
            standard_error=body.standard_error,
            lower=body.lower,
            upper=body.upper,
            level=body.level,
            geos=body.geos,
            start_week=body.start_week,
            end_week=body.end_week,
            truth=body.truth,
        )
        session.add(row)
        await session.flush()
        await audit(session, actor, "post_result", "experiment", experiment_id, {"method": body.method})
        return envelope(
            {"experiment_id": experiment_id, "result_id": row.id, "posted_at": row.posted_at.isoformat()}
        )

    @app.get("/v1/experiments")
    async def list_experiments(session: SessionDep) -> dict[str, Any]:
        experiments = (await session.exec(select(Experiment).order_by(Experiment.registered_at))).all()  # type: ignore[arg-type]
        results = (await session.exec(select(ExperimentResult))).all()
        by_id: dict[str, list[dict[str, Any]]] = {}
        for r in results:
            by_id.setdefault(r.experiment_id, []).append(_result_payload(r))
        return envelope(
            {"experiments": [_experiment_payload(e, by_id.get(e.experiment_id, [])) for e in experiments]}
        )

    @app.get("/v1/experiments/{experiment_id}")
    async def get_experiment(experiment_id: str, session: SessionDep) -> dict[str, Any]:
        experiment = (
            await session.exec(select(Experiment).where(Experiment.experiment_id == experiment_id))
        ).first()
        if experiment is None:
            raise HTTPException(status_code=404, detail="no experiment with that id")
        results = (
            await session.exec(
                select(ExperimentResult).where(ExperimentResult.experiment_id == experiment_id)
            )
        ).all()
        return envelope(_experiment_payload(experiment, [_result_payload(r) for r in results]))

    @app.post("/v1/optimize")
    async def optimize_budget(body: OptimizeIn, request: Request) -> dict[str, Any]:
        state = state_of(request)
        plan = _run_optimizer(state, body)
        return envelope({"plan": _plan_payload(plan), "stored": False})

    @app.post("/v1/plans", status_code=201)
    async def save_plan(
        body: OptimizeIn, request: Request, session: SessionDep, actor: ActorDep
    ) -> dict[str, Any]:
        require_writer(actor)
        state = state_of(request)
        plan = _run_optimizer(state, body)
        row = PlanRow(
            plan_id=str(uuid.uuid4()),
            model_version=plan.model_version,
            backend=plan.backend,
            spec_hash=plan.spec_hash,
            inputs_hash=plan.inputs_hash,
            total_budget=plan.constraints.total_budget,
            allocation=plan.spend,
            expected_profit=plan.expected_profit,
            profit_lower=plan.profit_lower,
            profit_upper=plan.profit_upper,
            level=plan.level,
            constraints=plan.constraints.model_dump(mode="json"),
            degenerate=plan.degenerate,
            note=body.note,
        )
        session.add(row)
        await session.flush()
        await audit(session, actor, "save", "plan", row.plan_id, {"inputs_hash": plan.inputs_hash})
        return envelope(
            {"plan_id": row.plan_id, "created_at": row.created_at.isoformat(), "plan": _plan_payload(plan)}
        )

    @app.get("/v1/plans")
    async def list_plans(session: SessionDep, limit: int = 50) -> dict[str, Any]:
        rows = (
            await session.exec(select(PlanRow).order_by(col(PlanRow.created_at).desc()).limit(limit))
        ).all()
        return envelope({"plans": [_plan_row_payload(r) for r in rows]})

    @app.get("/v1/plans/{plan_id}")
    async def get_plan(plan_id: str, session: SessionDep) -> dict[str, Any]:
        row = (await session.exec(select(PlanRow).where(PlanRow.plan_id == plan_id))).first()
        if row is None:
            raise HTTPException(status_code=404, detail="no plan with that id")
        return envelope(_plan_row_payload(row))

    @app.get("/v1/audit")
    async def audit_log(session: SessionDep, limit: int = 100) -> dict[str, Any]:
        rows = (
            await session.exec(select(AuditEntry).order_by(col(AuditEntry.at).desc()).limit(min(limit, 500)))
        ).all()
        return envelope(
            {
                "entries": [
                    {
                        "at": r.at.isoformat(),
                        "actor": r.actor,
                        "action": r.action,
                        "resource": r.resource,
                        "resource_id": r.resource_id,
                        "detail": r.detail,
                    }
                    for r in rows
                ]
            }
        )

    @app.get("/v1/ping-db")
    async def ping(session: SessionDep) -> dict[str, Any]:
        value = (await session.exec(text("select 1"))).scalar()  # type: ignore[call-overload]
        return envelope({"database": int(value)})

    return app


def _run_optimizer(state: AppState, body: OptimizeIn) -> Plan:
    if state.model is None:
        raise HTTPException(status_code=503, detail="no fitted model on this server")
    kwargs: dict[str, Any] = {"total_budget": body.total_budget}
    for field in ("floor_share", "ceiling_share", "max_change_share", "floors", "ceilings"):
        value = getattr(body, field)
        if value is not None:
            kwargs[field] = value
    if body.apply_allowance and state.allowance and state.revenue_per_acquisition:
        kwargs["allowance"] = state.allowance
        kwargs["revenue_per_acquisition"] = state.revenue_per_acquisition
    try:
        constraints = Constraints(**kwargs)
        return optimize(state.model, constraints)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _plan_payload(plan: Plan) -> dict[str, Any]:
    return {**plan.model_dump(mode="json"), "spend": plan.spend}


def _plan_row_payload(row: PlanRow) -> dict[str, Any]:
    return {
        "plan_id": row.plan_id,
        "model_version": row.model_version,
        "backend": row.backend,
        "spec_hash": row.spec_hash,
        "inputs_hash": row.inputs_hash,
        "total_budget": row.total_budget,
        "allocation": row.allocation,
        "expected_profit": row.expected_profit,
        "profit_lower": row.profit_lower,
        "profit_upper": row.profit_upper,
        "level": row.level,
        "constraints": row.constraints,
        "degenerate": row.degenerate,
        "note": row.note,
        "created_at": row.created_at.isoformat(),
    }


def _experiment_payload(e: Experiment, results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "experiment_id": e.experiment_id,
        "name": e.name,
        "kind": e.kind,
        "plan_hash": e.plan_hash,
        "design": e.design,
        "registered_at": e.registered_at.isoformat(),
        "results": results,
    }


def _result_payload(r: ExperimentResult) -> dict[str, Any]:
    return {
        "result_id": r.id,
        "method": r.method,
        "channel": r.channel,
        "incremental_revenue": r.incremental_revenue,
        "standard_error": r.standard_error,
        "lower": r.lower,
        "upper": r.upper,
        "level": r.level,
        "geos": r.geos,
        "start_week": r.start_week,
        "end_week": r.end_week,
        "truth": r.truth,
        "posted_at": r.posted_at.isoformat(),
    }
