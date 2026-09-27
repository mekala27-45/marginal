"""The geo lift test: design, power by simulation, difference in differences, synthetic control
with placebo inference, all on markets where the truth is known.

Design picks treated geos by stratified assignment on pre period sales: geos are sorted by
their pre period sales, cut into strata of four, and one geo per stratum is drawn, so the
treated group spans the size distribution. Analysis runs two ways and reports both: a two
way fixed effects difference in differences on log sales with standard errors clustered by
geo, and a synthetic control for the treated aggregate with non negative weights fit on the
pre period and inference by placebo permutation over control geos.
"""

from __future__ import annotations

import math

import numpy as np
import polars as pl
from marginal_core.config import CHANNELS, POLICY
from marginal_core.model import StrictModel
from marginal_core.seeds import rng
from marginal_sim import Intervention, MarketSpec, simulate_market
from scipy.optimize import nnls
from scipy.stats import norm

from marginal_experiments.registration import GeoLiftDesign


class DiDResult(StrictModel):
    delta_log: float
    se_log: float
    incremental_revenue: float
    standard_error: float
    lower: float
    upper: float
    level: float
    treated_window_sales: float
    geos: int
    weeks_used: int


class SyntheticControlResult(StrictModel):
    incremental_revenue: float
    lower: float
    upper: float
    p_value: float
    placebo_permutations: int
    placebo_effects: list[float]
    weights: dict[int, float]
    pre_period_rmse: float
    level: float
    largest_weight: float


class PowerCell(StrictModel):
    spend_multiplier: float
    window_weeks: int
    simulations: int
    power: float
    mean_true_lift: float


# Design


def stratified_assignment(
    pre_sales: dict[int, float], treated_count: int, seed: int
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """One treated geo per stratum of pre period sales, drawn in sorted order from a named stream."""
    if treated_count <= 0 or treated_count >= len(pre_sales):
        raise ValueError("treated count must leave both groups non empty")
    ordered = sorted(pre_sales, key=lambda g: (pre_sales[g], g))
    strata = np.array_split(np.array(ordered), treated_count)
    r = rng(seed, "geo_assignment")
    treated = tuple(sorted(int(r.choice(stratum)) for stratum in strata))
    control = tuple(sorted(g for g in pre_sales if g not in treated))
    return treated, control


def design_test(
    geo_panel: pl.DataFrame,
    *,
    seed: int,
    channel: str = POLICY.lift_test_channel,
    spend_change: float = POLICY.lift_test_spend_change,
    window_weeks: int = POLICY.lift_test_length_weeks,
    pre_period_weeks: int = POLICY.lift_test_pre_period_weeks,
    treated_count: int = 10,
    end_week: int | None = None,
) -> GeoLiftDesign:
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel}")
    last = int(geo_panel["week"].max()) if end_week is None else end_week  # type: ignore[arg-type]
    start = last - window_weeks + 1
    pre = geo_panel.filter((pl.col("week") < start) & (pl.col("week") >= start - pre_period_weeks))
    pre_sales = {
        int(r["geo"]): float(r["sales"])
        for r in pre.group_by("geo").agg(pl.col("sales").sum()).iter_rows(named=True)
    }
    treated, control = stratified_assignment(pre_sales, treated_count, seed)
    return GeoLiftDesign(
        name=f"{channel} holdout, {window_weeks} weeks, {treated_count} geos",
        channel=channel,
        spend_change=spend_change,
        assignment="stratified",
        treated_geos=treated,
        control_geos=control,
        pre_period_weeks=pre_period_weeks,
        start_week=start,
        end_week=last,
        placebo_permutations=POLICY.placebo_permutations,
        interval_level=POLICY.interval_level,
    )


def intervention_for(design: GeoLiftDesign) -> Intervention:
    return Intervention(
        channel=design.channel,
        geos=design.treated_geos,
        start_week=design.start_week,
        end_week=design.end_week,
        spend_multiplier=1.0 + design.spend_change,
    )


# Analysis


def _window_frame(geo_panel: pl.DataFrame, design: GeoLiftDesign) -> pl.DataFrame:
    first = design.start_week - design.pre_period_weeks
    return geo_panel.filter((pl.col("week") >= first) & (pl.col("week") <= design.end_week)).sort(
        ["geo", "week"]
    )


def difference_in_differences(geo_panel: pl.DataFrame, design: GeoLiftDesign) -> DiDResult:
    """Two way fixed effects on log sales, clustered by geo, converted to dollars over the window."""
    frame = _window_frame(geo_panel, design)
    geos = np.sort(frame["geo"].unique().to_numpy())
    weeks = np.sort(frame["week"].unique().to_numpy())
    g_index = {g: i for i, g in enumerate(geos)}
    w_index = {w: i for i, w in enumerate(weeks)}
    y = np.full((len(geos), len(weeks)), np.nan)
    for r in frame.iter_rows(named=True):
        y[g_index[int(r["geo"])], w_index[int(r["week"])]] = math.log(max(float(r["sales"]), 1e-9))
    if np.isnan(y).any():
        raise ValueError("the panel is not balanced over the analysis window")
    treated = np.array([g in design.treated_geos for g in geos])
    in_window = np.array([design.start_week <= w <= design.end_week for w in weeks])
    d = np.outer(treated, in_window).astype(float)
    y_t = y - y.mean(axis=1, keepdims=True) - y.mean(axis=0, keepdims=True) + y.mean()
    d_t = d - d.mean(axis=1, keepdims=True) - d.mean(axis=0, keepdims=True) + d.mean()
    denom = float((d_t**2).sum())
    delta = float((d_t * y_t).sum() / denom)
    resid = y_t - delta * d_t
    scores = (d_t * resid).sum(axis=1)
    g = len(geos)
    se = math.sqrt(g / (g - 1) * float((scores**2).sum()) / denom**2)
    observed = float(
        frame.filter(pl.col("geo").is_in(list(design.treated_geos)) & (pl.col("week") >= design.start_week))[
            "sales"
        ].sum()
    )
    # A holdout lowers treated sales by the factor exp(delta): the channel's incremental revenue is
    # the counterfactual minus what was observed. An increase is read the other way round.
    if design.spend_change < 0:
        incremental = observed * (math.exp(-delta) - 1.0)
    else:
        incremental = observed * (1.0 - math.exp(-delta))
    se_dollars = observed * math.exp(-delta) * se
    z = float(norm.ppf(1.0 - (1.0 - design.interval_level) / 2.0))
    return DiDResult(
        delta_log=delta,
        se_log=se,
        incremental_revenue=incremental,
        standard_error=se_dollars,
        lower=incremental - z * se_dollars,
        upper=incremental + z * se_dollars,
        level=design.interval_level,
        treated_window_sales=observed,
        geos=g,
        weeks_used=len(weeks),
    )


def _matrix(frame: pl.DataFrame, geos: list[int]) -> tuple[np.ndarray, np.ndarray]:
    weeks = np.sort(frame["week"].unique().to_numpy())
    pivot = frame.filter(pl.col("geo").is_in(geos)).pivot(on="geo", index="week", values="sales").sort("week")
    matrix = np.column_stack([pivot[str(g)].to_numpy().astype(float) for g in geos])
    return weeks, matrix


def _synthetic_effect(
    weeks: np.ndarray, treated_sum: np.ndarray, controls: np.ndarray, design: GeoLiftDesign
) -> tuple[float, np.ndarray, float]:
    pre = weeks < design.start_week
    post = (weeks >= design.start_week) & (weeks <= design.end_week)
    weights, _ = nnls(controls[pre], treated_sum[pre], maxiter=10_000)
    synthetic = controls @ weights
    rmse = float(np.sqrt(np.mean((treated_sum[pre] - synthetic[pre]) ** 2)))
    effect = float((treated_sum[post] - synthetic[post]).sum())
    return effect, weights, rmse


def synthetic_control(geo_panel: pl.DataFrame, design: GeoLiftDesign, seed: int) -> SyntheticControlResult:
    """Non negative weights on control geos fit to the treated aggregate over the pre period; the
    effect is the window gap in dollars; placebo permutation draws groups of the same size from
    the controls and repeats the fit, and the interval is the placebo distribution around the
    estimate."""
    frame = _window_frame(geo_panel, design)
    treated = list(design.treated_geos)
    controls = list(design.control_geos)
    weeks, t_matrix = _matrix(frame, treated)
    _, c_matrix = _matrix(frame, controls)
    treated_sum = t_matrix.sum(axis=1)
    gap, weights, rmse = _synthetic_effect(weeks, treated_sum, c_matrix, design)
    # A holdout makes the gap negative; the channel's incremental revenue is the size of it.
    sign = -1.0 if design.spend_change < 0 else 1.0
    effect = sign * gap
    r = rng(seed, "placebo", design.plan_hash)
    placebos: list[float] = []
    k = len(treated)
    for _ in range(design.placebo_permutations):
        chosen = np.sort(r.choice(len(controls), size=k, replace=False))
        pseudo_treated = c_matrix[:, chosen].sum(axis=1)
        remaining = np.delete(c_matrix, chosen, axis=1)
        pseudo_gap, _, _ = _synthetic_effect(weeks, pseudo_treated, remaining, design)
        placebos.append(sign * pseudo_gap)
    placebo = np.array(placebos)
    p_value = float(np.mean(np.abs(placebo) >= abs(effect)))
    alpha = (1.0 - design.interval_level) / 2.0
    lower = effect + float(np.quantile(placebo, alpha))
    upper = effect + float(np.quantile(placebo, 1.0 - alpha))
    return SyntheticControlResult(
        incremental_revenue=effect,
        lower=lower,
        upper=upper,
        p_value=p_value,
        placebo_permutations=len(placebos),
        placebo_effects=[float(v) for v in placebo],
        weights={int(g): float(w) for g, w in zip(controls, weights, strict=True)},
        pre_period_rmse=rmse,
        level=design.interval_level,
        largest_weight=float(weights.max() / weights.sum()) if weights.sum() > 0 else 0.0,
    )


# Truth and power


def true_lift(spec: MarketSpec, design: GeoLiftDesign) -> float:
    """The sales the intervention removed (or added) in the treated geos over the window, known
    because the market with and without it shares every random draw."""
    without = simulate_market(spec.model_copy(update={"intervention": None}))[0]
    with_test = simulate_market(spec.model_copy(update={"intervention": intervention_for(design)}))[0]
    treated = list(design.treated_geos)
    mask = (
        pl.col("geo").is_in(treated)
        & (pl.col("week") >= design.start_week)
        & (pl.col("week") <= design.end_week)
    )
    before = float(without.filter(mask)["sales"].sum())
    after = float(with_test.filter(mask)["sales"].sum())
    return before - after if design.spend_change < 0 else after - before


def power_curve(
    base: MarketSpec,
    design: GeoLiftDesign,
    *,
    spend_multipliers: tuple[float, ...] = (0.0, 0.5, 0.75),
    window_lengths: tuple[int, ...] = (4, 8),
    simulations: int = 60,
    first_seed: int = 5000,
) -> list[PowerCell]:
    """Share of simulated tests whose difference in differences interval excludes zero, per
    effect size (how much of the channel's spend the test removes) and test length."""
    cells: list[PowerCell] = []
    for multiplier in spend_multipliers:
        for length in window_lengths:
            rejections = 0
            lifts = []
            for i in range(simulations):
                seed = first_seed + i
                spec = base.model_copy(update={"seed": seed, "intervention": None})
                shorter = design.model_copy(
                    update={"start_week": design.end_week - length + 1, "spend_change": multiplier - 1.0}
                )
                tested = spec.model_copy(update={"intervention": intervention_for(shorter)})
                geo, _, _ = simulate_market(tested)
                result = difference_in_differences(geo, shorter)
                if result.lower > 0 or result.upper < 0:
                    rejections += 1
                lifts.append(true_lift(spec, shorter))
            cells.append(
                PowerCell(
                    spend_multiplier=multiplier,
                    window_weeks=length,
                    simulations=simulations,
                    power=rejections / simulations,
                    mean_true_lift=float(np.mean(lifts)),
                )
            )
    return cells
