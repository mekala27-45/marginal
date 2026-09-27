"""The out of process check: register an experiment, post a result, save a plan, and read all
three back through a connection this process opens itself.

Two modes. `--start-server` starts the API in a child process against DATABASE_URL (CI, or a
local Postgres), drives it over HTTP, then reads the rows with a fresh psycopg connection in
this process. `--base-url` drives a live server (the Fly deployment) and reads back through
the API's own GET endpoints from this separate client, which is the verification the README
prints. The audit row must be observed before the response's served_at in both modes.

    python scripts/check_persistence.py --start-server
    python scripts/check_persistence.py --base-url https://marginal-alderquist-api.fly.dev
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))

from marginal_core.statements import STATEMENT


def wait_for(base: str, seconds: float = 60.0) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            if httpx.get(f"{base}/v1/health", timeout=5.0).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1.0)
    raise SystemExit(f"the API at {base} did not answer within {seconds:.0f} seconds")


def drive(base: str, token: str) -> dict[str, object]:
    headers = {"Authorization": f"Bearer {token}"}
    plan_hash = uuid.uuid4().hex[:16]
    registered = httpx.post(
        f"{base}/v1/experiments",
        json={
            "name": "persistence check",
            "kind": "geo_lift",
            "plan_hash": plan_hash,
            "design": {"check": True},
        },
        headers=headers,
        timeout=30.0,
    )
    registered.raise_for_status()
    body = registered.json()
    experiment_id = str(body["experiment_id"])
    served_at = datetime.fromisoformat(str(body["served_at"]))
    posted = httpx.post(
        f"{base}/v1/experiments/{experiment_id}/result",
        json={
            "plan_hash": plan_hash,
            "method": "did",
            "channel": "display_retargeting",
            "incremental_revenue": 123456.0,
            "standard_error": 1000.0,
            "lower": 121800.0,
            "upper": 125100.0,
            "level": 0.9,
            "geos": [1, 2, 3],
            "start_week": 148,
            "end_week": 155,
        },
        headers=headers,
        timeout=30.0,
    )
    posted.raise_for_status()
    saved = httpx.post(
        f"{base}/v1/plans",
        json={"total_budget": 500000.0, "note": "persistence check"},
        headers=headers,
        timeout=60.0,
    )
    saved.raise_for_status()
    plan_id = str(saved.json()["plan_id"])
    return {
        "experiment_id": experiment_id,
        "plan_hash": plan_hash,
        "plan_id": plan_id,
        "served_at": served_at,
    }


def read_back_via_api(base: str, ids: dict[str, object]) -> dict[str, object]:
    experiment = httpx.get(f"{base}/v1/experiments/{ids['experiment_id']}", timeout=30.0)
    experiment.raise_for_status()
    plan = httpx.get(f"{base}/v1/plans/{ids['plan_id']}", timeout=30.0)
    plan.raise_for_status()
    audit = httpx.get(f"{base}/v1/audit?limit=20", timeout=30.0)
    audit.raise_for_status()
    e = experiment.json()
    if (
        e["plan_hash"] != ids["plan_hash"]
        or not e["results"]
        or e["results"][0]["incremental_revenue"] != 123456.0
    ):
        raise SystemExit("the experiment or its result did not come back as posted")
    if e["statement"] != STATEMENT or plan.json()["statement"] != STATEMENT:
        raise SystemExit("a response is missing the statement")
    entries = audit.json()["entries"]
    registration = [
        x for x in entries if x["action"] == "register" and x["resource_id"] == ids["experiment_id"]
    ]
    if not registration:
        raise SystemExit("no audit row for the registration")
    at = datetime.fromisoformat(registration[0]["at"])
    if at > ids["served_at"]:  # type: ignore[operator]
        raise SystemExit("the audit row was written after the response was served")
    return {
        "experiment": {"plan_hash": e["plan_hash"], "results": len(e["results"])},
        "plan": {"plan_id": plan.json()["plan_id"], "expected_profit": plan.json()["expected_profit"]},
        "audit_entries": len(entries),
        "audit_before_response": True,
    }


def read_back_via_postgres(url: str, ids: dict[str, object]) -> dict[str, object]:
    import psycopg

    plain = url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(plain) as conn, conn.cursor() as cur:
        cur.execute("select plan_hash from experiments where experiment_id = %s", (ids["experiment_id"],))
        experiment = cur.fetchone()
        cur.execute(
            "select incremental_revenue from experiment_results where experiment_id = %s",
            (ids["experiment_id"],),
        )
        result = cur.fetchone()
        cur.execute("select expected_profit from plans where plan_id = %s", (ids["plan_id"],))
        plan = cur.fetchone()
        cur.execute(
            "select at from audit_log where action = 'register' and resource_id = %s", (ids["experiment_id"],)
        )
        audit = cur.fetchone()
    if experiment is None or experiment[0] != ids["plan_hash"]:
        raise SystemExit("the experiment row is missing from a fresh connection")
    if result is None or result[0] != 123456.0:
        raise SystemExit("the result row is missing from a fresh connection")
    if plan is None:
        raise SystemExit("the plan row is missing from a fresh connection")
    if audit is None or audit[0] > ids["served_at"]:
        raise SystemExit("the audit row is missing or later than the response")
    return {"experiment": True, "result": True, "plan": float(plan[0]), "audit_before_response": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--start-server", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    token = os.environ.get("MARGINAL_WRITE_TOKEN", "check-token")
    server: subprocess.Popen[bytes] | None = None
    base = args.base_url
    try:
        if args.start_server:
            url = os.environ.get("MARGINAL_TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
            if not url:
                raise SystemExit("set MARGINAL_TEST_DATABASE_URL or DATABASE_URL to start a server")
            env = {**os.environ, "DATABASE_URL": url, "MARGINAL_WRITE_TOKEN": token, "MARGINAL_ENV": "check"}
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
        ids = drive(base, token)
        if args.start_server:
            url = os.environ.get("MARGINAL_TEST_DATABASE_URL") or os.environ["DATABASE_URL"]
            observed = read_back_via_postgres(url, ids)
        else:
            observed = read_back_via_api(base, ids)
        print(
            json.dumps(
                {"base_url": base, "ids": {k: str(v) for k, v in ids.items()}, "observed": observed}, indent=1
            )
        )
        print(
            "persistence check: an experiment, its result and a plan were read back from outside the server process"
        )
        return 0
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=20)


if __name__ == "__main__":
    sys.exit(main())
