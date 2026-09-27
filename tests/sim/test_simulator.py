"""Known truth tests on the simulator: the properties the truth tables must have by construction."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from marginal_core.config import CHANNELS
from marginal_sim import (
    CustomerSpec,
    MarketSpec,
    PathSpec,
    adstock,
    hill,
    hill_derivative,
    marginal_return,
    national_truth_table,
    quadrant_shares,
    response,
    simulate_customers,
    simulate_market,
    simulate_paths,
    true_incremental_share,
    truth_params,
)
from marginal_sim.spec import DEFAULT_CHANNELS


def test_adstock_with_zero_retention_is_the_identity() -> None:
    x = np.array([[1.0, 2.0, 3.0, 4.0]])
    assert np.allclose(adstock(x, 0.0, 5), x)


def test_adstock_of_a_constant_is_the_constant() -> None:
    x = np.full((2, 40), 7.0)
    stocked = adstock(x, 0.6, 13)
    assert np.allclose(stocked[:, 13:], 7.0)


@given(st.floats(0.0, 1e7), st.floats(1e3, 1e6), st.floats(0.5, 4.0))
@settings(max_examples=60)
def test_hill_is_bounded_and_monotone(x: float, k: float, s: float) -> None:
    lo = float(hill(np.array([x]), k, s)[0])
    hi = float(hill(np.array([x * 1.5 + 1.0]), k, s)[0])
    assert 0.0 <= lo <= hi <= 1.0


def test_hill_derivative_is_non_negative_and_matches_a_difference() -> None:
    k, s = 90_000.0, 1.8
    for x in (10_000.0, 90_000.0, 400_000.0):
        d = hill_derivative(x, k, s)
        numeric = float((hill(np.array([x + 1.0]), k, s) - hill(np.array([x - 1.0]), k, s))[0]) / 2.0
        assert d >= 0.0
        assert d == pytest.approx(numeric, rel=1e-4)


def test_truth_params_reproduce_the_stated_return_at_mean_spend() -> None:
    for channel in DEFAULT_CHANNELS:
        p = truth_params(channel)
        at_mean = float(response(p, np.array([channel.mean_weekly_spend]))[0])
        assert at_mean / channel.mean_weekly_spend == pytest.approx(channel.roas_at_mean, rel=1e-9)
        assert marginal_return(p, channel.mean_weekly_spend) < channel.roas_at_mean


def test_market_sales_are_baseline_plus_contributions_up_to_noise() -> None:
    geo, national, market = simulate_market(MarketSpec(seed=3, sales_noise=0.0))
    modeled = national["baseline_true"] + sum(national[f"incremental_true_{c}"] for c in CHANNELS)
    assert np.allclose(national["sales"].to_numpy(), modeled.to_numpy())
    assert geo.height == market.spec.geos * market.spec.weeks
    assert national.height == market.spec.weeks
    geo_sum = geo.group_by("week").agg(pl.col("sales").sum()).sort("week")["sales"].to_numpy()
    assert np.allclose(geo_sum, national["sales"].to_numpy())


def test_spend_correlation_rises_with_the_condition() -> None:
    low = simulate_market(MarketSpec(seed=5, spend_correlation=0.2, demand_feedback=False))[2]
    high = simulate_market(MarketSpec(seed=5, spend_correlation=0.9, demand_feedback=False))[2]
    assert low.achieved_spend_correlation < 0.45
    assert high.achieved_spend_correlation > 0.85


def test_feedback_makes_retargeting_spend_follow_baseline() -> None:
    off = simulate_market(MarketSpec(seed=8, demand_feedback=False))[1]
    on = simulate_market(MarketSpec(seed=8, demand_feedback=True))[1]

    def corr(frame: pl.DataFrame) -> float:
        return float(
            np.corrcoef(frame["spend_display_retargeting"].to_numpy(), frame["baseline_true"].to_numpy())[
                0, 1
            ]
        )

    assert corr(on) > corr(off) + 0.2


def test_market_is_deterministic_for_a_seed_and_differs_across_seeds() -> None:
    a = simulate_market(MarketSpec(seed=11))[1]
    b = simulate_market(MarketSpec(seed=11))[1]
    c = simulate_market(MarketSpec(seed=12))[1]
    assert a.equals(b)
    assert not a.equals(c)


def test_truth_table_returns_match_the_panel() -> None:
    _, national, market = simulate_market(MarketSpec(seed=2))
    truth = national_truth_table(national, market)
    tail = national.tail(52)
    row = truth.filter(pl.col("channel") == "email").row(0, named=True)
    assert row["roas_true"] == pytest.approx(
        float(tail["incremental_true_email"].sum()) / float(tail["spend_email"].sum())
    )
    assert list(truth["channel"]) == list(CHANNELS)


def test_customers_quadrants_are_exact_and_the_policy_targets_sure_things() -> None:
    randomized, policy, truth = simulate_customers(CustomerSpec(seed=4, customers=20_000))
    shares = quadrant_shares(truth)
    assert sum(shares.values()) == pytest.approx(1.0)
    persuadable = truth.filter(pl.col("quadrant") == "persuadable")
    assert (persuadable["y0"] == 0).all() and (persuadable["y1"] == 1).all()
    dogs = truth.filter(pl.col("quadrant") == "sleeping_dog")
    assert (dogs["y0"] == 1).all() and (dogs["y1"] == 0).all()
    assert dogs.height > 0
    # Observed outcomes are the potential outcome of the assigned arm.
    joined = randomized.join(truth.select(["customer_id", "y0", "y1"]), on="customer_id")
    expected = pl.when(pl.col("treated") == 1).then(pl.col("y1")).otherwise(pl.col("y0"))
    assert joined.filter(pl.col("converted") != expected).height == 0
    # The sure things policy contacts higher baseline converters than it leaves alone.
    p = policy.join(truth.select(["customer_id", "p0_true"]), on="customer_id")
    contacted = p.filter(pl.col("treated") == 1)["p0_true"].mean()
    left = p.filter(pl.col("treated") == 0)["p0_true"].mean()
    assert float(contacted) > float(left)  # type: ignore[arg-type]
    assert policy["treated"].mean() == pytest.approx(0.30, abs=0.001)


def test_oracle_policy_on_the_customers_has_no_regret_by_construction() -> None:
    _, _, truth = simulate_customers(CustomerSpec(seed=6, customers=10_000))
    oracle = truth.filter(pl.col("quadrant") == "persuadable").height
    value = truth.with_columns((pl.col("y1") - pl.col("y0")).alias("gain"))
    best = value.filter(pl.col("gain") > 0)["gain"].sum()
    assert best == oracle


def test_paths_credit_sums_and_the_retargeting_trap() -> None:
    touches, users = simulate_paths(PathSpec(seed=9, users=8_000))
    assert touches.height == int(users["touches"].sum())
    shares = true_incremental_share(touches)
    assert shares["share_true"].sum() == pytest.approx(1.0)
    last = (
        touches.join(users.select(["user_id", "converted"]), on="user_id")
        .filter(pl.col("converted") == 1)
        .sort(["user_id", "position"])
        .group_by("user_id")
        .last()
    )
    last_share = last.filter(pl.col("channel") == "display_retargeting").height / last.height
    truth_share = shares.filter(pl.col("channel") == "display_retargeting")["share_true"][0]
    assert last_share > 2 * truth_share
    # A touch's credit never exceeds its own effect and is non negative.
    assert (touches["credit_true"] >= 0).all()
    assert (touches["credit_true"] <= touches["touch_effect_true"] + 1e-12).all()


def test_paths_single_channel_credit_goes_to_that_channel() -> None:
    touches, _ = simulate_paths(PathSpec(seed=9, users=3_000))
    only_email = touches.filter(pl.col("channel") == "email")
    shares = true_incremental_share(only_email)
    assert shares.height == 1 and shares["share_true"][0] == pytest.approx(1.0)
