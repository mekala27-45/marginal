"""API fixtures: a real Postgres and a client with the write token.

Every test that checks persistence reads back through a connection opened for the
purpose, never through the application's session.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from marginal_api.app import create_app
from marginal_api.db import SQLModel, make_engine
from marginal_api.settings import Settings

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "test-token-not-a-secret"
DEFAULT_URL = "postgresql+psycopg://postgres@127.0.0.1:5433/marginal_test"


def _url() -> str:
    return os.environ.get("MARGINAL_TEST_DATABASE_URL", DEFAULT_URL)


def plain_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture(scope="session")
def database_url() -> str:
    url = _url()
    try:
        with psycopg.connect(plain_url(url), connect_timeout=3):
            pass
    except psycopg.OperationalError:
        if os.environ.get("MARGINAL_REQUIRE_POSTGRES"):
            pytest.fail(f"MARGINAL_REQUIRE_POSTGRES is set but no Postgres answers at {url}")
        pytest.skip(f"no Postgres reachable at {url}")
    return url


@pytest.fixture()
def clean_db(database_url: str) -> str:
    engine = make_engine(database_url)
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    engine.dispose()
    return database_url


@pytest.fixture()
def settings(clean_db: str) -> Settings:
    return Settings(database_url=clean_db, write_token=TOKEN, results=ROOT / "results", environment="test")


@pytest.fixture()
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture()
def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}
