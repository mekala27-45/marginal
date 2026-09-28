"""Stage: the posted lift result into both backends, before and after.

Writes under results/calibrate:
  {backend}_before_after.json      the tested channel before and after, truth beside it
  {backend}_calibrated_model.json  the calibrated response curves (the API serves own's)
  {backend}_recovery_after.parquet the calibrated estimates across the demonstration seeds
  own_weight_test.json             the interior test on the calibration weight
and results/manifests/calibrate.json. The bayes half runs when the bayes recovery has run
(its uncalibrated estimates per seed are the "before"); otherwise it is marked not run.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import polars as pl
from marginal_calibrate import (
    BeforeAfter,
    before_after,
    error_summary,
    lift_from_registry,
    recovery_after_calibration,
    weight_interior_test,
)
from marginal_core.config import CHANNEL_LABELS, POLICY
from marginal_core.manifest import Manifest, Scribe
from marginal_core.paths import Paths
from marginal_evaluation import observed
from marginal_mmm import MMMSpec, export_model, fit
from marginal_sim import condition_name, demonstration_spec


def _spec_factory(backend: str) -> Callable[[int], MMMSpec]:
    def inner(seed: int) -> MMMSpec:
        return _spec(backend, seed)

    return inner


def _spec(backend: str, seed: int) -> MMMSpec:
    return MMMSpec(backend="own", seed=seed) if backend == "own" else MMMSpec(backend="bayes", seed=seed)


def run(paths: Paths, as_of: str, seed: int, *, backends: tuple[str, ...] = ("own", "bayes")) -> Manifest:
    out = paths.results / "calibrate"
    out.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(as_of=as_of, seed=seed)
    geo = pl.read_parquet(paths.sim / "geo_panel.parquet")
    national = pl.read_parquet(paths.sim / "national.parquet")
    truth = pl.read_parquet(paths.sim / "truth_channels.parquet")
    lift, truth_lift = lift_from_registry(paths.results, geo)
    result = json.loads((paths.results / "experiments" / "geo_result.json").read_text(encoding="utf-8"))
    experiment = {"lower": float(result["did"]["lower"]), "upper": float(result["did"]["upper"])}
    base = demonstration_spec(seed)
    condition = condition_name(0.6, True)
    log = paths.logs / "calibrate.log"

    def progress(message: str) -> None:
        with log.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%H:%M:%S')} {message}\n")

    shared = Scribe(
        manifest,
        source="simulated",
        population="the posted lift result",
        origin="marginal_calibrate.loop",
        condition=condition,
    )
    shared.put("calibrate.channel", CHANNEL_LABELS[lift.channel], "text")
    shared.put("calibrate.experiment_lift", lift.incremental_revenue, "usd0")
    shared.put("calibrate.experiment_se", lift.standard_error, "usd0")
    shared.put("calibrate.truth_lift", truth_lift, "usd0")
    shared.put("calibrate.geo_share", lift.geo_share, "pct1")
    shared.put("calibrate.plan_hash", lift.plan_hash, "text")

    for backend in backends:
        rows_before = paths.results / "recovery" / f"{backend}_rows.parquet"
        if backend == "bayes" and not rows_before.exists():
            shared.put("calibrate.bayes.status", "not run: the bayes recovery study has not run", "text")
            continue
        model = fit(observed(national), _spec(backend, seed))
        calibrated, summary = before_after(model, lift, truth, truth_lift, experiment)
        (out / f"{backend}_before_after.json").write_text(
            json.dumps(summary.model_dump(), indent=1, sort_keys=True) + "\n"
        )
        spec_hash = calibrated.spec_hash[:8]
        export = export_model(calibrated, version=f"{backend}-{spec_hash}-calibrated")
        (out / f"{backend}_calibrated_model.json").write_text(
            json.dumps(export.model_dump(mode="json"), indent=1) + "\n"
        )
        _write_summary(manifest, backend, summary, condition)

        before = pl.read_parquet(rows_before).filter(pl.col("condition") == condition)
        seeds_env = os.environ.get(f"MARGINAL_CALIBRATE_SEEDS_{backend.upper()}")
        seeds = sorted(before["seed"].unique().to_list())
        if seeds_env:
            seeds = seeds[: int(seeds_env)]
        after = recovery_after_calibration(backend, seeds, base, _spec_factory(backend), progress=progress)
        after.write_parquet(out / f"{backend}_recovery_after.parquet")
        before_summary = error_summary(before.filter(pl.col("seed").is_in(seeds)))
        after_summary = error_summary(after)
        w = Scribe(
            manifest,
            source="simulated",
            model=backend,
            population="markets with known truth, demonstration condition",
            origin="marginal_calibrate.loop",
            condition=condition,
            seeds=len(seeds),
        )
        w.put(f"calibrate.{backend}.recovery.seeds", len(seeds), "int")
        w.put(f"calibrate.{backend}.recovery.error_before", before_summary["median_abs_error"], "pct1")
        w.put(f"calibrate.{backend}.recovery.error_after", after_summary["median_abs_error"], "pct1")
        w.put(f"calibrate.{backend}.recovery.coverage_before", before_summary["coverage"], "pct0")
        w.put(f"calibrate.{backend}.recovery.coverage_after", after_summary["coverage"], "pct0")
        tested_before = before.filter(pl.col("channel") == lift.channel)
        tested_after = after.filter(pl.col("channel") == lift.channel)
        w.put(
            f"calibrate.{backend}.recovery.tested_error_before",
            float(np.median(np.abs(tested_before["relative_error"].to_numpy()))),
            "pct1",
        )
        w.put(
            f"calibrate.{backend}.recovery.tested_error_after",
            float(np.median(np.abs(tested_after["relative_error"].to_numpy()))),
            "pct1",
        )
        w.put(
            f"calibrate.{backend}.recovery.tested_bias_before",
            float(np.mean(tested_before["relative_error"].to_numpy())),
            "spct1",
        )
        w.put(
            f"calibrate.{backend}.recovery.tested_bias_after",
            float(np.mean(tested_after["relative_error"].to_numpy())),
            "spct1",
        )
        w.table(
            f"calibrate.{backend}.recovery",
            ["", "Before", "After"],
            ["text", "pct1", "pct1"],
            [
                [
                    "Median absolute error, all channels",
                    before_summary["median_abs_error"],
                    after_summary["median_abs_error"],
                ],
                [
                    "Median absolute error, tested channel",
                    float(np.median(np.abs(tested_before["relative_error"].to_numpy()))),
                    float(np.median(np.abs(tested_after["relative_error"].to_numpy()))),
                ],
                ["Interval coverage, all channels", before_summary["coverage"], after_summary["coverage"]],
            ],
        )

    if "own" in backends:
        test = weight_interior_test(observed(national), _spec("own", seed), lift)
        (out / "own_weight_test.json").write_text(
            json.dumps(test.model_dump(), indent=1, sort_keys=True) + "\n"
        )
        w = Scribe(
            manifest,
            source="simulated",
            model="own",
            population="demonstration brand",
            origin="marginal_calibrate.loop.weight_interior_test",
            condition=condition,
        )
        w.put("calibrate.weight.residual_half", test.residual_half, "usd0")
        w.put("calibrate.weight.residual_one", test.residual_one, "usd0")
        w.put("calibrate.weight.residual_double", test.residual_double, "usd0")
        w.put("calibrate.weight.interior", "interior" if test.interior else "degenerate", "text")
        w.put("calibrate.weight.reason", test.reason, "text")
        w.put("calibrate.weight.level", POLICY.interval_level, "pct0")

    target = paths.results / "manifests" / "calibrate.json"
    _carry_over(manifest, target, backends)
    manifest.save(target)
    return manifest


def _carry_over(manifest: Manifest, target: Path, backends: tuple[str, ...]) -> None:
    """A run of one backend keeps the other backend's entries from the previous manifest, so
    ``--backends bayes`` after an ``own`` run leaves both halves on the page."""
    if not target.exists():
        return
    previous = Manifest.load(target)
    prefixes = [f"calibrate.{b}." for b in ("own", "bayes") if b not in backends]
    if "own" not in backends:
        prefixes.append("calibrate.weight.")
    for key, value in previous.values.items():
        if any(key.startswith(p) for p in prefixes) and key not in manifest.values:
            manifest.values[key] = value
    for key, table in previous.tables.items():
        if any(key.startswith(p) for p in prefixes) and key not in manifest.tables:
            manifest.tables[key] = table


def _write_summary(manifest: Manifest, backend: str, s: BeforeAfter, condition: str) -> None:
    w = Scribe(
        manifest,
        source="simulated",
        model=backend,
        population="demonstration brand",
        origin="marginal_calibrate.loop",
        condition=condition,
    )
    w.put(f"calibrate.{backend}.roas_before", s.roas_before, "float2")
    w.put(f"calibrate.{backend}.roas_before_lower", s.roas_before_lower, "float2")
    w.put(f"calibrate.{backend}.roas_before_upper", s.roas_before_upper, "float2")
    w.put(f"calibrate.{backend}.roas_after", s.roas_after, "float2")
    w.put(f"calibrate.{backend}.roas_after_lower", s.roas_after_lower, "float2")
    w.put(f"calibrate.{backend}.roas_after_upper", s.roas_after_upper, "float2")
    w.put(f"calibrate.{backend}.roas_true", s.roas_true, "float2")
    w.put(f"calibrate.{backend}.marginal_before", s.marginal_before, "float2")
    w.put(f"calibrate.{backend}.marginal_after", s.marginal_after, "float2")
    w.put(f"calibrate.{backend}.marginal_true", s.marginal_true, "float2")
    w.put(f"calibrate.{backend}.implied_before", s.implied_lift_before, "usd0")
    w.put(f"calibrate.{backend}.implied_after", s.implied_lift_after, "usd0")
    w.put(f"calibrate.{backend}.covers_before", "yes" if s.covers_before else "no", "text")
    w.put(f"calibrate.{backend}.covers_after", "yes" if s.covers_after else "no", "text")
    w.put(f"calibrate.{backend}.error_before", s.roas_before / s.roas_true - 1.0, "spct1")
    w.put(f"calibrate.{backend}.error_after", s.roas_after / s.roas_true - 1.0, "spct1")
    w.table(
        f"calibrate.{backend}.before_after",
        ["", "Before", "After", "Truth (simulated)"],
        ["text", "float2", "float2", "float2"],
        [
            ["Return on ad spend", s.roas_before, s.roas_after, s.roas_true],
            ["Interval lower", s.roas_before_lower, s.roas_after_lower, None],
            ["Interval upper", s.roas_before_upper, s.roas_after_upper, None],
            ["Marginal return", s.marginal_before, s.marginal_after, s.marginal_true],
        ],
    )
    w.table(
        f"calibrate.{backend}.lift",
        ["", "Dollars"],
        ["text", "usd0"],
        [
            ["Lift the model implied before", s.implied_lift_before],
            ["Lift the experiment found", s.experiment_lift],
            ["Lift the model implies after", s.implied_lift_after],
            ["True lift (simulated)", s.truth_lift],
        ],
    )
