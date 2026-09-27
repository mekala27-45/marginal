"""Shared fixtures and the availability probes behind the named skip markers."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _importable(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    external_ready = all(
        (ROOT / "data" / "external" / name).exists()
        for name in ("hillstorm_no_indices.csv.gz", "online+retail+ii.zip", "criteo-uplift-v2.1.csv.gz")
    )
    pymc_ready = _importable("pymc_marketing")
    lgbm_ready = _importable("lightgbm")
    for item in items:
        if "external" in item.keywords and not external_ready:
            if os.environ.get("MARGINAL_REQUIRE_EXTERNAL"):
                pytest.fail(
                    "MARGINAL_REQUIRE_EXTERNAL is set but the public datasets are not under data/external"
                )
            item.add_marker(pytest.mark.skip(reason="the public datasets are not under data/external"))
        if "pymc" in item.keywords and not pymc_ready:
            if os.environ.get("MARGINAL_REQUIRE_PYMC"):
                pytest.fail("MARGINAL_REQUIRE_PYMC is set but pymc_marketing does not import")
            item.add_marker(pytest.mark.skip(reason="pymc_marketing is not importable"))
        if "lightgbm" in item.keywords and not lgbm_ready:
            if os.environ.get("MARGINAL_REQUIRE_LIGHTGBM"):
                pytest.fail("MARGINAL_REQUIRE_LIGHTGBM is set but lightgbm does not import")
            item.add_marker(pytest.mark.skip(reason="lightgbm is not importable"))


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT
