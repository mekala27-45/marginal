"""The own backend: transforms, the interface, known truth recovery, and the calibration row."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from marginal_evaluation import observed
from marginal_mmm import LiftResult, MMMSpec, fit, geometric_adstock, half_life, hill, hill_slope
from marginal_mmm.own import OwnModel, fit_own
from marginal_sim import MarketSpec, national_truth_table, simulate_market

FAST = MMMSpec(backend="own", seed=7, bootstrap_replicates=40, nelder_mead_evaluations=300)


@pytest.fixture(scope="module")
def clean_market() -> tuple[pl.DataFrame, pl.DataFrame, OwnModel]:
    spec = MarketSpec(
        seed=7,
        spend_correlation=0.0,
        demand_feedback=False,
        sales_noise=0.0,
        competitor_noise=0.0,
        geo_spend_noise=0.0,
    )
    _, national, market = simulate_market(spec)
    truth = national_truth_table(national, market)
    model = fit_own(
        observed(national),
        MMMSpec(backend="own", seed=7, bootstrap_replicates=50, nelder_mead_evaluations=600),
    )
    return national, truth, model


def test_adstock_zero_retention_is_identity_and_constant_is_preserved() -> None:
    x = np.array([3.0, 1.0, 4.0, 1.0, 5.0])
    assert np.allclose(geometric_adstock(x, 0.0, 4), x)
    c = np.full(30, 2.0)
    assert np.allclose(geometric_adstock(c, 0.7, 6)[6:], 2.0)
    with pytest.raises(ValueError):
        geometric_adstock(x, 1.0, 4)


@given(st.floats(0.0, 1e6), st.floats(1e3, 5e5), st.floats(0.5, 3.0))
@settings(max_examples=40)
def test_hill_is_monotone_bounded_and_its_slope_non_negative(x: float, k: float, s: float) -> None:
    a = float(hill(np.array([x]), k, s)[0])
    b = float(hill(np.array([x + 10.0]), k, s)[0])
    assert 0.0 <= a <= b <= 1.0
    assert hill_slope(x, k, s) >= 0.0


def test_half_life() -> None:
    assert half_life(0.5) == pytest.approx(1.0)
    assert half_life(0.0) == 0.0


def test_known_truth_recovery_on_a_clean_uncorrelated_market(
    clean_market: tuple[pl.DataFrame, pl.DataFrame, OwnModel],
) -> None:
    """Stated tolerances: every marginal return within 25 percent, every carryover rate within
    0.15, every return within 40 percent, with zero noise, no correlation and no feedback."""
    _, truth, model = clean_market
    for est, row in zip(model.intervals(), truth.iter_rows(named=True), strict=True):
        assert est.channel == row["channel"]
        assert abs(est.marginal_return / row["marginal_return_true"] - 1.0) < 0.25, est.channel
        assert abs(est.carryover - row["carryover"]) < 0.15, est.channel
        assert abs(est.roas / row["roas_true"] - 1.0) < 0.40, est.channel


def test_the_steps_ran(clean_market: tuple[pl.DataFrame, pl.DataFrame, OwnModel]) -> None:
    """Did the step run: the bootstrap drew the stated replicates, the grid and the search
    evaluated, the solver converged on every channel."""
    _, _, model = clean_market
    d = model.diagnostics()
    assert d["bootstrap_replicates"] == 50
    assert model.bootstrap_beta.shape == (50, 7)
    assert int(d["grid_evaluations"]) == 7 * 4 * 4 * 3
    assert int(d["nelder_mead_evaluations"]) >= 300
    assert d["backend"] == "own" and d["data_source"] == "simulated"
    assert len(str(d["spec_hash"])) == 16


def test_outputs_carry_the_interface_shape(clean_market: tuple[pl.DataFrame, pl.DataFrame, OwnModel]) -> None:
    national, _, model = clean_market
    contributions = model.contributions()
    assert contributions.height == national.height
    modeled = contributions["baseline"] + sum(contributions[c] for c in model.channels)
    assert np.allclose(modeled.to_numpy(), contributions["fitted"].to_numpy())
    grid = np.array([0.0, 50_000.0, 100_000.0, 200_000.0])
    curve = model.response_curve("paid_search", grid)
    assert curve[0] == 0.0 and np.all(np.diff(curve) >= 0)
    assert model.marginal_return("paid_search", 100_000.0) >= 0.0
    for est in model.intervals():
        assert est.roas_lower <= est.roas_upper
        assert est.spend_last_year > 0


def test_fit_is_deterministic_for_a_seed_and_shuffle_proof() -> None:
    _, national, _ = simulate_market(MarketSpec(seed=3, weeks=104))
    panel = observed(national)
    a = fit(panel, FAST)
    b = fit(panel.sample(fraction=1.0, shuffle=True, seed=1), FAST)
    assert [e.roas for e in a.intervals()] == [e.roas for e in b.intervals()]


def test_calibration_row_moves_the_implied_lift_toward_the_experiment() -> None:
    _, national, _ = simulate_market(MarketSpec(seed=5, weeks=104))
    panel = observed(national)
    base = fit_own(panel, FAST)
    lift = LiftResult(
        channel="display_retargeting",
        window_start_week=90,
        window_end_week=101,
        geo_share=0.25,
        incremental_revenue=base.implied_lift(
            LiftResult(
                channel="display_retargeting",
                window_start_week=90,
                window_end_week=101,
                geo_share=0.25,
                incremental_revenue=0.0,
                standard_error=1.0,
                spend_change=-1.0,
                experiment_id="x",
                plan_hash="h",
            )
        )
        * 0.4,
        standard_error=20_000.0,
        spend_change=-1.0,
        experiment_id="exp-1",
        plan_hash="abcd",
    )
    calibrated = base.calibrate([lift])
    before = abs(base.implied_lift(lift) - lift.incremental_revenue)
    after = abs(calibrated.implied_lift(lift) - lift.incremental_revenue)
    assert after < before
    assert calibrated.diagnostics()["calibrated"] == 1
    assert calibrated.calibration_residuals["experiment_lift"] == lift.incremental_revenue


def test_a_channel_with_no_spend_variation_gets_a_wide_interval_not_a_crash() -> None:
    _, national, _ = simulate_market(MarketSpec(seed=9, weeks=80))
    panel = observed(national).with_columns(pl.lit(1000.0).alias("spend_direct_mail"))
    model = fit(panel, FAST)
    assert any(e.channel == "direct_mail" for e in model.intervals())
