"""The calibration loop: a posted lift result becomes a constraint on `own` and a lift test
measurement on `bayes`, and the pages show what it changed.

Before and after, per backend: the return estimate for the tested channel with its interval,
the truth beside it, the lift the model implies for the experiment against the lift the
experiment found, and the recovery error across the seeds of the demonstration condition.
The weight the experiment carries has its own interior test: if the calibrated fit reproduces
the experiment exactly, the weight dominates the data and the page says so.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import numpy as np
import polars as pl
from marginal_core.model import StrictModel
from marginal_evaluation import observed
from marginal_experiments import design_test, difference_in_differences, intervention_for
from marginal_mmm import LiftResult, MMMSpec, Model, fit
from marginal_mmm.own import fit_own
from marginal_sim import MarketSpec, national_truth_table, simulate_market


class BeforeAfter(StrictModel):
    backend: str
    channel: str
    roas_before: float
    roas_before_lower: float
    roas_before_upper: float
    roas_after: float
    roas_after_lower: float
    roas_after_upper: float
    roas_true: float
    marginal_before: float
    marginal_after: float
    marginal_true: float
    implied_lift_before: float
    implied_lift_after: float
    experiment_lift: float
    experiment_lower: float
    experiment_upper: float
    truth_lift: float
    covers_before: bool
    covers_after: bool


class WeightTest(StrictModel):
    residual_half: float
    residual_one: float
    residual_double: float
    interior: bool
    reason: str


def lift_from_registry(results: Path, geo_panel: pl.DataFrame) -> tuple[LiftResult, float]:
    """The posted difference in differences result as the constraint both backends receive, and
    the true lift beside it."""
    result = json.loads((results / "experiments" / "geo_result.json").read_text(encoding="utf-8"))
    design = json.loads((results / "experiments" / "geo_design.json").read_text(encoding="utf-8"))["design"]
    weights = geo_panel.filter(pl.col("week") == 0).select(["geo", "geo_weight"])
    treated = set(int(g) for g in design["treated_geos"])
    geo_share = float(weights.filter(pl.col("geo").is_in(list(treated)))["geo_weight"].sum())
    did = result["did"]
    lift = LiftResult(
        channel=str(design["channel"]),
        window_start_week=int(design["start_week"]),
        window_end_week=int(design["end_week"]),
        geo_share=geo_share,
        incremental_revenue=float(did["incremental_revenue"]),
        standard_error=float(did["standard_error"]),
        spend_change=float(design["spend_change"]),
        experiment_id=str(result["experiment_id"]),
        plan_hash=str(result["plan_hash"]),
    )
    return lift, float(result["truth"])


def before_after(
    model: Model, lift: LiftResult, truth: pl.DataFrame, truth_lift: float, experiment: dict[str, float]
) -> tuple[Model, BeforeAfter]:
    calibrated = model.calibrate([lift])
    before = next(e for e in model.intervals() if e.channel == lift.channel)
    after = next(e for e in calibrated.intervals() if e.channel == lift.channel)
    row = truth.filter(pl.col("channel") == lift.channel).row(0, named=True)
    roas_true = float(row["roas_true"])
    return calibrated, BeforeAfter(
        backend=model.backend,
        channel=lift.channel,
        roas_before=before.roas,
        roas_before_lower=before.roas_lower,
        roas_before_upper=before.roas_upper,
        roas_after=after.roas,
        roas_after_lower=after.roas_lower,
        roas_after_upper=after.roas_upper,
        roas_true=roas_true,
        marginal_before=before.marginal_return,
        marginal_after=after.marginal_return,
        marginal_true=float(row["marginal_return_true"]),
        implied_lift_before=model.implied_lift(lift),  # type: ignore[attr-defined]
        implied_lift_after=calibrated.implied_lift(lift),  # type: ignore[attr-defined]
        experiment_lift=lift.incremental_revenue,
        experiment_lower=experiment["lower"],
        experiment_upper=experiment["upper"],
        truth_lift=truth_lift,
        covers_before=before.roas_lower <= roas_true <= before.roas_upper,
        covers_after=after.roas_lower <= roas_true <= after.roas_upper,
    )


def weight_interior_test(panel: pl.DataFrame, spec: MMMSpec, lift: LiftResult) -> WeightTest:
    """Fit `own` with the experiment's weight halved, as stated, and doubled. The weight is an
    operating point when the residual against the experiment shrinks as the weight grows and is
    not zero at the stated weight; a zero residual means the weight, not the data, chose the fit."""
    residuals = {}
    for scale in (0.5, 1.0, 2.0):
        model = fit_own(panel, spec, lift_results=[lift], weight_scale=scale)
        residuals[scale] = float(model.calibration_residuals["residual"])
    half, one, double = abs(residuals[0.5]), abs(residuals[1.0]), abs(residuals[2.0])
    if one < 1e-6 * max(abs(lift.incremental_revenue), 1.0):
        return WeightTest(
            residual_half=residuals[0.5],
            residual_one=residuals[1.0],
            residual_double=residuals[2.0],
            interior=False,
            reason="the calibrated fit reproduces the experiment exactly; the weight dominates the data",
        )
    interior = half >= one >= double
    reason = (
        "the residual against the experiment shrinks as the weight grows and is not zero at the stated weight"
        if interior
        else "the residual does not shrink monotonically with the weight; the constraint is not binding smoothly"
    )
    return WeightTest(
        residual_half=residuals[0.5],
        residual_one=residuals[1.0],
        residual_double=residuals[2.0],
        interior=interior,
        reason=reason,
    )


def recovery_after_calibration(
    backend: str,
    seeds: list[int],
    base: MarketSpec,
    spec_for: Callable[[int], MMMSpec],
    progress: Callable[[str], None] | None = None,
) -> pl.DataFrame:
    """For each seed of the demonstration condition: run the geo test on that market, calibrate
    the backend with its result, and record the calibrated estimate against the truth."""
    rows = []
    for seed in seeds:
        spec = base.model_copy(update={"seed": seed, "intervention": None})
        geo, national, market = simulate_market(spec)
        truth = national_truth_table(national, market)
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
        # The model is fit on the market as it ran, test included: that is the panel an analyst has.
        model = fit(observed(national_after), spec_for(seed))
        calibrated = model.calibrate([lift])
        if progress:
            progress(f"{backend} calibrated seed {seed}")
        for est in calibrated.intervals():
            row = truth.filter(pl.col("channel") == est.channel).row(0, named=True)
            roas_true = float(row["roas_true"])
            rows.append(
                {
                    "backend": backend,
                    "seed": seed,
                    "channel": est.channel,
                    "roas_estimate": est.roas,
                    "roas_lower": est.roas_lower,
                    "roas_upper": est.roas_upper,
                    "roas_true": roas_true,
                    "relative_error": (est.roas - roas_true) / roas_true,
                    "covered": est.roas_lower <= roas_true <= est.roas_upper,
                    "marginal_estimate": est.marginal_return,
                    "marginal_true": float(row["marginal_return_true"]),
                }
            )
    return pl.DataFrame(rows)


def error_summary(rows: pl.DataFrame) -> dict[str, float]:
    errors = np.abs(rows["relative_error"].to_numpy())
    return {
        "median_abs_error": float(np.median(errors)),
        "coverage": float(rows["covered"].cast(pl.Float64).mean()),  # type: ignore[arg-type]
        "seeds": float(rows["seed"].n_unique()),
    }
