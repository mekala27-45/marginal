"""Stage: the geo lift test on the simulator and the email experiment on Hillstrom.

The geo test follows the order a measurement team follows: design from the pre period,
power by simulation, registration of the plan hash, only then the test's data, the SRM
gate, the analysis, and the result posted against the hash. Writes under results/experiments:
  geo_design.json, geo_power.parquet, geo_result.json, geo_placebo.parquet,
  geo_series.parquet (treated aggregate against its synthetic control by week),
  registry.json (registrations and posted results, with the route each took),
  email_effects.parquet, email_segments.parquet, email_analysis.json
  and results/manifests/experiments.json.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import polars as pl
from marginal_contracts import hillstrom, source
from marginal_core.config import CHANNEL_LABELS, POLICY
from marginal_core.manifest import Manifest, Scribe
from marginal_core.paths import Paths
from marginal_experiments import (
    analyse,
    design_test,
    difference_in_differences,
    email_design,
    intervention_for,
    power_curve,
    srm_gate,
    synthetic_control,
    true_lift,
)
from marginal_experiments.registration import ResultRecord
from marginal_sim import demonstration_spec, simulate_market

from marginal_registry.client import Registry


def _now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def run(paths: Paths, as_of: str, seed: int) -> Manifest:
    out = paths.results / "experiments"
    out.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(as_of=as_of, seed=seed)
    registry = Registry(out / "registry.json")
    _geo_lift(paths, out, manifest, registry, seed)
    _email(paths, out, manifest, registry)
    manifest.save(paths.results / "manifests" / "experiments.json")
    return manifest


def _geo_lift(paths: Paths, out: Path, manifest: Manifest, registry: Registry, seed: int) -> None:
    base = demonstration_spec(seed)
    geo_before, _, _ = simulate_market(base)
    design = design_test(geo_before, seed=seed)

    # Power, then the registered plan carries the power at the true effect.
    cells = power_curve(base, design)
    at_truth = next(
        c
        for c in cells
        if c.spend_multiplier == 1.0 + design.spend_change and c.window_weeks == design.window_weeks
    )
    design = design.model_copy(update={"power_at_true_effect": at_truth.power})
    pl.DataFrame([c.model_dump() for c in cells]).write_parquet(out / "geo_power.parquet")

    record = registry.register(design.name, "geo_lift", design.plan_hash, design.model_dump(mode="json"))
    (out / "geo_design.json").write_text(
        json.dumps(
            {
                "design": design.model_dump(mode="json"),
                "plan_hash": design.plan_hash,
                "registration": record.model_dump(mode="json"),
            },
            indent=1,
            sort_keys=True,
        )
        + "\n"
    )

    # Only now does the test's data exist.
    tested = base.model_copy(update={"intervention": intervention_for(design)})
    geo_after, _, _ = simulate_market(tested)
    srm = srm_gate(
        {"treated": len(design.treated_geos), "control": len(design.control_geos)},
        {"treated": len(design.treated_geos) / base.geos, "control": len(design.control_geos) / base.geos},
    )
    if not srm.passed:
        raise ValueError("the geo assignment failed the SRM gate")
    did = difference_in_differences(geo_after, design)
    sc = synthetic_control(geo_after, design, seed)
    truth = true_lift(base, design)

    posted = {}
    for method, est in (
        ("did", (did.incremental_revenue, did.standard_error, did.lower, did.upper)),
        ("synthetic_control", (sc.incremental_revenue, (sc.upper - sc.lower) / 3.29, sc.lower, sc.upper)),
    ):
        result = ResultRecord(
            experiment_id=record.experiment_id,
            plan_hash=design.plan_hash,
            method=method,
            channel=design.channel,
            incremental_revenue=est[0],
            standard_error=est[1],
            lower=est[2],
            upper=est[3],
            level=design.interval_level,
            geos=design.treated_geos,
            start_week=design.start_week,
            end_week=design.end_week,
            posted_at=_now(),
            truth=truth,
        )
        posted[method] = registry.post_result(result)

    (out / "geo_result.json").write_text(
        json.dumps(
            {
                "srm": srm.model_dump(),
                "did": did.model_dump(),
                "synthetic_control": {k: v for k, v in sc.model_dump().items() if k != "placebo_effects"},
                "truth": truth,
                "posted_via": posted,
                "experiment_id": record.experiment_id,
                "plan_hash": design.plan_hash,
            },
            indent=1,
            sort_keys=True,
        )
        + "\n"
    )
    pl.DataFrame({"placebo_effect": sc.placebo_effects}).write_parquet(out / "geo_placebo.parquet")

    # The treated aggregate against its synthetic control, week by week, for the chart.
    frame = geo_after.filter(pl.col("week") >= design.start_week - design.pre_period_weeks)
    treated = (
        frame.filter(pl.col("geo").is_in(list(design.treated_geos)))
        .group_by("week")
        .agg(pl.col("sales").sum().alias("treated"))
        .sort("week")
    )
    controls = (
        frame.filter(pl.col("geo").is_in(list(design.control_geos)))
        .pivot(on="geo", index="week", values="sales")
        .sort("week")
    )
    synthetic = np.zeros(controls.height)
    for g, weight in sc.weights.items():
        synthetic = synthetic + controls[str(g)].to_numpy() * weight
    series = treated.with_columns(pl.Series("synthetic", synthetic)).with_columns(
        (pl.col("week") >= design.start_week).alias("in_window")
    )
    series.write_parquet(out / "geo_series.parquet")

    w = Scribe(
        manifest,
        source="simulated",
        model="did",
        population=f"{len(design.treated_geos)} treated geos of {base.geos}, {design.window_weeks} weeks",
        origin="marginal_experiments.geo_lift",
        condition=base.condition,
    )
    w.put("geo.channel", CHANNEL_LABELS[design.channel], "text")
    w.put("geo.spend_change", design.spend_change, "spct1")
    w.put("geo.treated_geos", len(design.treated_geos), "int")
    w.put("geo.control_geos", len(design.control_geos), "int")
    w.put("geo.treated_geo_ids", ", ".join(str(g) for g in design.treated_geos), "text")
    w.put("geo.window_weeks", design.window_weeks, "int")
    w.put("geo.pre_period_weeks", design.pre_period_weeks, "int")
    w.put("geo.start_week", design.start_week, "int")
    w.put("geo.end_week", design.end_week, "int")
    w.put("geo.plan_hash", design.plan_hash, "text")
    w.put("geo.experiment_id", record.experiment_id, "text")
    w.put("geo.registered_at", record.registered_at, "text")
    w.put("geo.registered_via", record.registered_via, "text")
    w.put("geo.result_posted_via", posted["did"], "text")
    w.put("geo.srm_p", srm.p_value, "float3")
    w.put("geo.srm_passed", "passed" if srm.passed else "failed", "text")
    w.put("geo.power_at_true_effect", at_truth.power, "pct0")
    w.put("geo.power_simulations", at_truth.simulations, "int")
    w.put("geo.truth", truth, "usd0")
    w.put("geo.did.estimate", did.incremental_revenue, "usd0")
    w.put("geo.did.lower", did.lower, "usd0")
    w.put("geo.did.upper", did.upper, "usd0")
    w.put("geo.did.standard_error", did.standard_error, "usd0")
    w.put("geo.did.delta_log", did.delta_log, "float4")
    w.put("geo.did.covers_truth", "yes" if did.lower <= truth <= did.upper else "no", "text")
    w.put("geo.did.error", did.incremental_revenue / truth - 1.0, "spct1")
    s = Scribe(
        manifest,
        source="simulated",
        model="synthetic_control",
        population=f"{len(design.treated_geos)} treated geos of {base.geos}, {design.window_weeks} weeks",
        origin="marginal_experiments.geo_lift",
        condition=base.condition,
    )
    s.put("geo.sc.estimate", sc.incremental_revenue, "usd0")
    s.put("geo.sc.lower", sc.lower, "usd0")
    s.put("geo.sc.upper", sc.upper, "usd0")
    s.put("geo.sc.p_value", sc.p_value, "float3")
    s.put("geo.sc.placebo_permutations", sc.placebo_permutations, "int")
    s.put("geo.sc.largest_weight", sc.largest_weight, "pct0")
    s.put("geo.sc.pre_period_rmse", sc.pre_period_rmse, "usd0")
    s.put("geo.sc.covers_truth", "yes" if sc.lower <= truth <= sc.upper else "no", "text")
    s.put("geo.sc.error", sc.incremental_revenue / truth - 1.0, "spct1")
    w.table(
        "geo.power",
        ["Spend removed", "Test length (weeks)", "Simulations", "Power", "Mean true lift"],
        ["pct0", "int", "int", "pct0", "usd0"],
        [[1.0 - c.spend_multiplier, c.window_weeks, c.simulations, c.power, c.mean_true_lift] for c in cells],
    )
    w.table(
        "geo.estimates",
        ["Method", "Estimate", "Lower", "Upper", "Truth (simulated)", "Covers", "Error"],
        ["text", "usd0", "usd0", "usd0", "usd0", "text", "spct1"],
        [
            [
                "Difference in differences",
                did.incremental_revenue,
                did.lower,
                did.upper,
                truth,
                "yes" if did.lower <= truth <= did.upper else "no",
                did.incremental_revenue / truth - 1.0,
            ],
            [
                "Synthetic control",
                sc.incremental_revenue,
                sc.lower,
                sc.upper,
                truth,
                "yes" if sc.lower <= truth <= sc.upper else "no",
                sc.incremental_revenue / truth - 1.0,
            ],
        ],
    )


def _email(paths: Paths, out: Path, manifest: Manifest, registry: Registry) -> None:
    frame = hillstrom.load(paths.external / source("hillstrom").filename)
    design = email_design()
    record = registry.register(design.name, "email", design.plan_hash, design.model_dump(mode="json"))
    analysis = analyse(frame, design)
    effects = pl.DataFrame([e.model_dump() for e in analysis.effects])
    segments = pl.DataFrame([s.model_dump() for s in analysis.segments])
    effects.write_parquet(out / "email_effects.parquet")
    segments.write_parquet(out / "email_segments.parquet")
    (out / "email_analysis.json").write_text(
        json.dumps(
            {k: v for k, v in analysis.model_dump().items() if k not in ("effects", "segments")}
            | {"registration": record.model_dump(mode="json")},
            indent=1,
            sort_keys=True,
            default=str,
        )
        + "\n"
    )
    w = Scribe(
        manifest,
        source="real:hillstrom",
        population="64,000 recent buyers, three arms",
        origin="marginal_experiments.email",
    )
    w.put("email.plan_hash", design.plan_hash, "text")
    w.put("email.registered_via", record.registered_via, "text")
    w.put("email.srm_p", analysis.srm.p_value, "float3")
    w.put("email.srm_passed", "passed" if analysis.srm.passed else "failed", "text")
    for arm, count in analysis.srm.observed.items():
        w.put(f"email.arm.{arm}", count, "int")
    for e in analysis.effects:
        fmt = "usd2" if e.outcome == "spend" else "pct2"
        w.put(f"email.{e.arm}.{e.outcome}.effect", e.effect, fmt)
        w.put(f"email.{e.arm}.{e.outcome}.lower", e.lower, fmt)
        w.put(f"email.{e.arm}.{e.outcome}.upper", e.upper, fmt)
        w.put(f"email.{e.arm}.{e.outcome}.control", e.control_mean, fmt)
        w.put(f"email.{e.arm}.{e.outcome}.treated", e.treated_mean, fmt)
    for arm in ("mens", "womens"):
        w.put(f"email.{arm}.revenue_per_email", analysis.incremental_revenue_per_email[arm], "usd2")
        w.put(f"email.{arm}.profit_per_email", analysis.incremental_profit_per_email[arm], "usd2")
    w.put("email.cost_per_email", analysis.cost_per_email, "usd2")
    w.put("email.margin_on_spend", analysis.margin_on_spend, "pct0")
    w.table(
        "email.effects",
        ["Arm", "Outcome", "No email", "Email", "Effect", "Lower", "Upper"],
        ["text", "text", "float4", "float4", "float4", "float4", "float4"],
        [
            [e.arm, e.outcome, e.control_mean, e.treated_mean, e.effect, e.lower, e.upper]
            for e in analysis.effects
        ],
    )
    conv = [s for s in analysis.segments if s.arm == "mens" and s.outcome == "conversion"]
    w.table(
        "email.segments.mens.conversion",
        ["History segment", "Effect", "Lower", "Upper", "p", "p adjusted", "Significant"],
        ["text", "pct2", "pct2", "pct2", "float3", "float3", "text"],
        [
            [s.segment, s.effect, s.lower, s.upper, s.p_value, s.p_adjusted, "yes" if s.significant else "no"]
            for s in conv
        ],
    )
    w.put("email.segments.mens.conversion.significant", sum(s.significant for s in conv), "int")
    w.put("email.segments.mens.conversion.count", len(conv), "int")
    spend = [s for s in analysis.segments if s.arm == "mens" and s.outcome == "spend"]
    w.put("email.segments.mens.spend.significant", sum(s.significant for s in spend), "int")
    w.put("email.segments.correction", design.correction, "text")
    w.put("email.window_days", design.outcome_window_days, "int")
    w.put("email.level", POLICY.interval_level, "pct0")
