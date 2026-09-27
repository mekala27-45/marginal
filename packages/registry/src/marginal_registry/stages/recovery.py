"""Stage: one backend fit on the demonstration brand, then graded on markets with known truth.

Writes, per backend:
  results/mmm/{backend}_returns.parquet        return per channel with the interval, beside the truth
  results/mmm/{backend}_contributions.parquet  baseline and contributions by week
  results/mmm/{backend}_curves.parquet         response curves on a spend grid with the truth beside
  results/mmm/{backend}_diagnostics.json       did it run: replicates, evaluations, draws, divergences
  results/recovery/{backend}_rows.parquet      every seed, condition and channel against the truth
  results/recovery/{backend}_ranks.parquet     rank agreement per seed and condition
  results/recovery/{backend}_summary.parquet   bias, error and coverage with intervals over seeds
  results/manifests/recovery_{backend}.json
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable

import numpy as np
import polars as pl
from marginal_core.config import CHANNEL_LABELS, CHANNELS, POLICY
from marginal_core.frames import mean, median, total
from marginal_core.manifest import Manifest, Scribe
from marginal_core.paths import Paths
from marginal_evaluation import ChannelEstimate, FitResult, floor_crossing, observed, run_recovery, summarise
from marginal_mmm import MMMSpec, Model, fit
from marginal_sim import CONDITIONS, condition_name, demonstration_spec, response, truth_params
from marginal_sim.spec import ChannelTruth

ERROR_FLOOR = 0.25
"""The callout names the conditions where the median absolute error over channels crosses this."""


def _spec(backend: str, seed: int) -> MMMSpec:
    if backend == "own":
        return MMMSpec(backend="own", seed=seed)
    return MMMSpec(backend="bayes", seed=seed)


def _fit_fn(backend: str) -> Callable[[pl.DataFrame, int], FitResult]:
    def inner(panel: pl.DataFrame, seed: int) -> FitResult:
        model = fit(panel, _spec(backend, seed))
        channels = [
            ChannelEstimate(
                channel=e.channel,
                roas=e.roas,
                roas_lower=e.roas_lower,
                roas_upper=e.roas_upper,
                marginal_return=e.marginal_return,
                carryover=e.carryover,
            )
            for e in model.intervals()
        ]
        return FitResult(backend=backend, channels=channels, diagnostics=model.diagnostics())

    return inner


def seeds_for(backend: str) -> int:
    override = os.environ.get(f"MARGINAL_RECOVERY_SEEDS_{backend.upper()}")
    if override:
        return int(override)
    return POLICY.recovery_seeds_own if backend == "own" else POLICY.recovery_seeds_bayes


def run(paths: Paths, as_of: str, seed: int, *, backend: str = "own") -> Manifest:
    if backend not in ("own", "bayes"):
        raise ValueError("backend must be own or bayes")
    manifest = Manifest(as_of=as_of, seed=seed)
    spec = demonstration_spec(seed)
    demo = _demonstration_fit(paths, manifest, backend, seed, spec.condition)
    _recovery_study(paths, manifest, backend, seed, demo)
    manifest.save(paths.results / "manifests" / f"recovery_{backend}.json")
    return manifest


def _demonstration_fit(paths: Paths, manifest: Manifest, backend: str, seed: int, condition: str) -> Model:
    national = pl.read_parquet(paths.sim / "national.parquet")
    truth = pl.read_parquet(paths.sim / "truth_channels.parquet")
    market = json.loads((paths.sim / "market.json").read_text())
    started = time.time()
    model = fit(observed(national), _spec(backend, seed), data_source="simulated")
    seconds = time.time() - started
    out = paths.results / "mmm"
    out.mkdir(parents=True, exist_ok=True)

    truth_by = {str(r["channel"]): r for r in truth.iter_rows(named=True)}
    rows = []
    for e in model.intervals():
        t = truth_by[e.channel]
        rows.append(
            {
                "backend": backend,
                "channel": e.channel,
                "roas": e.roas,
                "roas_lower": e.roas_lower,
                "roas_upper": e.roas_upper,
                "roas_true": float(t["roas_true"]),
                "covered": e.roas_lower <= float(t["roas_true"]) <= e.roas_upper,
                "marginal_return": e.marginal_return,
                "marginal_true": float(t["marginal_return_true"]),
                "carryover": e.carryover,
                "carryover_true": float(t["carryover"]),
                "half_life_weeks": e.half_life_weeks,
                "half_life_true": float(t["half_life_weeks"]),
                "half_saturation": e.half_saturation,
                "slope": e.slope,
                "spend_last_year": e.spend_last_year,
                "incremental_last_year": e.incremental_last_year,
            }
        )
    returns = pl.DataFrame(rows)
    returns.write_parquet(out / f"{backend}_returns.parquet")
    contributions = model.contributions().with_columns(pl.lit(backend).alias("backend"))
    contributions.write_parquet(out / f"{backend}_contributions.parquet")

    truth_params_by = {p["channel"]: p for p in market["truth"]}
    curve_rows = []
    for channel in CHANNELS:
        current = float(truth_by[channel]["weekly_spend_current"])
        grid = np.linspace(0.0, 3.0 * current, 31)
        est = model.response_curve(channel, grid)
        tp = truth_params(_channel_truth(truth_params_by[channel]))
        true_curve = response(tp, grid)
        for g, a, b in zip(grid, est, true_curve, strict=True):
            curve_rows.append(
                {
                    "backend": backend,
                    "channel": channel,
                    "spend": float(g),
                    "estimate": float(a),
                    "truth": float(b),
                }
            )
    pl.DataFrame(curve_rows).write_parquet(out / f"{backend}_curves.parquet")
    diagnostics = model.diagnostics()
    diagnostics["fit_seconds"] = round(seconds, 1)
    (out / f"{backend}_diagnostics.json").write_text(
        json.dumps(diagnostics, indent=1, sort_keys=True, default=str) + "\n"
    )

    w = Scribe(
        manifest,
        source="simulated",
        model=backend,
        population="demonstration brand, 156 weeks",
        origin=f"marginal_mmm.{backend}",
        condition=condition,
    )
    for r in returns.iter_rows(named=True):
        key = str(r["channel"])
        w.put(f"mmm.{backend}.roas.{key}", r["roas"], "float2")
        w.put(f"mmm.{backend}.roas_lower.{key}", r["roas_lower"], "float2")
        w.put(f"mmm.{backend}.roas_upper.{key}", r["roas_upper"], "float2")
        w.put(f"mmm.{backend}.marginal.{key}", r["marginal_return"], "float2")
        w.put(f"mmm.{backend}.half_life.{key}", r["half_life_weeks"], "float1")
        w.put(f"mmm.{backend}.covered.{key}", "yes" if r["covered"] else "no", "text")
    w.table(
        f"mmm.{backend}.returns",
        [
            "Channel",
            "Return",
            "Lower",
            "Upper",
            "Truth (simulated)",
            "Covers",
            "Marginal return",
            "True marginal",
            "Half life (weeks)",
            "True half life",
        ],
        ["text", "float2", "float2", "float2", "float2", "text", "float2", "float2", "float1", "float1"],
        [
            [
                CHANNEL_LABELS[str(r["channel"])],
                r["roas"],
                r["roas_lower"],
                r["roas_upper"],
                r["roas_true"],
                "yes" if r["covered"] else "no",
                r["marginal_return"],
                r["marginal_true"],
                r["half_life_weeks"],
                r["half_life_true"],
            ]
            for r in returns.iter_rows(named=True)
        ],
    )
    w.put(f"mmm.{backend}.covered_count", int(returns["covered"].sum()), "int")
    w.put(f"mmm.{backend}.residual_share", float(diagnostics.get("residual_share_of_sales", 0.0)), "pct1")
    w.put(
        f"mmm.{backend}.unexplained_variance",
        float(diagnostics.get("unexplained_variance_share", 0.0)),
        "pct1",
    )
    w.put(f"mmm.{backend}.fit_seconds", seconds, "float1")
    w.put(f"mmm.{backend}.spec_hash", str(diagnostics.get("spec_hash", "")), "text")
    baseline_share = total(contributions, "baseline") / total(contributions, "sales")
    w.put(f"mmm.{backend}.baseline_share", baseline_share, "pct1")
    for key in (
        "bootstrap_replicates",
        "grid_evaluations",
        "nelder_mead_evaluations",
        "draws",
        "chains",
        "divergences",
        "max_rhat",
        "tune",
    ):
        if key in diagnostics:
            value = diagnostics[key]
            fmt = "float3" if key == "max_rhat" else "int"
            w.put(f"mmm.{backend}.{key}", float(value) if fmt == "float3" else int(float(value)), fmt)
    return model


def _channel_truth(params: dict[str, object]) -> ChannelTruth:
    return ChannelTruth(
        channel=str(params["channel"]),
        mean_weekly_spend=float(params["mean_weekly_spend"]),  # type: ignore[arg-type]
        carryover=float(params["carryover"]),  # type: ignore[arg-type]
        half_saturation_ratio=float(params["half_saturation"]) / float(params["mean_weekly_spend"]),  # type: ignore[arg-type]
        slope=float(params["slope"]),  # type: ignore[arg-type]
        roas_at_mean=float(params["roas_at_mean"]),  # type: ignore[arg-type]
    )


def _recovery_study(paths: Paths, manifest: Manifest, backend: str, seed: int, demo: Model) -> None:
    seeds = seeds_for(backend)
    out = paths.results / "recovery"
    out.mkdir(parents=True, exist_ok=True)
    log = paths.logs / f"recovery_{backend}.log"
    log.parent.mkdir(parents=True, exist_ok=True)

    def progress(message: str) -> None:
        with log.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%H:%M:%S')} {message}\n")

    rows, ranks, diagnostics = run_recovery(_fit_fn(backend), backend, CONDITIONS, seeds, progress=progress)
    summary = summarise(rows, ranks, level=POLICY.interval_level, seed=seed)
    rows.write_parquet(out / f"{backend}_rows.parquet")
    ranks.write_parquet(out / f"{backend}_ranks.parquet")
    summary.write_parquet(out / f"{backend}_summary.parquet")
    (out / f"{backend}_diagnostics.json").write_text(json.dumps(diagnostics, indent=1, default=str) + "\n")

    w = Scribe(
        manifest,
        source="simulated",
        model=backend,
        population="markets with known truth",
        origin="marginal_evaluation.recovery",
        seeds=seeds,
    )
    w.put(f"recovery.{backend}.seeds_per_condition", seeds, "int")
    w.put(f"recovery.{backend}.conditions", len(CONDITIONS), "int")
    w.put(f"recovery.{backend}.fits", len(diagnostics), "int")
    table_rows = []
    for r in summary.iter_rows(named=True):
        cond = str(r["condition"])
        ch = str(r["channel"])
        slug = cond.replace(" ", "_").replace(",", "").replace(".", "")
        if ch == "all":
            w.put(
                f"recovery.{backend}.{slug}.median_abs_error", r["median_abs_error"], "pct1", condition=cond
            )
            w.put(f"recovery.{backend}.{slug}.coverage", r["coverage"], "pct0", condition=cond)
            w.put(f"recovery.{backend}.{slug}.rank_agreement", r["rank_agreement"], "float2", condition=cond)
            w.put(
                f"recovery.{backend}.{slug}.rank_agreement_lower",
                r["rank_agreement_lower"],
                "float2",
                condition=cond,
            )
            w.put(
                f"recovery.{backend}.{slug}.rank_agreement_upper",
                r["rank_agreement_upper"],
                "float2",
                condition=cond,
            )
            table_rows.append(
                [
                    cond,
                    "All channels",
                    None,
                    None,
                    None,
                    r["median_abs_error"],
                    None,
                    None,
                    r["coverage"],
                    r["rank_agreement"],
                ]
            )
        else:
            table_rows.append(
                [
                    cond,
                    CHANNEL_LABELS[ch],
                    r["bias"],
                    r["bias_lower"],
                    r["bias_upper"],
                    r["median_abs_error"],
                    r["median_abs_error_lower"],
                    r["median_abs_error_upper"],
                    r["coverage"],
                    None,
                ]
            )
    w.table(
        f"recovery.{backend}.summary",
        [
            "Condition",
            "Channel",
            "Bias",
            "Bias lower",
            "Bias upper",
            "Median abs error",
            "Error lower",
            "Error upper",
            "Coverage",
            "Rank agreement",
        ],
        ["text", "text", "spct1", "spct1", "spct1", "pct1", "pct1", "pct1", "pct0", "float2"],
        table_rows,
    )
    crossed = floor_crossing(summary, ERROR_FLOOR)
    w.put(f"recovery.{backend}.error_floor", ERROR_FLOOR, "pct0")
    w.put(f"recovery.{backend}.conditions_over_floor", ", ".join(crossed) if crossed else "none", "text")
    demo_condition = condition_name(0.6, True)
    demo_rows = summary.filter((pl.col("condition") == demo_condition) & (pl.col("channel") == "all"))
    if demo_rows.height:
        w.put(
            f"recovery.{backend}.demonstration.median_abs_error",
            demo_rows["median_abs_error"][0],
            "pct1",
            condition=demo_condition,
        )
        w.put(
            f"recovery.{backend}.demonstration.coverage",
            demo_rows["coverage"][0],
            "pct0",
            condition=demo_condition,
        )
    all_rows = summary.filter(pl.col("channel") == "all")
    abs_errors = rows.with_columns(pl.col("relative_error").abs().alias("abs_error"))
    w.put(f"recovery.{backend}.median_abs_error_overall", median(abs_errors, "abs_error"), "pct1")
    w.put(
        f"recovery.{backend}.coverage_overall",
        mean(rows.with_columns(pl.col("covered").cast(pl.Float64)), "covered"),
        "pct0",
    )
    worst = all_rows.sort("median_abs_error", descending=True).row(0, named=True)
    w.put(f"recovery.{backend}.worst_condition", str(worst["condition"]), "text")
    w.put(f"recovery.{backend}.worst_condition_error", worst["median_abs_error"], "pct1")
    best = all_rows.sort("median_abs_error").row(0, named=True)
    w.put(f"recovery.{backend}.best_condition", str(best["condition"]), "text")
    w.put(f"recovery.{backend}.best_condition_error", best["median_abs_error"], "pct1")
    # Did every fit run: for own the bootstrap count, for bayes the draws and divergences.
    ran = [d for d in diagnostics if float(d.get("bootstrap_replicates", d.get("draws", 0))) > 0]
    w.put(f"recovery.{backend}.fits_that_ran", len(ran), "int")
