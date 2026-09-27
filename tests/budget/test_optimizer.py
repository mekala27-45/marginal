from __future__ import annotations

import polars as pl
import pytest
from marginal_budget import (
    Constraints,
    compare,
    constraints_for,
    equal_split,
    evaluate,
    interior_test,
    last_year_mix,
    optimize,
    summarise_regret,
    truth_export,
)
from marginal_core.config import CHANNELS
from marginal_sim import MarketSpec, national_truth_table, simulate_market


@pytest.fixture(scope="module")
def truth() -> pl.DataFrame:
    _, national, market = simulate_market(MarketSpec(seed=8))
    return national_truth_table(national, market)


def test_truth_optimal_plan_beats_last_years_mix_on_the_true_curves(truth: pl.DataFrame) -> None:
    model = truth_export(truth)
    constraints = constraints_for(model)
    plan = optimize(model, constraints)
    _, plan_profit = evaluate(model, plan.spend)
    _, last_profit = evaluate(model, last_year_mix(model))
    _, equal_profit = evaluate(model, equal_split(model))
    assert plan_profit > last_profit
    assert plan_profit > equal_profit
    assert plan.starts == 8 and plan.starts_converged >= 1
    assert "success" in plan.solver_status.lower()


def test_marginal_returns_are_equal_across_interior_channels(truth: pl.DataFrame) -> None:
    model = truth_export(truth)
    plan = optimize(model, constraints_for(model))
    interior = [a for a in plan.allocation if a.at_bound == "interior"]
    assert len(interior) >= 2
    profits = [a.marginal_profit for a in interior]
    assert max(profits) - min(profits) <= 0.05
    assert plan.marginal_equalized
    assert tuple(plan.spend) == CHANNELS


def test_every_constraint_holds_and_the_hash_matches_its_inputs(truth: pl.DataFrame) -> None:
    model = truth_export(truth)
    constraints = constraints_for(model)
    plan = optimize(model, constraints)
    assert abs(sum(plan.spend.values()) - constraints.total_budget) < 1e-3 * constraints.total_budget
    for a in plan.allocation:
        assert a.spend >= a.last_year * (1.0 - constraints.max_change_share) - 1e-6
        assert a.spend <= a.last_year * (1.0 + constraints.max_change_share) + 1e-6
    again = optimize(model, constraints)
    assert again.inputs_hash == plan.inputs_hash
    other = optimize(model, constraints.model_copy(update={"max_change_share": 0.5}))
    assert other.inputs_hash != plan.inputs_hash


def test_the_allowance_constraint_binds_when_it_is_tight(truth: pl.DataFrame) -> None:
    model = truth_export(truth)
    loose = optimize(model, constraints_for(model))
    tight = optimize(
        model,
        constraints_for(model, allowance={"paid_search": 19.0}, revenue_per_acquisition=60.0),
    )
    search_loose = next(a for a in loose.allocation if a.channel == "paid_search")
    search_tight = next(a for a in tight.allocation if a.channel == "paid_search")
    assert search_tight.spend < search_loose.spend
    assert search_tight.at_bound == "allowance"
    assert search_tight.implied_acquisition_cost is not None


def test_an_impossible_budget_is_refused(truth: pl.DataFrame) -> None:
    model = truth_export(truth)
    with pytest.raises(ValueError, match="cannot satisfy"):
        optimize(model, Constraints(total_budget=1.0))


def test_interior_test_passes_on_the_optimum_and_fails_on_a_shifted_plan(truth: pl.DataFrame) -> None:
    model = truth_export(truth)
    constraints = constraints_for(model)
    plan = optimize(model, constraints)
    passed, reason = interior_test(model, constraints, plan)
    assert passed, reason
    interior = [a for a in plan.allocation if a.at_bound == "interior"]
    shifted = plan.model_copy(deep=True)
    a, b = interior[0], interior[1]
    moved = {x.channel: x.spend for x in shifted.allocation}
    moved[a.channel] -= 0.2 * a.spend
    moved[b.channel] += 0.2 * a.spend
    _, profit = evaluate(model, moved)
    shifted = shifted.model_copy(
        update={
            "allocation": [x.model_copy(update={"spend": moved[x.channel]}) for x in shifted.allocation],
            "expected_profit": profit,
        }
    )
    passed_shifted, _ = interior_test(model, constraints, shifted)
    assert not passed_shifted


def test_compare_and_summarise_regret_shapes(truth: pl.DataFrame) -> None:
    model = truth_export(truth)
    outcome = compare(model, model, constraints_for(model))
    assert outcome["share_captured"] == pytest.approx(1.0, abs=1e-6)
    assert outcome["regret"] == pytest.approx(0.0, abs=1e-3)
    rows = pl.DataFrame(
        [
            {"seed": 1, "backend": "own", "model": "uncalibrated", **outcome},
            {"seed": 2, "backend": "own", "model": "uncalibrated", **outcome},
            {"seed": 1, "backend": "own", "model": "calibrated", **outcome},
            {"seed": 2, "backend": "own", "model": "calibrated", **outcome},
        ]
    )
    summary = summarise_regret(rows)
    assert [s["model"] for s in summary] == ["uncalibrated", "calibrated"]
    assert summary[0]["beats_last_year_share"] == 1.0
