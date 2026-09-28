"""Stage: lifetime value on the Online Retail II purchase history, judged on a holdout, and the
acquisition cost allowance the budget optimizer and the API read.

The history is split where marginal_contracts.retail splits it: calibration to 30 November 2010,
holdout from 1 December 2010 to the end of the file. BG/NBD and Gamma-Gamma, both written in
marginal_clv, are fit on the calibration window, predict each calibration customer's purchase
days and revenue over the holdout, and are judged against what those customers did, by decile
of calibration frequency. PyMC-Marketing fits the same two models to the same frame as a cross
check. Lifetime value is computed at the calibration end from the models the holdout judged,
not from a refit on the whole file, so the published values come from the model whose holdout
errors are published beside them. Customers whose first purchase falls in the holdout are
counted but not predicted: the models describe customers they have seen.

Writes under results/clv:
  rfm.parquet                per customer: the calibration summary, segment, probability alive,
                             predicted and actual holdout purchases and revenue, and the twelve
                             month expected purchases, expected spend and lifetime value
  holdout_by_decile.parquet  predicted against actual per decile of calibration frequency, and overall
  calibration_plot.parquet   mean predicted against mean actual holdout purchases, ten bins by prediction
  clv_distribution.parquet   lifetime value histogram (30 bins; the last is open ended above the
                             99th percentile, so the long tail does not flatten the chart) and quantiles
  segments.parquet           per segment: customers, mean lifetime value, allowance
  parameters.json            both models' estimates and optimizer records, the independence check,
                             the cross check and the settings
  allowance.json             the allowance per channel and per segment and the revenue per
                             acquisition, the file marginal_budget and the API read
and results/manifests/clv.json.

Amounts are the retailer's own, in pounds sterling, printed with the repository's money formats.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from marginal_clv import (
    BGNBD,
    DAYS_PER_MONTH,
    SEGMENTS,
    Allowance,
    CrossCheck,
    GammaGamma,
    IndependenceCheck,
    acquisition_allowance,
    calibration_plot,
    cross_check,
    customer_lifetime_value,
    holdout_by_decile,
    holdout_frame,
    monthly_discount_rate,
    revenue_per_acquisition,
    rfm_frame,
    segments,
    spend_frequency_correlation,
)
from marginal_contracts.retail import CALIBRATION_END, HOLDOUT_START, split_windows
from marginal_core.config import CHANNEL_LABELS, CHANNELS, POLICY
from marginal_core.manifest import Manifest, Scalar, Scribe
from marginal_core.paths import Paths

HISTOGRAM_BINS = 30
HISTOGRAM_TOP = 0.99
QUANTILES = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99)


def run(paths: Paths, as_of: str, seed: int) -> Manifest:
    out = paths.results / "clv"
    out.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(as_of=as_of, seed=seed)

    purchases = pl.read_parquet(paths.data / "retail" / "purchases.parquet")
    calibration, holdout = split_windows(purchases)
    if holdout.height == 0 or calibration.height == 0:
        raise ValueError("the purchase history has an empty calibration or holdout window")
    if CALIBRATION_END + dt.timedelta(days=1) != HOLDOUT_START:
        raise ValueError("the holdout must start the day after the calibration window ends")
    first_holdout_day = holdout["day"].min()
    holdout_end = holdout["day"].max()
    if not isinstance(first_holdout_day, dt.date) or not isinstance(holdout_end, dt.date):
        raise TypeError("the purchase table's day column does not hold dates")
    if first_holdout_day <= CALIBRATION_END:
        raise ValueError("the holdout overlaps the calibration window")

    rfm = rfm_frame(purchases, CALIBRATION_END)
    actual = holdout_frame(purchases, HOLDOUT_START, holdout_end)
    if not rfm["customer_id"].equals(actual["customer_id"]):
        raise ValueError("the holdout frame and the calibration frame hold different customers")
    frame = rfm.join(actual, on="customer_id", how="left")
    horizon_days = (holdout_end - CALIBRATION_END).days
    if horizon_days != int(actual["holdout_days"][0]):
        raise ValueError("the prediction horizon and the holdout length disagree")
    customers_in_file = int(purchases["customer_id"].n_unique())
    new_in_holdout = customers_in_file - rfm.height

    x, t_x, age = frame["frequency"], frame["recency"], frame["T"]
    bg = BGNBD().fit(x, t_x, age)
    gg = GammaGamma().fit(frame["frequency"], frame["monetary"])
    independence = spend_frequency_correlation(frame["frequency"], frame["monetary"])

    predicted_purchases = bg.expected_purchases(horizon_days, x, t_x, age)
    spend = gg.conditional_expected_average_profit(frame["frequency"], frame["monetary"])
    predicted_revenue = predicted_purchases * spend
    deciles = holdout_by_decile(frame, predicted_purchases, predicted_revenue)
    plot = calibration_plot(frame, predicted_purchases)

    value = customer_lifetime_value(bg, gg, frame, POLICY.clv_horizon_months, POLICY.clv_discount_rate_annual)
    valued = segments(
        frame.with_columns(
            pl.Series("probability_alive", bg.probability_alive(x, t_x, age)),
            pl.Series("predicted_holdout_purchases", predicted_purchases),
            pl.Series("predicted_holdout_revenue", predicted_revenue),
        ).join(value, on="customer_id", how="left")
    )
    allowance = acquisition_allowance(valued, POLICY.contribution_margin, POLICY.clv_payback_share)
    rpa = revenue_per_acquisition(frame)
    check = cross_check(frame, bg, gg)

    valued.write_parquet(out / "rfm.parquet")
    deciles.write_parquet(out / "holdout_by_decile.parquet")
    plot.write_parquet(out / "calibration_plot.parquet")
    clv_values = valued["clv"].to_numpy()
    _distribution(clv_values).write_parquet(out / "clv_distribution.parquet")
    _segment_frame(allowance).write_parquet(out / "segments.parquet")
    settings = {
        "calibration_end": str(CALIBRATION_END),
        "holdout_start": str(HOLDOUT_START),
        "holdout_end": str(holdout_end),
        "holdout_days": horizon_days,
        "horizon_months": POLICY.clv_horizon_months,
        "days_per_month": DAYS_PER_MONTH,
        "discount_rate_annual": POLICY.clv_discount_rate_annual,
        "discount_rate_monthly": monthly_discount_rate(POLICY.clv_discount_rate_annual),
        "margin": POLICY.contribution_margin,
        "payback_share": POLICY.clv_payback_share,
    }
    counts = {
        "calibration": rfm.height,
        "repeat": int((rfm["frequency"] > 0).sum()),
        "in_file": customers_in_file,
        "new_in_holdout": new_in_holdout,
    }
    _write_json(out / "parameters.json", _parameters(bg, gg, independence, check, settings, counts))
    _write_json(out / "allowance.json", _allowance_payload(allowance, rpa), sort_keys=False)

    population = (
        f"{rfm.height:,} customers who bought by {CALIBRATION_END} (of {customers_in_file:,} in the file), "
        f"calibration to {CALIBRATION_END}"
    )
    _write_manifest(
        manifest,
        population,
        bg,
        gg,
        independence,
        deciles,
        clv_values,
        allowance,
        rpa,
        check,
        counts,
        holdout_end,
    )
    manifest.save(paths.results / "manifests" / "clv.json")
    return manifest


# Files


def _write_json(path: Path, payload: dict[str, Any], *, sort_keys: bool = True) -> None:
    path.write_text(json.dumps(payload, indent=1, sort_keys=sort_keys) + "\n", encoding="utf-8")


def _distribution(clv: np.ndarray) -> pl.DataFrame:
    """Thirty equal bins from zero to the 99th percentile, the last open ended, then the quantiles."""
    top = float(np.quantile(clv, HISTOGRAM_TOP))
    low = min(0.0, float(clv.min()))
    edges = np.linspace(low, top, HISTOGRAM_BINS + 1)
    # np.histogram closes the last bin, so clipping at the top edge puts the tail into it.
    counts, _ = np.histogram(np.clip(clv, low, top), bins=edges)
    rows: list[dict[str, Any]] = [
        {
            "kind": "bin",
            "bin": i + 1,
            "low": float(edges[i]),
            "high": float(edges[i + 1]),
            "open_ended": i == HISTOGRAM_BINS - 1,
            "customers": int(counts[i]),
            "share": float(counts[i]) / clv.size,
            "quantile": None,
            "value": None,
        }
        for i in range(HISTOGRAM_BINS)
    ]
    rows += [
        {
            "kind": "quantile",
            "bin": None,
            "low": None,
            "high": None,
            "open_ended": None,
            "customers": None,
            "share": None,
            "quantile": q,
            "value": float(np.quantile(clv, q)),
        }
        for q in QUANTILES
    ]
    schema = {
        "kind": pl.Utf8,
        "bin": pl.Int64,
        "low": pl.Float64,
        "high": pl.Float64,
        "open_ended": pl.Boolean,
        "customers": pl.Int64,
        "share": pl.Float64,
        "quantile": pl.Float64,
        "value": pl.Float64,
    }
    return pl.DataFrame(rows, schema=schema)


def _segment_frame(allowance: Allowance) -> pl.DataFrame:
    by_slug = {s.slug: s for s in SEGMENTS}
    return pl.DataFrame(
        [
            {
                "segment": s.segment,
                "label": s.label,
                "frequency_low": by_slug[s.segment].low,
                "frequency_high": by_slug[s.segment].high,
                "customers": s.customers,
                "mean_clv": s.mean_clv,
                "allowance": s.allowance,
            }
            for s in allowance.segments
        ],
        schema={
            "segment": pl.Utf8,
            "label": pl.Utf8,
            "frequency_low": pl.Int64,
            "frequency_high": pl.Int64,
            "customers": pl.Int64,
            "mean_clv": pl.Float64,
            "allowance": pl.Float64,
        },
    )


def _parameters(
    bg: BGNBD,
    gg: GammaGamma,
    independence: IndependenceCheck,
    check: CrossCheck,
    settings: dict[str, Any],
    counts: dict[str, int],
) -> dict[str, Any]:
    if bg.record is None or gg.record is None:
        raise ValueError("both models must be fit before their parameters are written")
    return {
        "bgnbd": {**bg.params, "fit": bg.record.model_dump(mode="json")},
        "gamma_gamma": {
            **gg.params,
            "population_mean_spend": gg.population_mean_spend,
            "fit": gg.record.model_dump(mode="json"),
            "independence": independence.model_dump(mode="json"),
        },
        "crosscheck": check.model_dump(mode="json"),
        "settings": settings,
        "customers": counts,
    }


def _allowance_payload(allowance: Allowance, rpa: float) -> dict[str, Any]:
    """The exact shape marginal_budget and the API read; the keys are a contract."""
    return {
        "allowance_by_channel": {c: allowance.by_channel[c] for c in CHANNELS},
        "allowance_by_segment": allowance.by_segment,
        "revenue_per_acquisition": rpa,
        "margin": POLICY.contribution_margin,
        "payback_share": POLICY.clv_payback_share,
        "horizon_months": POLICY.clv_horizon_months,
        "discount_rate_annual": POLICY.clv_discount_rate_annual,
    }


# The manifest


def _yes(flag: bool) -> str:
    return "yes" if flag else "no"


def _write_manifest(
    manifest: Manifest,
    population: str,
    bg: BGNBD,
    gg: GammaGamma,
    independence: IndependenceCheck,
    deciles: pl.DataFrame,
    clv_values: np.ndarray,
    allowance: Allowance,
    rpa: float,
    check: CrossCheck,
    counts: dict[str, int],
    holdout_end: dt.date,
) -> None:
    if bg.record is None:
        raise ValueError("the BG/NBD model must be fit before it is published")
    w = Scribe(manifest, source="real:retail", model="bgnbd", population=population, origin="marginal_clv")
    w.put("clv.customers", counts["calibration"], "int")
    w.put("clv.customers_repeat", counts["repeat"], "int")
    w.put("clv.customers_in_file", counts["in_file"], "int")
    w.put("clv.customers_new_in_holdout", counts["new_in_holdout"], "int")
    w.put("clv.calibration_end", str(CALIBRATION_END), "text")
    w.put("clv.holdout_start", str(HOLDOUT_START), "text")
    w.put("clv.holdout_end", str(holdout_end), "text")
    for name, value in bg.params.items():
        w.put(f"clv.bgnbd.{name}", value, "float3")
    for name, value in gg.params.items():
        w.put(f"clv.gg.{name}", value, "float3")
    w.put("clv.gg.correlation", independence.correlation, "float3")
    w.put("clv.bgnbd.converged", _yes(bg.record.converged), "text")
    w.put("clv.bgnbd.evaluations", bg.record.evaluations, "int")

    rows = deciles.to_dicts()
    overall = rows[-1]
    if overall["decile"] != "all":
        raise ValueError("the decile table must end with the overall row")
    w.put("clv.holdout.mae_purchases", overall["mae_purchases"], "float2")
    w.put("clv.holdout.mae_revenue", overall["mae_revenue"], "usd2")
    w.put("clv.holdout.predicted_purchases_total", overall["predicted_purchases"], "int")
    w.put("clv.holdout.actual_purchases_total", overall["actual_purchases"], "int")
    w.put("clv.holdout.predicted_revenue_total", overall["predicted_revenue"], "usd2")
    w.put("clv.holdout.actual_revenue_total", overall["actual_revenue"], "usd2")
    # The miss, plainly: predicted over actual, overall and in the top decile, and the fitted
    # dropout probability after a purchase (a / (a + b)), which is what drives an over prediction.
    w.put(
        "clv.holdout.purchases_predicted_over_actual",
        overall["predicted_purchases"] / overall["actual_purchases"] - 1.0,
        "spct1",
    )
    w.put(
        "clv.holdout.revenue_predicted_over_actual",
        overall["predicted_revenue"] / overall["actual_revenue"] - 1.0,
        "spct1",
    )
    top = rows[-2]
    w.put(
        "clv.holdout.top_decile_purchases_predicted_over_actual",
        top["predicted_purchases"] / top["actual_purchases"] - 1.0,
        "spct1",
    )
    w.put("clv.bgnbd.dropout_after_purchase", bg.params["a"] / (bg.params["a"] + bg.params["b"]), "pct2")
    w.table(
        "clv.holdout_by_decile",
        [
            "Decile",
            "Customers",
            "Predicted purchases",
            "Actual purchases",
            "Predicted revenue",
            "Actual revenue",
        ],
        ["text", "int", "int", "int", "usd2", "usd2"],
        [
            [
                "All customers" if r["decile"] == "all" else str(r["decile"]),
                r["customers"],
                r["predicted_purchases"],
                r["actual_purchases"],
                r["predicted_revenue"],
                r["actual_revenue"],
            ]
            for r in rows
        ],
    )

    w.put("clv.clv.mean", float(np.mean(clv_values)), "usd2")
    w.put("clv.clv.median", float(np.median(clv_values)), "usd2")
    w.put("clv.clv.p90", float(np.quantile(clv_values, 0.90)), "usd2")
    w.put("clv.allowance.overall", allowance.overall.allowance, "usd2")
    for s in allowance.segments:
        w.put(f"clv.allowance.{s.segment}", s.allowance, "usd2")
    for c in allowance.channels:
        w.put(f"clv.allowance.channel.{c.channel}", c.allowance, "usd2")
    w.put("clv.revenue_per_acquisition", rpa, "usd2")
    by_slug = {s.slug: s for s in SEGMENTS}
    segment_rows: list[list[Scalar]] = [
        [f"{s.label.capitalize()} ({by_slug[s.segment].description})", s.customers, s.mean_clv, s.allowance]
        for s in allowance.segments
    ]
    overall_row: list[Scalar] = [
        "All customers",
        allowance.overall.customers,
        allowance.overall.mean_clv,
        allowance.overall.allowance,
    ]
    w.table(
        "clv.segments",
        ["Segment", "Customers", "Mean lifetime value", "Allowance"],
        ["text", "int", "usd2", "usd2"],
        [*segment_rows, overall_row],
    )
    w.table(
        "clv.allowance_by_channel",
        ["Channel", "Allowance"],
        ["text", "usd2"],
        [[CHANNEL_LABELS[c.channel], c.allowance] for c in allowance.channels],
    )

    cross = Scribe(
        manifest,
        source="real:retail",
        model="bgnbd_pymc" if check.available else "bgnbd",
        population=f"{population}; PyMC-Marketing fit by MAP under flat priors beside the repository's fit",
        origin="marginal_clv.crosscheck",
    )
    cross.put("clv.crosscheck.available", _yes(check.available), "text")
    cross.put("clv.crosscheck.max_relative_difference", check.max_relative_difference, "pct3")
    cross.table(
        "clv.parameters",
        ["Parameter", "Repository", "PyMC-Marketing"],
        ["text", "float3", "float3"],
        [
            [f"{'BG/NBD' if p.model == 'bgnbd' else 'Gamma-Gamma'} {p.parameter}", p.repository, p.pymc]
            for p in check.parameters
        ],
    )
