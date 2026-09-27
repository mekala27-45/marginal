from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest
from marginal_calibrate import (
    before_after,
    error_summary,
    lift_from_registry,
    recovery_after_calibration,
    weight_interior_test,
)
from marginal_evaluation import observed
from marginal_mmm import LiftResult, MMMSpec, fit
from marginal_sim import MarketSpec, national_truth_table, simulate_market

FAST = MMMSpec(backend="own", seed=3, bootstrap_replicates=30, nelder_mead_evaluations=200)


def _lift(model: object, national: pl.DataFrame) -> LiftResult:
    probe = LiftResult(
        channel="display_retargeting",
        window_start_week=88,
        window_end_week=95,
        geo_share=0.25,
        incremental_revenue=1.0,
        standard_error=1.0,
        spend_change=-1.0,
        experiment_id="e",
        plan_hash="h",
    )
    implied = model.implied_lift(probe)  # type: ignore[attr-defined]
    return probe.model_copy(
        update={"incremental_revenue": implied * 0.6, "standard_error": max(implied * 0.05, 1.0)}
    )


def test_before_after_moves_the_tested_channel_toward_the_experiment() -> None:
    _, national, market = simulate_market(MarketSpec(seed=3, weeks=96))
    truth = national_truth_table(national, market)
    model = fit(observed(national), FAST)
    lift = _lift(model, national)
    calibrated, summary = before_after(
        model, lift, truth, truth_lift=lift.incremental_revenue, experiment={"lower": 0.0, "upper": 1.0}
    )
    assert summary.channel == "display_retargeting"
    assert abs(summary.implied_lift_after - lift.incremental_revenue) < abs(
        summary.implied_lift_before - lift.incremental_revenue
    )
    assert calibrated.diagnostics()["calibrated"] == 1
    assert summary.roas_after < summary.roas_before


def test_weight_interior_test_runs_three_fits_and_reports() -> None:
    _, national, _ = simulate_market(MarketSpec(seed=4, weeks=96))
    model = fit(observed(national), FAST)
    lift = _lift(model, national)
    test = weight_interior_test(observed(national), FAST, lift)
    assert test.residual_half != test.residual_one
    assert isinstance(test.interior, bool) and test.reason


def test_weight_test_rejects_an_exact_reproduction() -> None:
    """A weight that reproduces the experiment exactly is degenerate by construction: give the
    experiment a standard error near zero and the residual collapses."""
    _, national, _ = simulate_market(MarketSpec(seed=4, weeks=96))
    model = fit(observed(national), FAST)
    lift = _lift(model, national).model_copy(update={"standard_error": 1e-6})
    test = weight_interior_test(observed(national), FAST, lift)
    assert not test.interior
    assert "exactly" in test.reason


def test_recovery_after_calibration_records_every_seed_and_channel() -> None:
    rows = recovery_after_calibration(
        "own", [41, 42], MarketSpec(seed=41, weeks=104), lambda s: FAST.model_copy(update={"seed": s})
    )
    assert rows.height == 2 * 7
    summary = error_summary(rows)
    assert summary["seeds"] == 2 and 0.0 <= summary["coverage"] <= 1.0


def test_lift_from_registry_reads_the_posted_result(tmp_path: Path) -> None:
    results = tmp_path / "results" / "experiments"
    results.mkdir(parents=True)
    (results / "geo_result.json").write_text(
        json.dumps(
            {
                "did": {"incremental_revenue": 100.0, "standard_error": 5.0},
                "truth": 90.0,
                "experiment_id": "x",
                "plan_hash": "h" * 16,
            }
        )
    )
    (results / "geo_design.json").write_text(
        json.dumps(
            {
                "design": {
                    "channel": "email",
                    "start_week": 10,
                    "end_week": 17,
                    "treated_geos": [0, 1],
                    "spend_change": -1.0,
                }
            }
        )
    )
    geo = pl.DataFrame({"week": [0, 0, 0], "geo": [0, 1, 2], "geo_weight": [0.2, 0.3, 0.5]})
    lift, truth = lift_from_registry(tmp_path / "results", geo)
    assert lift.channel == "email" and lift.geo_share == pytest.approx(0.5) and truth == 90.0
    assert lift.window_end_week == 17
