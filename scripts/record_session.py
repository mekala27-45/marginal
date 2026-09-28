"""Record an API session for the site's fallback bundle.

Starts the API in a child process against a local Postgres (or drives a running server with
--base-url), walks the flow the site performs (health, models, the registered geo lift test and
its result, the optimizer at the current budget and at four other budgets, a saved plan, the
plan list, the audit log) and writes every response, labelled recorded, to
web/public/data/recorded_session.json. When the live API is asleep the site serves these
responses and says so on the page.

    MARGINAL_TEST_DATABASE_URL=postgresql+psycopg://... python scripts/record_session.py --start-server
    python scripts/record_session.py --base-url https://marginal-alderquist-api.fly.dev
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "public" / "data" / "recorded_session.json"
BUDGET_STEPS = (0.8, 0.9, 1.0, 1.1, 1.2)


def wait_for(base: str, seconds: float = 90.0) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            if httpx.get(f"{base}/v1/health", timeout=5.0).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1.0)
    raise SystemExit(f"the API at {base} did not answer within {seconds:.0f} seconds")


def record(base: str, token: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    session: dict[str, Any] = {
        "recorded": True,
        "recorded_at": datetime.now(UTC).isoformat(),
        "base_url": base,
        "responses": {},
    }
    responses = session["responses"]

    def get(name: str, path: str) -> dict[str, Any]:
        r = httpx.get(f"{base}{path}", timeout=60.0)
        r.raise_for_status()
        body: dict[str, Any] = r.json()
        responses[name] = {"method": "GET", "path": path, "status": r.status_code, "body": body}
        return body

    def post(name: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        r = httpx.post(f"{base}{path}", json=payload, headers=headers, timeout=120.0)
        r.raise_for_status()
        body: dict[str, Any] = r.json()
        responses[name] = {
            "method": "POST",
            "path": path,
            "status": r.status_code,
            "request": payload,
            "body": body,
        }
        return body

    get("health", "/v1/health")
    get("models", "/v1/models")

    # The geo lift test as the pipeline registered it, with the same plan hash and design.
    design = json.loads((ROOT / "results" / "experiments" / "geo_design.json").read_text(encoding="utf-8"))
    result = json.loads((ROOT / "results" / "experiments" / "geo_result.json").read_text(encoding="utf-8"))
    registration = design["registration"]
    registered = post(
        "register_experiment",
        "/v1/experiments",
        {
            "name": registration["name"],
            "kind": registration["kind"],
            "plan_hash": registration["plan_hash"],
            "design": design["design"],
        },
    )
    experiment_id = str(registered["experiment_id"])
    did = result["did"]
    post(
        "post_result",
        f"/v1/experiments/{experiment_id}/result",
        {
            "plan_hash": registration["plan_hash"],
            "method": "did",
            "channel": design["design"]["channel"],
            "incremental_revenue": did["incremental_revenue"],
            "standard_error": did["standard_error"],
            "lower": did["lower"],
            "upper": did["upper"],
            "level": did["level"],
            "geos": design["design"]["treated_geos"],
            "start_week": design["design"]["start_week"],
            "end_week": design["design"]["end_week"],
            "truth": result["truth"],
        },
    )
    get("experiment", f"/v1/experiments/{experiment_id}")
    get("experiments", "/v1/experiments")

    # The optimizer at the current budget and around it, as the slider asks for it.
    model = json.loads((ROOT / "results" / "mmm" / "own_model.json").read_text(encoding="utf-8"))
    total = float(sum(c["weekly_spend_current"] for c in model["channels"]))
    session["budget_current"] = total
    for step in BUDGET_STEPS:
        post(f"optimize_{int(step * 100)}", "/v1/optimize", {"total_budget": round(total * step, 2)})
    saved = post(
        "save_plan",
        "/v1/plans",
        {"total_budget": round(total, 2), "note": "recorded session for the site's fallback bundle"},
    )
    get("plan", f"/v1/plans/{saved['plan_id']}")
    get("plans", "/v1/plans?limit=20")
    get("audit", "/v1/audit?limit=20")
    return session


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--start-server", action="store_true")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()
    token = os.environ.get("MARGINAL_WRITE_TOKEN", "record-token")
    server: subprocess.Popen[bytes] | None = None
    base = args.base_url
    try:
        if args.start_server:
            url = os.environ.get("MARGINAL_TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
            if not url:
                raise SystemExit("set MARGINAL_TEST_DATABASE_URL or DATABASE_URL to start a server")
            env = {**os.environ, "DATABASE_URL": url, "MARGINAL_WRITE_TOKEN": token, "MARGINAL_ENV": "record"}
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "alembic",
                    "-c",
                    str(ROOT / "packages" / "api" / "alembic.ini"),
                    "upgrade",
                    "head",
                ],
                cwd=ROOT / "packages" / "api",
                env=env,
                check=True,
            )
            server = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "marginal_api.main:app",
                    "--port",
                    str(args.port),
                    "--log-level",
                    "warning",
                ],
                cwd=ROOT,
                env=env,
            )
            base = f"http://127.0.0.1:{args.port}"
        if not base:
            raise SystemExit("give --base-url or --start-server")
        wait_for(base)
        session = record(base, token)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(session, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"recorded {len(session['responses'])} responses to {out.relative_to(ROOT)}")
        return 0
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=20)


if __name__ == "__main__":
    sys.exit(main())
