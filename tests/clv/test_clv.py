"""Lifetime value: the frames, both likelihoods, recovery of known parameters, the predictions,
the allowance, the holdout table and the cross check.

The simulation designs give each model enough information to identify its parameters, so the
35 percent tolerance is a check and not a coin toss. BG/NBD customers are observed for 180 to
720 days with a mean purchase rate of one every 25 days, so dropout shows in the data; across
twenty seeds the worst error at 4,000 customers was 15 percent (in b). Gamma-Gamma customers
make few repeat purchases, because p and v are told apart only by the noise in a customer's
mean spend, which more purchases average away; the worst error across thirty seeds was 19
percent (in v).
"""

from __future__ import annotations

import datetime as dt
import math
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from marginal_clv import (
    BGNBD,
    CHANNEL_SEGMENT_MIX,
    GammaGamma,
    acquisition_allowance,
    check_mixes,
    cross_check,
    customer_lifetime_value,
    holdout_by_decile,
    holdout_frame,
    rfm_frame,
    segments,
    spend_frequency_correlation,
)
from marginal_contracts.retail import CALIBRATION_END, HOLDOUT_START, split_windows
from marginal_core.config import CHANNELS, POLICY
from marginal_core.seeds import rng
from polars.testing import assert_frame_equal

# Fixtures on the committed purchase history.


@pytest.fixture(scope="module")
def purchases(root: Path) -> pl.DataFrame:
    return pl.read_parquet(root / "data" / "retail" / "purchases.parquet")


@pytest.fixture(scope="module")
def rfm(purchases: pl.DataFrame) -> pl.DataFrame:
    return rfm_frame(purchases, CALIBRATION_END)


@pytest.fixture(scope="module")
def fitted(rfm: pl.DataFrame) -> tuple[BGNBD, GammaGamma]:
    bg = BGNBD().fit(rfm["frequency"], rfm["recency"], rfm["T"])
    gg = GammaGamma().fit(rfm["frequency"], rfm["monetary"])
    return bg, gg


# Simulators of the two models.


def _simulate_bgnbd(
    n: int, r: float, alpha: float, a: float, b: float, seed: int, horizon: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """BG/NBD customers: frequency, recency, age, and purchases in the ``horizon`` days after.

    While active a customer buys at rate lambda ~ Gamma(r, alpha); after each repeat purchase
    they leave with probability p ~ Beta(a, b). The clock runs on past the window's end, which
    the exponential waiting times allow.
    """
    g = rng(seed, "bgnbd_simulation")
    rate = g.gamma(r, 1.0 / alpha, n)
    leave = g.beta(a, b, n)
    age = np.floor(g.uniform(180.0, 721.0, n))
    x, t_x, later = np.zeros(n), np.zeros(n), np.zeros(n)
    for i in range(n):
        t, active = 0.0, True
        while active:
            t += g.exponential(1.0 / rate[i])
            if t > age[i] + horizon:
                break
            if t <= age[i]:
                x[i] += 1
                t_x[i] = t
            else:
                later[i] += 1
            active = g.random() >= leave[i]
    return x, t_x, age, later


def _simulate_spend(n: int, p: float, q: float, v: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Gamma-Gamma customers: repeat purchases x and their mean spend."""
    g = rng(seed, "gamma_gamma_simulation")
    x = 1 + g.poisson(1.0, n)
    scale = g.gamma(q, 1.0 / v, n)
    spend = g.gamma(p, 1.0 / np.repeat(scale, x))
    starts = np.concatenate([[0], np.cumsum(x)[:-1]])
    return x.astype(np.float64), np.add.reduceat(spend, starts) / x


def _simulated_rfm(n: int, seed: int) -> pl.DataFrame:
    """An rfm_frame shaped table drawn from both models, with an interior maximum for each."""
    x, t_x, age, _ = _simulate_bgnbd(n, r=0.8, alpha=20.0, a=0.8, b=2.5, seed=seed, horizon=0.0)
    g = rng(seed, "spend_for_cross_check")
    scale = g.gamma(4.0, 1.0 / 30.0, n)
    monetary = [
        float(g.gamma(2.0, 1.0 / scale[i], int(k)).mean()) if k > 0 else None for i, k in enumerate(x)
    ]
    return pl.DataFrame(
        {
            "customer_id": np.arange(1, n + 1),
            "frequency": x.astype(np.int64),
            "recency": t_x,
            "T": age,
            "monetary": monetary,
        },
        schema_overrides={"monetary": pl.Float64},
    )


# 1. The frames on a table small enough to count by hand.


def _hand_table() -> pl.DataFrame:
    rows = [
        (3, dt.date(2020, 2, 3), 99.0),
        (1, dt.date(2020, 1, 20), 30.0),
        (1, dt.date(2020, 1, 1), 10.0),
        (2, dt.date(2020, 1, 10), 40.0),
        (1, dt.date(2020, 1, 5), 20.0),
        (1, dt.date(2020, 1, 5), 5.0),  # a second basket on the same day is the same purchase
        (3, dt.date(2020, 1, 15), 12.0),
        (4, dt.date(2020, 2, 10), 50.0),  # first bought in the holdout
        (1, dt.date(2020, 2, 5), 7.0),
        (1, dt.date(2020, 2, 5), 8.0),
    ]
    return pl.DataFrame(
        rows, schema={"customer_id": pl.Int64, "day": pl.Date, "revenue": pl.Float64}, orient="row"
    )


def test_rfm_frame_matches_counts_made_by_hand() -> None:
    frame = rfm_frame(_hand_table(), dt.date(2020, 1, 31))
    assert frame["customer_id"].to_list() == [1, 2, 3]
    # Customer 1: days 1, 5 and 20 January, the fifth holding 20 + 5.
    assert frame["purchase_days"].to_list() == [3, 1, 1]
    assert frame["frequency"].to_list() == [2, 0, 0]
    assert frame["recency"].to_list() == [19, 0, 0]
    assert frame["T"].to_list() == [30, 21, 16]
    assert frame["monetary"].to_list() == [pytest.approx((25.0 + 30.0) / 2), None, None]
    assert frame["first_revenue"].to_list() == [10.0, 40.0, 12.0]
    assert frame["first_day"].to_list() == [dt.date(2020, 1, 1), dt.date(2020, 1, 10), dt.date(2020, 1, 15)]


def test_holdout_frame_matches_counts_made_by_hand() -> None:
    frame = holdout_frame(_hand_table(), dt.date(2020, 2, 1), dt.date(2020, 2, 29))
    # Customer 4 first bought in the holdout, so the models have nothing to predict them from.
    assert frame["customer_id"].to_list() == [1, 2, 3]
    assert frame["holdout_purchases"].to_list() == [1, 0, 1]
    assert frame["holdout_revenue"].to_list() == [15.0, 0.0, 99.0]
    assert frame["holdout_days"].to_list() == [29, 29, 29]
    with pytest.raises(ValueError, match="before it starts"):
        holdout_frame(_hand_table(), dt.date(2020, 2, 29), dt.date(2020, 2, 1))


# 2. The windows on the committed file.


def test_holdout_never_overlaps_the_calibration_window(purchases: pl.DataFrame, rfm: pl.DataFrame) -> None:
    calibration, holdout = split_windows(purchases)
    first_holdout, last_holdout = holdout["day"].min(), holdout["day"].max()
    last_calibration, latest_first = calibration["day"].max(), rfm["first_day"].max()
    assert isinstance(first_holdout, dt.date) and isinstance(last_holdout, dt.date)
    assert isinstance(last_calibration, dt.date) and isinstance(latest_first, dt.date)
    assert first_holdout > CALIBRATION_END
    assert last_calibration <= CALIBRATION_END
    assert latest_first <= CALIBRATION_END
    assert calibration.height + holdout.height == purchases.height
    assert CALIBRATION_END + dt.timedelta(days=1) == HOLDOUT_START

    actual = holdout_frame(purchases, HOLDOUT_START, last_holdout)
    assert actual["customer_id"].equals(rfm["customer_id"])
    seen = holdout.filter(pl.col("customer_id").is_in(rfm["customer_id"].to_list()))
    assert int(actual["holdout_purchases"].sum()) == seen.height
    assert (rfm["recency"] <= rfm["T"]).all()


# 3. The likelihood stays finite.


@pytest.mark.parametrize(
    "params",
    [
        {"r": 0.9, "alpha": 74.0, "a": 0.34, "b": 309.0},
        {"r": 1e-8, "alpha": 1e-8, "a": 1e-8, "b": 1e-8},
        {"r": 1e8, "alpha": 1e8, "a": 1e8, "b": 1e8},
        {"r": 1e-8, "alpha": 1e8, "a": 1e8, "b": 1e-8},
        {"r": 50.0, "alpha": 0.01, "a": 0.01, "b": 1e6},
        {"r": 1e-300, "alpha": 1e300, "a": 1e-300, "b": 1e300},
    ],
)
def test_the_likelihood_is_finite_on_the_whole_frame(rfm: pl.DataFrame, params: dict[str, float]) -> None:
    ll = BGNBD(**params).log_likelihood_by_customer(rfm["frequency"], rfm["recency"], rfm["T"])
    assert ll.shape == (rfm.height,)
    assert np.all(np.isfinite(ll))


def _central_difference(fun: Callable[[np.ndarray], float], point: np.ndarray, step: float) -> np.ndarray:
    return np.array(
        [(fun(point + step * e) - fun(point - step * e)) / (2.0 * step) for e in np.eye(point.size)]
    )


def test_both_gradients_match_central_differences(rfm: pl.DataFrame) -> None:
    """The fits rely on the analytic gradients. A one sided difference is too noisy to judge
    them, because betaln and gammaln carry rounding error near 1e-13 into the objective;
    central differences at a step of 1e-4 agree with a correct gradient to about 1e-8, and a
    missing or wrong term would be off by 1e-3 or more."""
    from marginal_clv import bgnbd, gamma_gamma

    x, t_x, age = (rfm[c].to_numpy().astype(np.float64) for c in ("frequency", "recency", "T"))
    point = np.log([0.9, 70.0, 0.4, 250.0])
    _, analytic = bgnbd._objective(point, x, t_x, age)
    numeric = _central_difference(lambda v: bgnbd._objective(v, x, t_x, age)[0], point, 1e-4)
    assert np.allclose(analytic, numeric, rtol=0.0, atol=1e-7)

    repeat = rfm.filter(pl.col("frequency") > 0)
    fx, fm = repeat["frequency"].to_numpy().astype(np.float64), repeat["monetary"].to_numpy()
    point = np.log([2.0, 3.5, 500.0])
    _, analytic = gamma_gamma._objective(point, fx, fm)
    numeric = _central_difference(lambda v: gamma_gamma._objective(v, fx, fm)[0], point, 1e-4)
    assert np.allclose(analytic, numeric, rtol=0.0, atol=1e-7)


# 4 and 5. Recovery of known parameters.


def test_bgnbd_recovers_known_parameters() -> None:
    truth = {"r": 0.8, "alpha": 20.0, "a": 0.8, "b": 2.5}
    x, t_x, age, later = _simulate_bgnbd(4000, **truth, seed=41, horizon=180.0)
    model = BGNBD().fit(x, t_x, age)
    assert model.record is not None and model.record.converged
    for name, value in truth.items():
        assert model.params[name] == pytest.approx(value, rel=0.35), name
    # The conditional expectation, at the fitted parameters, against what the simulated
    # customers went on to do in the next 180 days.
    predicted = model.expected_purchases(180.0, x, t_x, age)
    assert predicted.sum() == pytest.approx(later.sum(), rel=0.10)


def test_a_fit_whose_maximum_is_on_the_edge_is_not_called_converged() -> None:
    """Customers who never leave: the likelihood keeps rising as a goes to zero, so there is no
    estimate of the dropout process to publish, while the purchase process is still identified."""
    g = rng(44, "no_dropout")
    n = 2000
    rate = g.gamma(0.8, 1.0 / 20.0, n)
    age = np.floor(g.uniform(180.0, 721.0, n))
    x = g.poisson(rate * age).astype(np.float64)
    # Given x purchases on (0, age], the last one is the largest of x uniform times.
    t_x = np.array([g.uniform(0.0, a, int(k)).max() if k > 0 else 0.0 for a, k in zip(age, x, strict=True)])
    model = BGNBD().fit(x, t_x, age)
    assert model.record is not None
    assert not model.record.converged
    assert "a" in model.record.beyond_limit
    assert model.r == pytest.approx(0.8, rel=0.35)
    assert model.alpha == pytest.approx(20.0, rel=0.35)


def test_gamma_gamma_recovers_known_parameters() -> None:
    truth = {"p": 2.0, "q": 4.0, "v": 30.0}
    x, m = _simulate_spend(4000, **truth, seed=43)
    model = GammaGamma().fit(x, m)
    assert model.record is not None and model.record.converged
    for name, value in truth.items():
        assert model.params[name] == pytest.approx(value, rel=0.35), name
    assert model.population_mean_spend == pytest.approx(2.0 * 30.0 / 3.0, rel=0.15)
    # Spend was drawn independently of frequency, so the check must read it as weak.
    assert spend_frequency_correlation(x, m).weak


# 6. The predictions behave.


@pytest.mark.parametrize("which", ["fitted", "a_above_one", "a_at_one"])
def test_expected_purchases_grow_with_time_and_probability_alive_is_a_probability(
    rfm: pl.DataFrame, fitted: tuple[BGNBD, GammaGamma], which: str
) -> None:
    model = {
        "fitted": fitted[0],
        "a_above_one": BGNBD(r=0.8, alpha=40.0, a=2.5, b=4.0),
        "a_at_one": BGNBD(r=0.8, alpha=40.0, a=1.0, b=4.0),
    }[which]
    x, t_x, age = rfm["frequency"], rfm["recency"], rfm["T"]
    horizons = np.array([0.0, 1.0, 30.4375, 91.0, 365.25, 3652.5])
    expected = model.expected_purchases(horizons[:, None], x, t_x, age)
    assert expected.shape == (horizons.size, rfm.height)
    assert np.all(np.isfinite(expected)) and np.all(expected >= 0.0)
    assert np.all(expected[0] == 0.0)
    assert np.all(np.diff(expected, axis=0) >= -1e-12)
    assert np.all(expected[-1] > expected[2])
    alive = model.probability_alive(x, t_x, age)
    assert np.all((alive >= 0.0) & (alive <= 1.0))
    assert np.all(alive[rfm["frequency"].to_numpy() == 0] == 1.0)


# 7. The allowance.


def test_allowance_is_positive_and_below_lifetime_value_at_margin(
    rfm: pl.DataFrame, fitted: tuple[BGNBD, GammaGamma]
) -> None:
    bg, gg = fitted
    value = customer_lifetime_value(bg, gg, rfm, POLICY.clv_horizon_months, POLICY.clv_discount_rate_annual)
    valued = segments(rfm.join(value, on="customer_id"))
    margin = POLICY.contribution_margin
    allowance = acquisition_allowance(valued, margin, POLICY.clv_payback_share)
    for s in [*allowance.segments, allowance.overall]:
        assert 0.0 < s.allowance < s.mean_clv * margin, s.segment
    for c in allowance.channels:
        assert 0.0 < c.allowance < c.mean_clv * margin, c.channel
    assert list(allowance.by_channel) == list(CHANNELS)
    by_segment = {s.segment: s for s in allowance.segments}
    assert by_segment["frequent"].mean_clv > by_segment["one_time"].mean_clv

    check_mixes(CHANNEL_SEGMENT_MIX)
    for channel, mix in CHANNEL_SEGMENT_MIX.items():
        assert sum(mix.values()) == pytest.approx(1.0, abs=1e-12), channel
    assert len({tuple(sorted(mix.items())) for mix in CHANNEL_SEGMENT_MIX.values()}) == len(CHANNELS)
    short = {
        **CHANNEL_SEGMENT_MIX,
        "email": {"one_time": 0.2, "occasional": 0.3, "regular": 0.3, "frequent": 0.1},
    }
    with pytest.raises(ValueError, match="sums to"):
        check_mixes(short)


def test_lifetime_value_is_spend_times_purchases_discounted_by_month(
    rfm: pl.DataFrame, fitted: tuple[BGNBD, GammaGamma]
) -> None:
    bg, gg = fitted
    flat = customer_lifetime_value(bg, gg, rfm, 12, 0.0)
    undiscounted = flat["expected_average_spend"].to_numpy() * flat["expected_purchases_horizon"].to_numpy()
    assert np.allclose(flat["clv"].to_numpy(), undiscounted, rtol=1e-10)
    discounted = customer_lifetime_value(bg, gg, rfm, 12, 0.10)["clv"].to_numpy()
    assert np.all(discounted < undiscounted)
    # Even a purchase at the horizon's end is discounted by no more than a year at ten percent.
    assert np.all(discounted >= undiscounted / 1.10 - 1e-9)


def test_segments_follow_the_stated_frequency_bands() -> None:
    frame = segments(pl.DataFrame({"frequency": [0, 1, 2, 3, 5, 6, 40]}))
    assert frame["segment"].to_list() == [
        "one_time",
        "occasional",
        "occasional",
        "regular",
        "regular",
        "frequent",
        "frequent",
    ]
    assert frame["segment_label"].to_list()[0] == "one time"


# 8. The holdout table adds up.


def test_holdout_by_decile_totals_equal_the_sums_of_the_input() -> None:
    g = rng(8, "decile_test")
    n = 1003
    bought = g.poisson(1.0, n)
    frame = pl.DataFrame(
        {
            "customer_id": np.arange(5000, 5000 + n),
            "frequency": g.poisson(1.5, n),  # many ties, so the customer id order matters
            "holdout_purchases": bought,
            "holdout_revenue": np.where(bought > 0, g.gamma(2.0, 60.0, n) * bought, 0.0),
        }
    )
    predicted_purchases = g.gamma(1.0, 1.0, n)
    predicted_revenue = predicted_purchases * g.gamma(4.0, 20.0, n)
    table = holdout_by_decile(frame, predicted_purchases, predicted_revenue)
    deciles = table.filter(pl.col("decile") != "all")
    overall = table.filter(pl.col("decile") == "all")
    assert deciles["decile"].to_list() == [str(d) for d in range(1, 11)]
    assert overall.height == 1
    sums = {
        "customers": n,
        "predicted_purchases": predicted_purchases.sum(),
        "actual_purchases": int(bought.sum()),
        "predicted_revenue": predicted_revenue.sum(),
        "actual_revenue": frame["holdout_revenue"].sum(),
    }
    for column, total in sums.items():
        assert deciles[column].sum() == pytest.approx(total, rel=1e-12), column
        assert overall[column][0] == pytest.approx(total, rel=1e-12), column
    assert overall["mae_purchases"][0] == pytest.approx(np.mean(np.abs(predicted_purchases - bought)))
    sizes = deciles["customers"].to_list()
    assert max(sizes) - min(sizes) <= 1
    highs, lows = deciles["frequency_high"].to_list(), deciles["frequency_low"].to_list()
    assert all(h <= lo for h, lo in zip(highs[:-1], lows[1:], strict=True))
    # The table depends on the customers, not on the order their rows arrive in.
    order = g.permutation(n)
    shuffled = holdout_by_decile(frame[order], predicted_purchases[order], predicted_revenue[order])
    assert_frame_equal(shuffled, table)


# 9. The cross check.


@pytest.mark.pymc
def test_the_cross_check_agrees_with_pymc_marketing_on_300_customers() -> None:
    """Simulated customers, because small samples of the retail file put the BG/NBD maximum on
    the edge of the parameter space, where a and b run off along a flat ridge and two correct
    optimizers stop at different points with the same likelihood."""
    frame = _simulated_rfm(300, seed=51)
    check = cross_check(frame)
    assert check.available and check.customers == 300
    assert len(check.parameters) == 7
    for row in check.parameters:
        assert row.pymc is not None
        assert math.copysign(1.0, row.pymc) == math.copysign(1.0, row.repository), row.parameter
        assert abs(math.log10(row.pymc / row.repository)) < 1.0, row.parameter
    # Same likelihood, same flat priors, both run to convergence: the two should agree closely.
    assert check.max_relative_difference is not None and check.max_relative_difference < 1e-3
    assert check.bgnbd_log_likelihood_gap is not None and abs(check.bgnbd_log_likelihood_gap) < 1e-6
    assert (
        check.gamma_gamma_log_likelihood_gap is not None and abs(check.gamma_gamma_log_likelihood_gap) < 1e-6
    )


def test_the_cross_check_reports_itself_unavailable_without_the_library(
    rfm: pl.DataFrame, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "pymc_marketing", None)
    check = cross_check(rfm.head(300))
    assert not check.available
    assert check.reason is not None and "not importable" in check.reason
    assert all(row.pymc is None for row in check.parameters)
    assert check.max_relative_difference is None
