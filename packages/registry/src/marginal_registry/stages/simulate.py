"""Stage: the market with known truth for the demonstration seed.

Writes, under data/sim:
  geo_panel.parquet         geo by week: sales, spend per channel, the true baseline and contributions
  national.parquet          the week level panel the mix models fit, with the truth beside it
  truth_channels.parquet    per channel: the true parameters, last year's spend and return, marginal return
  customers_truth.parquet   200,000 customers: features, both potential outcomes, the true effect,
                            the quadrant, and both assignments (the coin and the sure things policy);
                            marginal_sim.customers.randomized_view and policy_view give what an
                            analyst is allowed to see
  paths.parquet             every touch with its true incremental credit
  path_users.parquet        every user's intent, conversion probability and outcome
  market.json               the spec and the truth parameters
"""

from __future__ import annotations

import json

import polars as pl
from marginal_core.config import CHANNEL_LABELS, CHANNELS
from marginal_core.frames import mean
from marginal_core.frames import share as share_of
from marginal_core.manifest import Manifest, Scribe
from marginal_core.paths import Paths
from marginal_sim import (
    CustomerSpec,
    PathSpec,
    demonstration_spec,
    national_truth_table,
    quadrant_shares,
    simulate_customers,
    simulate_market,
    simulate_paths,
    true_incremental_share,
)


def run(paths: Paths, as_of: str, seed: int) -> Manifest:
    out = paths.sim
    out.mkdir(parents=True, exist_ok=True)
    spec = demonstration_spec(seed)
    geo, national, market = simulate_market(spec)
    truth = national_truth_table(national, market)
    geo.write_parquet(out / "geo_panel.parquet")
    national.write_parquet(out / "national.parquet")
    truth.write_parquet(out / "truth_channels.parquet")
    (out / "market.json").write_text(
        json.dumps(market.model_dump(mode="json"), indent=1, sort_keys=True) + "\n"
    )

    randomized, _policy, customers_truth = simulate_customers(CustomerSpec(seed=seed))
    customers_truth.write_parquet(out / "customers_truth.parquet")

    touches, users = simulate_paths(PathSpec(seed=seed))
    touches.write_parquet(out / "paths.parquet")
    users.write_parquet(out / "path_users.parquet")

    manifest = Manifest(as_of=as_of, seed=seed)
    w = Scribe(
        manifest,
        source="simulated",
        population=f"{spec.geos} geos, {spec.weeks} weeks, demonstration seed",
        origin="marginal_sim.market",
        condition=spec.condition,
    )
    w.put("sim.geos", spec.geos, "int")
    w.put("sim.weeks", spec.weeks, "int")
    w.put("sim.first_week", str(spec.first_week), "text")
    w.put("sim.last_week", str(market.week_dates[-1]), "text")
    w.put("sim.condition", spec.condition, "text")
    w.put("sim.spend_correlation_target", spec.spend_correlation, "float1")
    w.put("sim.spend_correlation_achieved", market.achieved_spend_correlation, "float2")
    w.put("sim.feedback_coefficient", spec.feedback_coefficient, "float1")
    total_sales = float(national["sales"].sum())
    total_baseline = float(national["baseline_true"].sum())
    total_inc = sum(float(national[f"incremental_true_{c}"].sum()) for c in CHANNELS)
    total_spend = sum(float(national[f"spend_{c}"].sum()) for c in CHANNELS)
    w.put("sim.sales_weekly_mean", total_sales / spec.weeks, "usd0")
    w.put("sim.baseline_share", total_baseline / total_sales, "pct1")
    w.put("sim.incremental_share", total_inc / total_sales, "pct1")
    w.put("sim.spend_weekly_mean", total_spend / spec.weeks, "usd0")
    w.put("sim.roas_blended", total_inc / total_spend, "float2")
    rows = []
    for r in truth.iter_rows(named=True):
        rows.append(
            [
                CHANNEL_LABELS[str(r["channel"])],
                r["spend_last_year"],
                r["roas_true"],
                r["marginal_return_true"],
                r["carryover"],
                r["half_life_weeks"],
                r["half_saturation"],
                r["slope"],
            ]
        )
        key = str(r["channel"])
        w.put(f"sim.truth.roas.{key}", r["roas_true"], "float2")
        w.put(f"sim.truth.marginal.{key}", r["marginal_return_true"], "float2")
        w.put(f"sim.truth.carryover.{key}", r["carryover"], "float2")
        w.put(f"sim.truth.half_life.{key}", r["half_life_weeks"], "float1")
        w.put(f"sim.truth.spend_last_year.{key}", r["spend_last_year"], "usd0")
        w.put(f"sim.truth.weekly_spend_current.{key}", r["weekly_spend_current"], "usd0")
    w.table(
        "sim.truth_channels",
        [
            "Channel",
            "Spend last year",
            "True return",
            "True marginal return",
            "Carryover",
            "Half life (weeks)",
            "Half saturation",
            "Slope",
        ],
        ["text", "usd0", "float2", "float2", "float2", "float1", "usd0", "float1"],
        rows,
    )

    c = Scribe(
        manifest,
        source="simulated",
        population=f"{randomized.height:,} customers, demonstration seed",
        origin="marginal_sim.customers",
    )
    shares = quadrant_shares(customers_truth)
    c.put("sim.customers", randomized.height, "int")
    for name, share in shares.items():
        c.put(f"sim.quadrant.{name}", share, "pct1")
    c.put("sim.customers.ate_true", mean(customers_truth, "tau_true"), "pct2")
    c.put("sim.customers.p0_mean", mean(customers_truth, "p0_true"), "pct2")
    c.put("sim.customers.negative_effect_share", share_of(customers_truth, pl.col("tau_true") < 0), "pct1")
    c.put("sim.customers.policy_contact_share", CustomerSpec(seed=seed).policy_contact_share, "pct0")

    p = Scribe(
        manifest,
        source="simulated",
        population=f"{users.height:,} user paths, demonstration seed",
        origin="marginal_sim.paths",
    )
    shares_frame = true_incremental_share(touches)
    p.put("sim.paths.users", users.height, "int")
    p.put("sim.paths.touches", touches.height, "int")
    p.put("sim.paths.conversion_rate", mean(users, "converted"), "pct1")
    p.put("sim.paths.mean_touches", mean(users, "touches"), "float1")
    for r in shares_frame.iter_rows(named=True):
        p.put(f"sim.paths.share_true.{r['channel']}", r["share_true"], "pct1")

    manifest.save(paths.results / "manifests" / "simulate.json")
    return manifest
