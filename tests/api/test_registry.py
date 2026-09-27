"""The registry observed independently: rows from a second connection, the audit row before the
response, the plan hash rules, and the statement on every endpoint."""

from __future__ import annotations

from datetime import datetime

import psycopg
import pytest
from fastapi.testclient import TestClient
from marginal_core.statements import STATEMENT

from tests.api.conftest import plain_url

pytestmark = pytest.mark.postgres

DESIGN = {
    "name": "display holdout",
    "kind": "geo_lift",
    "plan_hash": "0123456789abcdef",
    "design": {"geos": [1, 2]},
}
RESULT = {
    "plan_hash": "0123456789abcdef",
    "method": "did",
    "channel": "display_retargeting",
    "incremental_revenue": 150000.0,
    "standard_error": 10000.0,
    "lower": 133000.0,
    "upper": 167000.0,
    "level": 0.9,
    "geos": [1, 2],
    "start_week": 148,
    "end_week": 155,
}


def _rows(url: str, sql: str) -> list[tuple[object, ...]]:
    with psycopg.connect(plain_url(url)) as conn, conn.cursor() as cur:
        cur.execute(sql)
        return list(cur.fetchall())


def test_plan_is_committed(client: TestClient, auth: dict[str, str], clean_db: str) -> None:
    response = client.post("/v1/plans", json={"total_budget": 500_000.0, "note": "test"}, headers=auth)
    assert response.status_code == 201, response.text
    plan_id = response.json()["plan_id"]
    rows = _rows(
        clean_db, f"select plan_id, model_version, expected_profit from plans where plan_id = '{plan_id}'"
    )
    assert len(rows) == 1 and rows[0][1].startswith("own")


def test_experiment_result_is_committed(client: TestClient, auth: dict[str, str], clean_db: str) -> None:
    registered = client.post("/v1/experiments", json=DESIGN, headers=auth)
    assert registered.status_code == 201, registered.text
    experiment_id = registered.json()["experiment_id"]
    posted = client.post(f"/v1/experiments/{experiment_id}/result", json=RESULT, headers=auth)
    assert posted.status_code == 201, posted.text
    rows = _rows(
        clean_db,
        f"select method, incremental_revenue from experiment_results where experiment_id = '{experiment_id}'",
    )
    assert rows == [("did", 150000.0)]
    listed = client.get("/v1/experiments").json()
    assert listed["experiments"][0]["results"][0]["method"] == "did"


def test_audit_precedes_response(client: TestClient, auth: dict[str, str], clean_db: str) -> None:
    response = client.post("/v1/experiments", json=DESIGN, headers=auth)
    served_at = datetime.fromisoformat(response.json()["served_at"])
    rows = _rows(clean_db, "select at, action, resource_id from audit_log order by at")
    assert len(rows) == 1
    at, action, resource_id = rows[0]
    assert action == "register" and resource_id == response.json()["experiment_id"]
    assert at <= served_at  # type: ignore[operator]


def test_a_result_needs_a_registered_plan_hash(client: TestClient, auth: dict[str, str]) -> None:
    missing = client.post("/v1/experiments/does-not-exist/result", json=RESULT, headers=auth)
    assert missing.status_code == 404
    registered = client.post("/v1/experiments", json=DESIGN, headers=auth).json()
    wrong = client.post(
        f"/v1/experiments/{registered['experiment_id']}/result",
        json={**RESULT, "plan_hash": "ffffffffffffffff"},
        headers=auth,
    )
    assert wrong.status_code == 409
    assert "does not match" in wrong.json()["error"]


def test_registering_the_same_design_twice_returns_the_same_id(
    client: TestClient, auth: dict[str, str]
) -> None:
    first = client.post("/v1/experiments", json=DESIGN, headers=auth).json()
    second = client.post("/v1/experiments", json=DESIGN, headers=auth).json()
    assert first["experiment_id"] == second["experiment_id"]
    assert second["already_registered"] is True


def test_writes_need_the_token(client: TestClient) -> None:
    assert client.post("/v1/experiments", json=DESIGN).status_code == 401
    assert client.post("/v1/plans", json={"total_budget": 500_000.0}).status_code == 401
    assert (
        client.post("/v1/experiments", json=DESIGN, headers={"Authorization": "Bearer wrong"}).status_code
        == 401
    )


def test_optimize_answers_without_storing(client: TestClient, clean_db: str) -> None:
    response = client.post("/v1/optimize", json={"total_budget": 500_000.0})
    assert response.status_code == 200, response.text
    plan = response.json()["plan"]
    assert abs(sum(plan["spend"].values()) - 500_000.0) < 1.0
    assert plan["starts"] == 8
    assert _rows(clean_db, "select count(*) from plans")[0][0] == 0


def test_an_impossible_budget_is_refused(client: TestClient) -> None:
    response = client.post("/v1/optimize", json={"total_budget": 5.0})
    assert response.status_code == 422
    assert "cannot satisfy" in response.json()["error"]


def test_statement_on_every_endpoint(client: TestClient, auth: dict[str, str]) -> None:
    """Walks the route table rather than a hand kept list."""
    registered = client.post("/v1/experiments", json=DESIGN, headers=auth).json()
    saved = client.post("/v1/plans", json={"total_budget": 500_000.0}, headers=auth).json()
    params = {"experiment_id": registered["experiment_id"], "plan_id": saved["plan_id"]}
    seen = 0
    for route in client.app.routes:  # type: ignore[attr-defined]
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set())
        if not path.startswith("/v1/"):
            continue
        for name, value in params.items():
            path = path.replace("{" + name + "}", value)
        for method in methods:
            if method == "GET":
                response = client.get(path)
            elif method == "POST" and "optimize" in path:
                response = client.post(path, json={"total_budget": 500_000.0})
            elif method == "POST" and path.endswith("/plans"):
                response = client.post(path, json={"total_budget": 500_000.0}, headers=auth)
            elif method == "POST" and path.endswith("/result"):
                response = client.post(path, json=RESULT, headers=auth)
            elif method == "POST":
                response = client.post(path, json=DESIGN, headers=auth)
            else:
                continue
            assert response.json()["statement"] == STATEMENT, path
            seen += 1
    assert seen >= 10
    error = client.get("/v1/plans/nope")
    assert error.status_code == 404 and error.json()["statement"] == STATEMENT


def test_health_and_models(client: TestClient) -> None:
    health = client.get("/v1/health").json()
    assert health["status"] == "ok" and health["database"] == "ok"
    models = client.get("/v1/models").json()
    assert any(m["backend"] == "own" for m in models["models"])
