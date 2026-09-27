from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pytest
from marginal_experiments import (
    analyse,
    design_test,
    difference_in_differences,
    email_design,
    intervention_for,
    power_curve,
    srm_gate,
    stratified_assignment,
    synthetic_control,
    true_lift,
)
from marginal_registry.client import Registry
from marginal_sim import MarketSpec, simulate_market

# The SRM gate: three tests.


def test_srm_gate_passes_a_balanced_assignment() -> None:
    result = srm_gate({"a": 10_000, "b": 10_050}, {"a": 0.5, "b": 0.5})
    assert result.passed and result.p_value > 0.5


def test_srm_gate_rejects_a_deliberately_imbalanced_assignment() -> None:
    result = srm_gate({"a": 10_000, "b": 9_000}, {"a": 0.5, "b": 0.5})
    assert not result.passed and result.p_value < 1e-6


def test_srm_gate_refuses_to_pass_on_an_empty_assignment() -> None:
    with pytest.raises(ValueError, match="empty"):
        srm_gate({"a": 0, "b": 0}, {"a": 0.5, "b": 0.5})
    with pytest.raises(ValueError, match="differ"):
        srm_gate({"a": 5}, {"a": 0.5, "b": 0.5})


# Design and registration.


def test_stratified_assignment_spans_the_size_distribution() -> None:
    pre = {g: float(1000 + 100 * g) for g in range(40)}
    treated, control = stratified_assignment(pre, 10, seed=1)
    assert len(treated) == 10 and len(control) == 30 and not set(treated) & set(control)
    assert min(treated) < 8 and max(treated) > 31
    assert stratified_assignment(pre, 10, seed=1) == (treated, control)
    with pytest.raises(ValueError):
        stratified_assignment(pre, 40, seed=1)


def test_changing_the_design_changes_the_plan_hash() -> None:
    geo, _, _ = simulate_market(MarketSpec(seed=2))
    design = design_test(geo, seed=2)
    other = design.model_copy(update={"end_week": design.end_week - 1})
    assert design.plan_hash != other.plan_hash
    assert design.model_copy().plan_hash == design.plan_hash


# Analysis against known truth.


@pytest.fixture(scope="module")
def tested_market() -> tuple[MarketSpec, pl.DataFrame, object]:
    base = MarketSpec(seed=21, spend_correlation=0.6, demand_feedback=True)
    geo, _, _ = simulate_market(base)
    design = design_test(geo, seed=21)
    tested = base.model_copy(update={"intervention": intervention_for(design)})
    geo_after, _, _ = simulate_market(tested)
    return base, geo_after, design


def test_difference_in_differences_recovers_the_planted_lift(
    tested_market: tuple[MarketSpec, pl.DataFrame, object],
) -> None:
    base, geo_after, design = tested_market
    truth = true_lift(base, design)  # type: ignore[arg-type]
    result = difference_in_differences(geo_after, design)  # type: ignore[arg-type]
    assert truth > 0
    assert abs(result.incremental_revenue / truth - 1.0) < 0.35
    assert result.lower < result.upper
    assert result.weeks_used == design.pre_period_weeks + design.window_weeks  # type: ignore[attr-defined]


def test_synthetic_control_runs_every_permutation_and_recovers_the_lift(
    tested_market: tuple[MarketSpec, pl.DataFrame, object],
) -> None:
    base, geo_after, design = tested_market
    small = design.model_copy(update={"placebo_permutations": 50})  # type: ignore[attr-defined]
    result = synthetic_control(geo_after, small, seed=21)
    truth = true_lift(base, small)
    assert result.placebo_permutations == 50
    assert len(result.placebo_effects) == 50
    assert result.lower <= result.incremental_revenue <= result.upper
    assert abs(result.incremental_revenue / truth - 1.0) < 0.35
    assert result.p_value <= 0.1
    assert abs(sum(result.weights.values())) > 0


def test_a_null_test_finds_nothing(tested_market: tuple[MarketSpec, pl.DataFrame, object]) -> None:
    base, _, design = tested_market
    geo_null, _, _ = simulate_market(base)
    result = difference_in_differences(geo_null, design)  # type: ignore[arg-type]
    assert result.lower < 0 < result.upper


def test_power_curve_rises_with_effect_and_length() -> None:
    base = MarketSpec(seed=31)
    geo, _, _ = simulate_market(base)
    design = design_test(geo, seed=31)
    cells = power_curve(base, design, spend_multipliers=(0.0, 0.9), window_lengths=(2, 8), simulations=6)
    assert len(cells) == 4
    by = {(c.spend_multiplier, c.window_weeks): c for c in cells}
    assert by[(0.0, 8)].power >= by[(0.9, 8)].power
    assert all(c.simulations == 6 for c in cells)


# The email experiment.


def _email_frame(n: int = 60_000, effect: float = 0.02, seed: int = 3) -> pl.DataFrame:
    r = np.random.default_rng(seed)
    arms = r.choice(["control", "mens", "womens"], size=n)
    segment = r.choice(["1) $0 - $100", "2) $100 - $200", "3) $200 - $350"], size=n)
    base = r.random(n) < 0.05
    lifted = r.random(n) < (0.05 + effect)
    conversion = np.where(arms == "mens", lifted, base).astype(int)
    visit = np.where(arms == "control", r.random(n) < 0.10, r.random(n) < 0.15).astype(int)
    spend = conversion * r.gamma(2.0, 40.0, n)
    return pl.DataFrame(
        {"arm": arms, "history_segment": segment, "visit": visit, "conversion": conversion, "spend": spend}
    )


def test_email_analysis_finds_the_planted_effect_and_corrects_segments() -> None:
    analysis = analyse(_email_frame())
    assert analysis.srm.passed
    mens = next(e for e in analysis.effects if e.arm == "mens" and e.outcome == "conversion")
    assert mens.effect == pytest.approx(0.02, abs=0.008)
    assert mens.lower > 0
    womens = next(e for e in analysis.effects if e.arm == "womens" and e.outcome == "conversion")
    assert womens.lower < 0 < womens.upper
    families = {(s.arm, s.outcome) for s in analysis.segments}
    assert ("mens", "conversion") in families
    for s in analysis.segments:
        assert s.p_adjusted >= s.p_value
    assert "mens" in analysis.incremental_profit_per_email


def test_email_analysis_refuses_when_the_srm_gate_fails() -> None:
    frame = _email_frame().filter(~((pl.col("arm") == "mens") & (pl.col("visit") == 1)))
    with pytest.raises(ValueError, match="SRM gate failed"):
        analyse(frame)


def test_email_design_hash_is_stable() -> None:
    assert email_design().plan_hash == email_design().plan_hash


# The registry client falls back to a local record when the API is unreachable.


def test_registry_registers_locally_without_an_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MARGINAL_API_BASE", raising=False)
    registry = Registry(tmp_path / "registry.json")
    record = registry.register("test", "geo_lift", "abcd1234abcd1234", {"x": 1})
    assert record.registered_via == "local"
    assert registry.experiments()[0]["plan_hash"] == "abcd1234abcd1234"
    again = registry.register("test", "geo_lift", "abcd1234abcd1234", {"x": 1})
    assert again.experiment_id == record.experiment_id
    assert len(registry.experiments()) == 1


def test_registry_records_the_route_when_the_api_does_not_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MARGINAL_API_BASE", "http://127.0.0.1:9")
    registry = Registry(tmp_path / "registry.json")
    record = registry.register("test", "email", "ffff0000ffff0000", {})
    assert record.registered_via == "local"
