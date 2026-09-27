"""The regret study: what a plan built on the estimated curves earns when the true curves are the
judge, against the plan built on the truth, last year's mix and an equal split.

For each seed of the demonstration condition the market is simulated, the geo test is run on
it, the backend is fit before and after calibration, each fit's plan is optimized under the
stated constraints, and every plan is evaluated on that market's true curves. The share of the
truth optimal gain captured is the headline: how much of what was there to win the model found.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import polars as pl
from marginal_core.config import CHANNELS, POLICY
from marginal_evaluation import bootstrap_interval, observed
from marginal_experiments import design_test, difference_in_differences, intervention_for
from marginal_mmm import CurveParams, LiftResult, MMMSpec, ModelExport, export_model, fit
from marginal_sim import MarketSpec, national_truth_table, simulate_market

from marginal_budget.optimizer import Constraints, evaluate, optimize


def truth_export(truth: pl.DataFrame, version: str = "truth") -> ModelExport:
    """The simulator's true response curves in the same record the optimizer reads."""
    channels = []
    for r in truth.iter_rows(named=True):
        channels.append(
            CurveParams(
                channel=str(r["channel"]),
                ceiling=float(r["ceiling"]),
                half_saturation=float(r["half_saturation"]),
                slope=float(r["slope"]),
                carryover=float(r["carryover"]),
                weekly_spend_current=float(r["weekly_spend_current"]),
                spend_last_year=float(r["spend_last_year"]),
                ceiling_draws=[],
            )
        )
    return ModelExport(
        backend="truth",
        spec_hash="truth",
        data_source="simulated",
        calibrated=False,
        version=version,
        channels=channels,
    )


def last_year_mix(model: ModelExport) -> dict[str, float]:
    return {c.channel: c.weekly_spend_current for c in model.channels}


def equal_split(model: ModelExport) -> dict[str, float]:
    total = sum(c.weekly_spend_current for c in model.channels)
    return {c.channel: total / len(model.channels) for c in model.channels}


def constraints_for(
    model: ModelExport,
    *,
    allowance: dict[str, float] | None = None,
    revenue_per_acquisition: float | None = None,
) -> Constraints:
    total = sum(c.weekly_spend_current for c in model.channels)
    return Constraints(
        total_budget=total, allowance=allowance, revenue_per_acquisition=revenue_per_acquisition
    )


def compare(model: ModelExport, truth: ModelExport, constraints: Constraints) -> dict[str, float]:
    """Profit on the true curves of: the model's plan, the truth optimal plan under the same
    constraints, last year's mix and an equal split (the equal split ignores the change limit,
    which is the point of showing it)."""
    plan = optimize(model, constraints)
    optimal = optimize(truth, constraints)
    _, plan_profit = evaluate(truth, plan.spend, constraints.margin)
    _, optimal_profit = evaluate(truth, optimal.spend, constraints.margin)
    _, last_profit = evaluate(truth, last_year_mix(truth), constraints.margin)
    _, equal_profit = evaluate(truth, equal_split(truth), constraints.margin)
    gain_plan = plan_profit - last_profit
    gain_optimal = optimal_profit - last_profit
    return {
        "plan_profit": plan_profit,
        "optimal_profit": optimal_profit,
        "last_year_profit": last_profit,
        "equal_split_profit": equal_profit,
        "gain_plan": gain_plan,
        "gain_optimal": gain_optimal,
        "share_captured": gain_plan / gain_optimal if gain_optimal > 0 else float("nan"),
        "model_expected_profit": plan.expected_profit,
        "regret": optimal_profit - plan_profit,
    }


def regret_study(
    seeds: list[int],
    base: MarketSpec,
    spec_for: Callable[[int], MMMSpec],
    *,
    progress: Callable[[str], None] | None = None,
) -> pl.DataFrame:
    rows = []
    for seed in seeds:
        spec = base.model_copy(update={"seed": seed, "intervention": None})
        geo, national, market = simulate_market(spec)
        truth_table = national_truth_table(national, market)
        truth = truth_export(truth_table)
        design = design_test(geo, seed=seed)
        tested = spec.model_copy(update={"intervention": intervention_for(design)})
        geo_after, national_after, _ = simulate_market(tested)
        did = difference_in_differences(geo_after, design)
        weights = geo.filter(pl.col("week") == 0).select(["geo", "geo_weight"])
        geo_share = float(weights.filter(pl.col("geo").is_in(list(design.treated_geos)))["geo_weight"].sum())
        lift = LiftResult(
            channel=design.channel,
            window_start_week=design.start_week,
            window_end_week=design.end_week,
            geo_share=geo_share,
            incremental_revenue=did.incremental_revenue,
            standard_error=did.standard_error,
            spend_change=design.spend_change,
            experiment_id=f"seed-{seed}",
            plan_hash=design.plan_hash,
        )
        model = fit(observed(national_after), spec_for(seed))
        calibrated = model.calibrate([lift])
        constraints = constraints_for(truth)
        for label, m in (("uncalibrated", model), ("calibrated", calibrated)):
            export = export_model(m, version=f"{m.backend}-{label}")
            outcome = compare(export, truth, constraints)
            rows.append({"seed": seed, "backend": m.backend, "model": label, **outcome})
            if progress:
                progress(f"regret seed {seed} {label}: captured {outcome['share_captured']:.2f}")
    return pl.DataFrame(rows)


def summarise_regret(
    rows: pl.DataFrame, level: float = POLICY.interval_level, seed: int = 0
) -> list[dict[str, float | str | int]]:
    out: list[dict[str, float | str | int]] = []
    for label in ("uncalibrated", "calibrated"):
        sub = rows.filter(pl.col("model") == label).sort("seed")
        captured = sub["share_captured"].drop_nans().to_numpy()
        gain = sub["gain_plan"].to_numpy()
        gain_optimal = sub["gain_optimal"].to_numpy()
        c = bootstrap_interval(captured, level=level, seed=seed, stream=f"captured {label}")
        g = bootstrap_interval(gain, level=level, seed=seed, stream=f"gain {label}")
        beats_last_year = float(np.mean(gain > 0))
        out.append(
            {
                "model": label,
                "seeds": int(sub.height),
                "share_captured": c.estimate,
                "share_captured_lower": c.lower,
                "share_captured_upper": c.upper,
                "gain_over_last_year": g.estimate,
                "gain_lower": g.lower,
                "gain_upper": g.upper,
                "optimal_gain_mean": float(np.mean(gain_optimal)),
                "beats_last_year_share": beats_last_year,
                "equal_split_gain_mean": float(
                    np.mean(sub["equal_split_profit"].to_numpy() - sub["last_year_profit"].to_numpy())
                ),
            }
        )
    return out


def channel_order_check(plan_spend: dict[str, float]) -> bool:
    return tuple(plan_spend) == CHANNELS
