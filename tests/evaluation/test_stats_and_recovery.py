from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from marginal_core.config import CHANNELS
from marginal_evaluation import (
    ChannelEstimate,
    FitResult,
    benjamini_hochberg,
    bootstrap_interval,
    coverage,
    floor_crossing,
    normal_interval,
    observed,
    paired_bootstrap,
    run_recovery,
    spearman,
    summarise,
)
from marginal_sim import MarketSpec, national_truth_table, simulate_market


def test_bootstrap_interval_contains_the_mean_and_is_order_independent() -> None:
    x = np.arange(1, 101, dtype=float)
    a = bootstrap_interval(x, replicates=300, seed=3)
    b = bootstrap_interval(x[::-1], replicates=300, seed=3)
    assert a.lower <= 50.5 <= a.upper
    assert a == b
    assert a.replicates == 300


def test_bootstrap_refuses_empty_and_handles_one_value() -> None:
    with pytest.raises(ValueError, match="empty"):
        bootstrap_interval([])
    one = bootstrap_interval([2.0])
    assert one.lower == one.upper == 2.0 and one.replicates == 0


def test_paired_bootstrap_sees_a_paired_difference_a_plain_one_would_miss() -> None:
    r = np.random.default_rng(1)
    base = r.normal(0, 10, 200)
    a = base + 0.5
    b = base
    paired = paired_bootstrap(a, b, replicates=400, seed=2)
    assert paired.lower > 0
    with pytest.raises(ValueError, match="one value of each"):
        paired_bootstrap([1.0, 2.0], [1.0])


def test_benjamini_hochberg_matches_a_known_example() -> None:
    p = [0.01, 0.04, 0.03, 0.20, 0.5]
    adjusted, rejected = benjamini_hochberg(p, q=0.05)
    assert adjusted == pytest.approx([0.05, 0.2 / 3, 0.2 / 3, 0.25, 0.5])
    assert rejected == [True, False, False, False, False]
    assert benjamini_hochberg(p, q=0.10)[1] == [True, True, True, False, False]
    assert benjamini_hochberg([]) == ([], [])


def test_normal_interval_and_coverage() -> None:
    i = normal_interval(1.0, 0.5, level=0.90)
    assert i.lower == pytest.approx(1.0 - 1.6449 * 0.5, abs=1e-3)
    assert coverage([i, i], [1.2, 3.0]) == 0.5
    with pytest.raises(ValueError):
        coverage([], [])


def test_spearman() -> None:
    assert spearman([1, 2, 3], [10, 20, 30]) == 1.0
    assert spearman([1, 2, 3], [30, 20, 10]) == -1.0
    assert spearman([1, 1, 1], [1, 2, 3]) == 0.0


def test_observed_strips_every_truth_column() -> None:
    _, national, _ = simulate_market(MarketSpec(seed=1, weeks=30))
    seen = observed(national)
    assert not any("true" in c for c in seen.columns)
    assert "sales" in seen.columns and "spend_email" in seen.columns


def _oracle_fit(national: pl.DataFrame, seed: int) -> FitResult:
    """A backend that reads the truth back: bias zero, coverage one, rank agreement one."""
    spec = MarketSpec(seed=seed, spend_correlation=0.2, demand_feedback=False)
    _, full, market = simulate_market(spec)
    truth = national_truth_table(full, market)
    channels = [
        ChannelEstimate(
            channel=str(r["channel"]),
            roas=float(r["roas_true"]),
            roas_lower=float(r["roas_true"]) * 0.9,
            roas_upper=float(r["roas_true"]) * 1.1,
            marginal_return=float(r["marginal_return_true"]),
        )
        for r in truth.iter_rows(named=True)
    ]
    return FitResult(backend="oracle", channels=channels, diagnostics={"ran": 1})


def _noisy_fit(national: pl.DataFrame, seed: int) -> FitResult:
    channels = [
        ChannelEstimate(channel=c, roas=5.0, roas_lower=4.9, roas_upper=5.1, marginal_return=float(i))
        for i, c in enumerate(CHANNELS)
    ]
    return FitResult(backend="noisy", channels=channels, diagnostics={"ran": 1})


def test_recovery_runner_grades_an_oracle_as_perfect() -> None:
    rows, ranks, diagnostics = run_recovery(_oracle_fit, "oracle", [(0.2, False)], seeds=3, first_seed=50)
    assert rows.height == 3 * len(CHANNELS)
    assert rows["covered"].all()
    assert np.allclose(rows["relative_error"].to_numpy(), 0.0)
    assert ranks["rank_agreement"].to_list() == [1.0, 1.0, 1.0]
    assert len(diagnostics) == 3
    summary = summarise(rows, ranks)
    all_row = summary.filter(pl.col("channel") == "all").row(0, named=True)
    assert all_row["rank_agreement"] == 1.0 and all_row["coverage"] == 1.0
    assert floor_crossing(summary, 0.2) == []


def test_recovery_runner_grades_a_wrong_backend_as_wrong() -> None:
    rows, ranks, _ = run_recovery(_noisy_fit, "noisy", [(0.9, True)], seeds=2, first_seed=60)
    assert not rows["covered"].any()
    summary = summarise(rows, ranks)
    assert floor_crossing(summary, 0.2) == ["rho 0.9, feedback on"]
    email = summary.filter(pl.col("channel") == "email").row(0, named=True)
    assert email["bias"] < 0  # true email return is above five
    assert email["seeds"] == 2
