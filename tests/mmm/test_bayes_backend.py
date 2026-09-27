"""The bayes backend: the sampler ran as specified, the outputs carry the interface shape in
dollars, the numpy transforms agree with the library, a seed fixes the fit, a lift test pulls
the model toward the experiment, and a fit over its ceilings is reported rather than raised.

Every fit here draws 40 samples on two chains after 40 tuning steps, so the suite runs in
minutes; the tolerances that depend on that are loose and say so. The backend is imported
through `marginal_mmm.fit` or inside a test, so this module collects without PyMC and the
pymc marker can skip it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import polars as pl
import pytest
from marginal_core.config import CHANNELS
from marginal_evaluation import observed
from marginal_mmm import ChannelReturn, LiftResult, MMMSpec, fit, geometric_adstock, hill
from marginal_sim import MarketSpec, simulate_market

if TYPE_CHECKING:
    from marginal_mmm.bayes import BayesModel

FAST = MMMSpec(backend="bayes", seed=5, chains=2, draws=40, tune=40)


@pytest.fixture(scope="module")
def panel() -> pl.DataFrame:
    _, national, _ = simulate_market(MarketSpec(seed=5, weeks=104))
    return observed(national)


@pytest.fixture(scope="module")
def model(panel: pl.DataFrame) -> BayesModel:
    fitted = fit(panel, FAST)
    from marginal_mmm.bayes import BayesModel

    assert isinstance(fitted, BayesModel)
    return fitted


def _display_holdout(incremental_revenue: float, standard_error: float) -> LiftResult:
    return LiftResult(
        channel="display_retargeting",
        window_start_week=90,
        window_end_week=101,
        geo_share=0.25,
        incremental_revenue=incremental_revenue,
        standard_error=standard_error,
        spend_change=-1.0,
        experiment_id="exp-1",
        plan_hash="abcd",
    )


@pytest.mark.pymc
def test_the_sampler_ran_as_specified(model: BayesModel) -> None:
    """Did it run: the counts are read from what the sampler wrote, not copied from the spec."""
    d = model.diagnostics()
    assert d["chains"] == 2
    assert d["draws"] == 40
    assert d["tune"] == 40
    assert model.contribution_draws.shape == (2 * 40, 104, len(CHANNELS))
    assert isinstance(d["divergences"], int) and d["divergences"] >= 0
    assert isinstance(d["max_rhat"], float) and np.isfinite(d["max_rhat"])
    assert isinstance(d["fit_status"], str)
    assert (d["fit_status"] == "ok") == (d["failed_ceilings"] == "")
    assert float(d["sampling_seconds"]) > 0.0
    assert "saturation_beta" in str(d["priors"])
    assert d["backend"] == "bayes" and d["data_source"] == "simulated" and d["calibrated"] == 0
    assert len(str(d["spec_hash"])) == 16


@pytest.mark.pymc
def test_outputs_carry_the_interface_shape_in_dollars(model: BayesModel, panel: pl.DataFrame) -> None:
    returns = model.intervals()
    assert [r.channel for r in returns] == list(CHANNELS)
    for r in returns:
        assert isinstance(r, ChannelReturn)
        assert r.roas_lower <= r.roas <= r.roas_upper, r.channel
        assert r.spend_last_year > 0.0 and r.incremental_last_year >= 0.0
        assert r.marginal_return >= 0.0
        assert 0.0 < r.carryover < 1.0 and r.half_life_weeks >= 0.0
        assert r.half_saturation > 0.0 and r.slope > 0.0

    frame = model.contributions()
    assert frame.columns == ["week", "baseline", *CHANNELS, "fitted", "sales", "residual"]
    assert frame.height == panel.height
    fitted = frame["fitted"].to_numpy()
    sales = frame["sales"].to_numpy()
    # The baseline is assembled from the intercept, controls and seasonality, so with the
    # channels it has to rebuild the fit the library reports.
    modeled = frame["baseline"].to_numpy() + sum(frame[c].to_numpy() for c in CHANNELS)
    assert np.mean(np.abs(modeled - fitted) / np.abs(fitted)) < 0.05
    # Loose because forty draws; what it rules out is a fit left in the library's scaled units.
    assert np.mean(np.abs(fitted - sales) / sales) < 0.25
    media_share = float(sum(frame[c].sum() for c in CHANNELS)) / float(frame["sales"].sum())
    assert 0.02 < media_share < 0.95

    grid = np.linspace(0.0, 300_000.0, 31)
    for c in CHANNELS:
        curve = model.response_curve(c, grid)
        assert curve[0] == 0.0 and np.all(np.diff(curve) >= 0.0), c
        assert model.marginal_return(c, 60_000.0) >= 0.0


@pytest.mark.pymc
def test_the_repository_transforms_reproduce_the_library_contributions(model: BayesModel) -> None:
    """The response curve is numpy arithmetic on the library's parameters. Rebuilding every
    posterior draw with the repository's adstock (lags 0 to the max lag) and Hill curve, spend
    in dollars divided by the channel's scale and the result times the sales scale, must give
    the library's own contributions; this pins the lag count, the parameter roles and the units."""
    posterior = model.mmm.idata["posterior"]
    columns = [f"spend_{c}" for c in CHANNELS]

    def draws(name: str) -> np.ndarray:
        stacked = posterior[name].sel(channel=columns).stack(sample=("chain", "draw"))
        return np.asarray(stacked.transpose("sample", "channel").to_numpy())

    alpha, beta, kappa, slope = (
        draws(n) for n in ("adstock_alpha", "saturation_beta", "saturation_kappa", "saturation_slope")
    )
    rebuilt = np.zeros_like(model.contribution_draws)
    for s in range(alpha.shape[0]):
        for j in range(len(CHANNELS)):
            scaled = model.spend[:, j] / model.channel_scale[j]
            stocked = geometric_adstock(scaled, float(alpha[s, j]), model.spec.adstock_max_lag)
            rebuilt[s, :, j] = model.target_scale * beta[s, j] * hill(stocked, kappa[s, j], slope[s, j])
    assert np.allclose(rebuilt, model.contribution_draws, rtol=1e-9, atol=1e-6)


@pytest.mark.pymc
def test_a_seed_fixes_the_fit_whatever_the_row_order(model: BayesModel, panel: pl.DataFrame) -> None:
    again = fit(panel.sample(fraction=1.0, shuffle=True, seed=1), FAST)
    assert [e.roas for e in again.intervals()] == [e.roas for e in model.intervals()]


@pytest.mark.pymc
def test_a_lift_test_pulls_the_implied_lift_toward_the_experiment(model: BayesModel) -> None:
    """The experiment finds 40 percent of what the uncalibrated model implies, with a standard
    error well under the gap, so the calibrated posterior has to move toward it."""
    uncalibrated = model.implied_lift(_display_holdout(0.0, 1.0))
    lift = _display_holdout(0.4 * uncalibrated, 20_000.0)
    calibrated = model.calibrate([lift])
    before = abs(model.implied_lift(lift) - lift.incremental_revenue)
    after = abs(calibrated.implied_lift(lift) - lift.incremental_revenue)
    assert after < before
    d = calibrated.diagnostics()
    assert d["calibrated"] == 1
    assert d["calibration_experiment_lift"] == lift.incremental_revenue
    assert calibrated.lift_results == [lift]


@pytest.mark.pymc
def test_a_fit_over_its_ceilings_is_reported_not_raised(panel: pl.DataFrame) -> None:
    """A divergence ceiling of -1 fails every fit; the rhat ceiling is lifted out of the way so
    the status can only come from the divergence count."""
    strict = MMMSpec(backend="bayes", seed=5, chains=2, draws=40, tune=40, max_divergences=-1, max_rhat=100.0)
    model = fit(panel, strict)
    d = model.diagnostics()
    assert d["fit_status"] == "failed ceilings"
    assert d["failed_ceilings"] == "divergences"
    assert len(model.intervals()) == len(CHANNELS)
