"""Tables for everything the API persists across a request boundary: experiments, their
results, plans, and the audit log. Every one of them is observed from an independently
opened connection in the tests, because a test that shares the application's session
cannot see a missing commit (Day 5 of this series found exactly that bug)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import Field, Session, SQLModel, create_engine, select


def now() -> datetime:
    return datetime.now(UTC)


class Experiment(SQLModel, table=True):
    __tablename__ = "experiments"
    id: int | None = Field(default=None, primary_key=True)
    experiment_id: str = Field(index=True, unique=True)
    name: str
    kind: str
    plan_hash: str = Field(index=True)
    design: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    registered_at: datetime = Field(default_factory=now)


class ExperimentResult(SQLModel, table=True):
    __tablename__ = "experiment_results"
    id: int | None = Field(default=None, primary_key=True)
    experiment_id: str = Field(foreign_key="experiments.experiment_id", index=True)
    plan_hash: str
    method: str
    channel: str
    incremental_revenue: float
    standard_error: float
    lower: float
    upper: float
    level: float
    geos: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    start_week: int
    end_week: int
    truth: float | None = None
    posted_at: datetime = Field(default_factory=now)


class PlanRow(SQLModel, table=True):
    __tablename__ = "plans"
    id: int | None = Field(default=None, primary_key=True)
    plan_id: str = Field(index=True, unique=True)
    model_version: str
    backend: str
    spec_hash: str
    inputs_hash: str
    total_budget: float
    allocation: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    expected_profit: float
    profit_lower: float
    profit_upper: float
    level: float
    constraints: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    degenerate: bool = False
    note: str = ""
    created_at: datetime = Field(default_factory=now)


class AuditEntry(SQLModel, table=True):
    __tablename__ = "audit_log"
    id: int | None = Field(default=None, primary_key=True)
    at: datetime = Field(default_factory=now, index=True)
    actor: str
    action: str
    resource: str
    resource_id: str = ""
    detail: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


def make_async_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True)


def make_engine(url: str) -> Any:
    return create_engine(url, pool_pre_ping=True)


def create_all(engine: Any) -> None:
    SQLModel.metadata.create_all(engine)


def reset(engine: Any) -> None:
    """Clear every table the demo writes to. Used by reset and rederive before publish."""
    with Session(engine) as session:
        for table in (ExperimentResult, PlanRow, AuditEntry, Experiment):
            for row in session.exec(select(table)).all():
                session.delete(row)
        session.commit()
