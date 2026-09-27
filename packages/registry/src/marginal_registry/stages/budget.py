"""Stage: the plan for the demonstration brand, the regret study and the precomputed surface.

Writes under results/budget:
  plan_calibrated.json, plan_uncalibrated.json, plan_truth.json   the three plans under the same constraints
  comparison.json        the plans evaluated on the true curves against last year's mix and an equal split
  regret_rows.parquet    per seed outcomes; regret_summary.parquet with intervals over seeds
  surface.parquet        the precomputed slider surface (budget grid, one constraint at a time)
  interior_test.json     the interior test on the allocation
and results/manifests/budget.json.
"""

from __future__ import annotations

import json
import os
import time

import polars as pl
from marginal_budget import Constraints, Plan, evaluate, interior_test, optimize
from marginal_budget.regret import (
    constraints_for,
    equal_split,
    last_year_mix,
    regret_study,
    summarise_regret,
    truth_export,
)
from marginal_core.config import CHANNEL_LABELS, POLICY
from marginal_core.manifest import Manifest, Scribe
from marginal_core.paths import Paths
from marginal_mmm import MMMSpec, ModelExport
from marginal_sim import condition_name, demonstration_spec


def _load_model(paths: Paths, name: str) -> ModelExport:
    return ModelExport.model_validate(json.loads((paths.results / name).read_text(encoding="utf-8")))


def run(paths: Paths, as_of: str, seed: int) -> Manifest:
    out = paths.results / "budget"
    out.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(as_of=as_of, seed=seed)
    condition = condition_name(0.6, True)
    truth_table = pl.read_parquet(paths.sim / "truth_channels.parquet")
    truth = truth_export(truth_table)
    uncalibrated = _load_model(paths, "mmm/own_model.json")
    calibrated_path = paths.results / "calibrate" / "own_calibrated_model.json"
    calibrated = (
        _load_model(paths, "calibrate/own_calibrated_model.json")
        if calibrated_path.exists()
        else uncalibrated
    )
    allowance, revenue_per_acquisition = _allowance(paths)
    constraints = constraints_for(truth, allowance=allowance, revenue_per_acquisition=revenue_per_acquisition)

    plans: dict[str, Plan] = {}
    for label, model in (("calibrated", calibrated), ("uncalibrated", uncalibrated), ("truth", truth)):
        plan = optimize(model, constraints, seed=seed)
        plans[label] = plan
        (out / f"plan_{label}.json").write_text(
            json.dumps({**plan.model_dump(mode="json"), "spend": plan.spend}, indent=1) + "\n"
        )

    # Every plan judged on the true curves.
    comparison: dict[str, dict[str, float]] = {}
    margin = constraints.margin
    _, last_profit = evaluate(truth, last_year_mix(truth), margin)
    _, equal_profit = evaluate(truth, equal_split(truth), margin)
    for label, plan in plans.items():
        revenue, profit = evaluate(truth, plan.spend, margin)
        comparison[label] = {
            "true_revenue": revenue,
            "true_profit": profit,
            "expected_profit": plan.expected_profit,
            "gain_over_last_year": profit - last_profit,
        }
    comparison["last_year"] = {"true_profit": last_profit, "gain_over_last_year": 0.0}
    comparison["equal_split"] = {
        "true_profit": equal_profit,
        "gain_over_last_year": equal_profit - last_profit,
    }
    gain_optimal = comparison["truth"]["gain_over_last_year"]
    captured = (
        comparison["calibrated"]["gain_over_last_year"] / gain_optimal if gain_optimal > 0 else float("nan")
    )
    captured_uncal = (
        comparison["uncalibrated"]["gain_over_last_year"] / gain_optimal if gain_optimal > 0 else float("nan")
    )
    (out / "comparison.json").write_text(json.dumps(comparison, indent=1, sort_keys=True) + "\n")

    passed, reason = interior_test(calibrated, constraints, plans["calibrated"])
    (out / "interior_test.json").write_text(
        json.dumps({"interior": passed, "reason": reason}, indent=1) + "\n"
    )

    # The regret study over the demonstration condition's seeds.
    seeds_env = os.environ.get("MARGINAL_REGRET_SEEDS")
    seeds = [1000 + i for i in range(int(seeds_env) if seeds_env else 10)]
    log = paths.logs / "budget.log"

    def progress(message: str) -> None:
        with log.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%H:%M:%S')} {message}\n")

    rows = regret_study(
        seeds, demonstration_spec(seed), lambda s: MMMSpec(backend="own", seed=s), progress=progress
    )
    rows.write_parquet(out / "regret_rows.parquet")
    summary = summarise_regret(rows, seed=seed)
    pl.DataFrame(summary).write_parquet(out / "regret_summary.parquet")

    surface = _surface(calibrated, constraints, seed)
    surface.write_parquet(out / "surface.parquet")

    _write_manifest(
        manifest,
        plans,
        comparison,
        captured,
        captured_uncal,
        passed,
        reason,
        summary,
        constraints,
        condition,
        surface,
        allowance is not None,
    )
    manifest.save(paths.results / "manifests" / "budget.json")
    return manifest


def _allowance(paths: Paths) -> tuple[dict[str, float] | None, float | None]:
    path = paths.results / "clv" / "allowance.json"
    if not path.exists():
        return None, None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(k): float(v) for k, v in payload["allowance_by_channel"].items()}, float(
        payload["revenue_per_acquisition"]
    )


def _surface(model: ModelExport, base: Constraints, seed: int) -> pl.DataFrame:
    """A grid over total budget at the stated constraints, and one constraint moved at a time."""
    total = base.total_budget
    rows = []
    grids: list[tuple[str, dict[str, float]]] = [("default", {})]
    for share in (0.15, 0.50):
        grids.append((f"max_change_{int(share * 100)}", {"max_change_share": share}))
    for label, override in grids:
        for step in range(-8, 9):
            budget = total * (1.0 + 0.05 * step)
            try:
                plan = optimize(
                    model, base.model_copy(update={"total_budget": budget, **override}), seed=seed
                )
            except (ValueError, RuntimeError):
                continue
            for a in plan.allocation:
                rows.append(
                    {
                        "surface": label,
                        "budget": budget,
                        "budget_share_of_last_year": 1.0 + 0.05 * step,
                        "channel": a.channel,
                        "spend": a.spend,
                        "expected_revenue": a.expected_revenue,
                        "at_bound": a.at_bound,
                        "expected_profit": plan.expected_profit,
                        "profit_lower": plan.profit_lower,
                        "profit_upper": plan.profit_upper,
                        "degenerate": plan.degenerate,
                        "labeled": "precomputed",
                    }
                )
    return pl.DataFrame(rows)


def _write_manifest(
    manifest: Manifest,
    plans: dict[str, Plan],
    comparison: dict[str, dict[str, float]],
    captured: float,
    captured_uncal: float,
    interior: bool,
    reason: str,
    summary: list[dict[str, float | str | int]],
    constraints: Constraints,
    condition: str,
    surface: pl.DataFrame,
    allowance: bool,
) -> None:
    w = Scribe(
        manifest,
        source="simulated",
        model="optimizer",
        population="demonstration brand, calibrated own curves",
        origin="marginal_budget.optimizer",
        condition=condition,
    )
    plan = plans["calibrated"]
    w.put("budget.total_weekly", constraints.total_budget, "usd0")
    w.put("budget.total_annual", constraints.total_budget * 52, "usd0")
    w.put("budget.margin", constraints.margin, "pct0")
    w.put("budget.max_change_share", constraints.max_change_share, "pct0")
    w.put("budget.allowance_applied", "yes" if allowance else "no", "text")
    w.put("budget.model_version", plan.model_version, "text")
    w.put("budget.inputs_hash", plan.inputs_hash, "text")
    w.put("budget.solver_status", plan.solver_status, "text")
    w.put("budget.starts", plan.starts, "int")
    w.put("budget.starts_converged", plan.starts_converged, "int")
    w.put("budget.marginal_equalized", "yes" if plan.marginal_equalized else "no", "text")
    w.put("budget.marginal_spread", plan.marginal_spread, "float3")
    w.put("budget.interior_channels", plan.interior_channels, "int")
    w.put("budget.interior", "interior" if interior else "degenerate", "text")
    w.put("budget.interior_reason", reason, "text")
    w.put("budget.expected_profit_weekly", plan.expected_profit, "usd0")
    w.put("budget.expected_profit_lower", plan.profit_lower, "usd0")
    w.put("budget.expected_profit_upper", plan.profit_upper, "usd0")
    w.put("budget.expected_revenue_weekly", plan.expected_revenue, "usd0")
    # The two headline numbers, on the demonstration brand, judged on the true curves.
    w.put(
        "budget.headline.gain_over_last_year_weekly", comparison["calibrated"]["gain_over_last_year"], "usd0"
    )
    w.put(
        "budget.headline.gain_over_last_year_annual",
        comparison["calibrated"]["gain_over_last_year"] * 52,
        "usd0",
    )
    w.put("budget.headline.gain_optimal_annual", comparison["truth"]["gain_over_last_year"] * 52, "usd0")
    w.put("budget.headline.share_captured", captured, "pct0")
    w.put("budget.headline.share_captured_uncalibrated", captured_uncal, "pct0")
    w.put(
        "budget.headline.equal_split_gain_annual",
        comparison["equal_split"]["gain_over_last_year"] * 52,
        "usd0",
    )
    w.put("budget.headline.last_year_profit_weekly", comparison["last_year"]["true_profit"], "usd0")
    for label in ("calibrated", "uncalibrated", "truth"):
        w.put(f"budget.{label}.true_profit_weekly", comparison[label]["true_profit"], "usd0")
        w.put(f"budget.{label}.expected_profit_weekly", comparison[label]["expected_profit"], "usd0")
    w.table(
        "budget.allocation",
        [
            "Channel",
            "Last year (weekly)",
            "Plan (weekly)",
            "Change",
            "Expected revenue",
            "Marginal return",
            "Marginal profit",
            "Bound",
        ],
        ["text", "usd0", "usd0", "spct1", "usd0", "float2", "spct1", "text"],
        [
            [
                CHANNEL_LABELS[a.channel],
                a.last_year,
                a.spend,
                a.change,
                a.expected_revenue,
                a.marginal_return,
                a.marginal_profit,
                a.at_bound,
            ]
            for a in plan.allocation
        ],
    )
    for a in plan.allocation:
        w.put(f"budget.plan.{a.channel}", a.spend, "usd0")
        w.put(f"budget.change.{a.channel}", a.change, "spct1")
        w.put(f"budget.bound.{a.channel}", a.at_bound, "text")
    w.table(
        "budget.comparison",
        ["Plan", "True weekly profit", "Gain over last year (weekly)", "Gain over last year (annual)"],
        ["text", "usd0", "usd0", "usd0"],
        [
            [
                "Calibrated model's plan",
                comparison["calibrated"]["true_profit"],
                comparison["calibrated"]["gain_over_last_year"],
                comparison["calibrated"]["gain_over_last_year"] * 52,
            ],
            [
                "Uncalibrated model's plan",
                comparison["uncalibrated"]["true_profit"],
                comparison["uncalibrated"]["gain_over_last_year"],
                comparison["uncalibrated"]["gain_over_last_year"] * 52,
            ],
            [
                "Truth optimal plan",
                comparison["truth"]["true_profit"],
                comparison["truth"]["gain_over_last_year"],
                comparison["truth"]["gain_over_last_year"] * 52,
            ],
            ["Last year's mix", comparison["last_year"]["true_profit"], 0.0, 0.0],
            [
                "Equal split",
                comparison["equal_split"]["true_profit"],
                comparison["equal_split"]["gain_over_last_year"],
                comparison["equal_split"]["gain_over_last_year"] * 52,
            ],
        ],
    )
    r = Scribe(
        manifest,
        source="simulated",
        model="optimizer",
        population="markets with known truth, demonstration condition",
        origin="marginal_budget.regret",
        condition=condition,
        seeds=int(summary[0]["seeds"]),
    )
    for s in summary:
        label = str(s["model"])
        r.put(f"budget.regret.{label}.seeds", int(s["seeds"]), "int")
        r.put(f"budget.regret.{label}.share_captured", s["share_captured"], "pct0")
        r.put(f"budget.regret.{label}.share_captured_lower", s["share_captured_lower"], "pct0")
        r.put(f"budget.regret.{label}.share_captured_upper", s["share_captured_upper"], "pct0")
        r.put(f"budget.regret.{label}.gain_weekly", s["gain_over_last_year"], "usd0")
        r.put(f"budget.regret.{label}.gain_lower", s["gain_lower"], "usd0")
        r.put(f"budget.regret.{label}.gain_upper", s["gain_upper"], "usd0")
        r.put(f"budget.regret.{label}.beats_last_year", s["beats_last_year_share"], "pct0")
        r.put(f"budget.regret.{label}.optimal_gain_mean", s["optimal_gain_mean"], "usd0")
        r.put(f"budget.regret.{label}.equal_split_gain_mean", s["equal_split_gain_mean"], "usd0")
    r.table(
        "budget.regret",
        [
            "Model",
            "Seeds",
            "Share of optimal gain captured",
            "Lower",
            "Upper",
            "Gain over last year (weekly)",
            "Lower",
            "Upper",
            "Beats last year",
        ],
        ["text", "int", "pct0", "pct0", "pct0", "usd0", "usd0", "usd0", "pct0"],
        [
            [
                str(s["model"]),
                int(s["seeds"]),
                s["share_captured"],
                s["share_captured_lower"],
                s["share_captured_upper"],
                s["gain_over_last_year"],
                s["gain_lower"],
                s["gain_upper"],
                s["beats_last_year_share"],
            ]
            for s in summary
        ],
    )
    w.put("budget.surface.points", surface.filter(pl.col("channel") == "paid_search").height, "int")
    w.put("budget.surface.budget_min", float(surface["budget"].min()), "usd0")  # type: ignore[arg-type]
    w.put("budget.surface.budget_max", float(surface["budget"].max()), "usd0")  # type: ignore[arg-type]
    w.put("budget.level", POLICY.interval_level, "pct0")
