"""The Makefile's pipeline target runs the stages in the order the registry declares."""

from __future__ import annotations

import re
from pathlib import Path

from marginal_registry.stages.assemble import ORDER

ROOT = Path(__file__).resolve().parents[2]
MAKE_NAMES = {"recovery_own": "recovery", "recovery_bayes": "recovery-bayes"}


def test_makefile_pipeline_follows_the_stage_order() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    match = re.search(r"^pipeline:\s*(.+)$", text, re.M)
    assert match is not None, "the Makefile has no pipeline target"
    targets = match.group(1).split()
    expected = [MAKE_NAMES.get(name, name) for name in ORDER if name != "data"]
    assert targets[: len(expected)] == expected
    assert targets[len(expected) :] == ["manifest", "render", "marts"]


def test_lifetime_value_runs_before_the_budget() -> None:
    assert ORDER.index("clv") < ORDER.index("budget")
