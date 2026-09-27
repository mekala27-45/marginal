"""The `own` backend: geometric adstock, Hill saturation, a log linear baseline with additive
media effects fit by bounded nonlinear least squares, a stated search for the transform
parameters under rolling origin validation, and block bootstrap intervals. Written in the
repository so every step can be read.

Sales in a week are organic demand times the week's controls (exp of a linear index over
trend, log price, promotion, holiday and Fourier seasonality, because demand is
multiplicative in the world) plus each channel's saturated adstocked spend times a non
negative coefficient. The coefficient on a channel is its ceiling in dollars, so a channel's
contribution in a week is the coefficient times the saturation value, and its response curve
at a steady weekly spend S is the coefficient times Hill(S).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import polars as pl
from marginal_core.seeds import rng
from scipy.optimize import least_squares, minimize

from marginal_mmm.interface import ChannelReturn, LiftResult, MMMSpec, design_columns
from marginal_mmm.transforms import geometric_adstock, half_life, hill, hill_slope

SCALE = 1e6  # sales are fit in millions so the solver sees numbers near one


@dataclass(frozen=True)
class ChannelParams:
    theta: float
    k: float
    s: float


@dataclass
class Solution:
    gamma: np.ndarray  # baseline index coefficients
    beta: np.ndarray  # channel ceilings, in millions
    rmse: float  # in millions


@dataclass
class OwnModel:
    spec: MMMSpec
    data_source: str
    weeks: np.ndarray
    sales: np.ndarray
    spend: np.ndarray  # T x C
    controls: np.ndarray  # T x P, the baseline design
    control_names: list[str]
    raw_controls: dict[str, np.ndarray]
    params: list[ChannelParams]
    ridge: float
    gamma: np.ndarray
    beta: np.ndarray  # C, in dollars
    saturated: np.ndarray  # T x C, Hill of adstocked spend
    bootstrap_beta: np.ndarray  # R x C, in dollars
    validation_error: float
    search: dict[str, float | int | str]
    lift_results: list[LiftResult] = field(default_factory=list)
    calibration_weight_scale: float = 1.0
    calibration_residuals: dict[str, float] = field(default_factory=dict)

    @property
    def backend(self) -> str:
        return "own"

    @property
    def spec_hash(self) -> str:
        return self.spec.hash

    @property
    def channels(self) -> tuple[str, ...]:
        return self.spec.channels

    @property
    def baseline(self) -> np.ndarray:
        return np.asarray(SCALE * np.exp(self.controls @ self.gamma))

    @property
    def fitted(self) -> np.ndarray:
        return np.asarray(self.baseline + self.saturated @ self.beta)

    # Outputs

    def contributions(self) -> pl.DataFrame:
        cols: dict[str, np.ndarray] = {"week": self.weeks, "baseline": self.baseline}
        for j, c in enumerate(self.channels):
            cols[c] = self.beta[j] * self.saturated[:, j]
        cols["fitted"] = self.fitted
        cols["sales"] = self.sales
        cols["residual"] = self.sales - self.fitted
        return pl.DataFrame(cols)

    def response_curve(self, channel: str, spend_grid: np.ndarray) -> np.ndarray:
        j = self.channels.index(channel)
        p = self.params[j]
        return np.asarray(self.beta[j] * hill(np.asarray(spend_grid, dtype=float), p.k, p.s))

    def marginal_return(self, channel: str, at_spend: float) -> float:
        j = self.channels.index(channel)
        p = self.params[j]
        return float(self.beta[j] * hill_slope(at_spend, p.k, p.s))

    def intervals(self) -> list[ChannelReturn]:
        n = self.spec.last_year_weeks
        tail = slice(len(self.weeks) - n, len(self.weeks))
        alpha = (1.0 - self.spec.level) / 2.0
        out = []
        for j, c in enumerate(self.channels):
            spend = float(self.spend[tail, j].sum())
            sat = float(self.saturated[tail, j].sum())
            inc = float(self.beta[j] * sat)
            draws = (
                self.bootstrap_beta[:, j] * sat / spend if spend > 0 else np.zeros(len(self.bootstrap_beta))
            )
            p = self.params[j]
            out.append(
                ChannelReturn(
                    channel=c,
                    roas=inc / spend if spend > 0 else 0.0,
                    roas_lower=float(np.quantile(draws, alpha)) if len(draws) else 0.0,
                    roas_upper=float(np.quantile(draws, 1.0 - alpha)) if len(draws) else 0.0,
                    marginal_return=self.marginal_return(c, spend / n),
                    carryover=p.theta,
                    half_life_weeks=half_life(p.theta),
                    half_saturation=p.k,
                    slope=p.s,
                    spend_last_year=spend,
                    incremental_last_year=inc,
                )
            )
        return out

    def diagnostics(self) -> dict[str, float | int | str]:
        resid = self.sales - self.fitted
        ss_res = float(np.sum(resid**2))
        ss_tot = float(np.sum((self.sales - self.sales.mean()) ** 2))
        out: dict[str, float | int | str] = {
            "backend": "own",
            "spec_hash": self.spec_hash,
            "data_source": self.data_source,
            "validation_error": self.validation_error,
            "ridge": self.ridge,
            "unexplained_variance_share": ss_res / ss_tot if ss_tot > 0 else 0.0,
            "residual_share_of_sales": float(np.mean(np.abs(resid)) / np.mean(self.sales)),
            "bootstrap_replicates": int(self.bootstrap_beta.shape[0]),
            "calibrated": int(bool(self.lift_results)),
        }
        out.update(self.search)
        out.update({f"calibration_{k}": v for k, v in self.calibration_residuals.items()})
        return out

    def calibrate(self, lift_results: list[LiftResult]) -> OwnModel:
        return fit_own(self.panel(), self.spec, data_source=self.data_source, lift_results=lift_results)

    def implied_lift(self, lift: LiftResult) -> float:
        """What the model says the experiment should have found: the channel's contribution in
        the window, scaled to the treated geos, times the spend change (a holdout removes it all)."""
        j = self.channels.index(lift.channel)
        window = (self.weeks >= lift.window_start_week) & (self.weeks <= lift.window_end_week)
        return float(-lift.spend_change * lift.geo_share * self.beta[j] * self.saturated[window, j].sum())

    def panel(self) -> pl.DataFrame:
        cols: dict[str, np.ndarray] = {"week": self.weeks, "sales": self.sales}
        for j, c in enumerate(self.channels):
            cols[f"spend_{c}"] = self.spend[:, j]
        for name in ("price_index", "promo", "holiday"):
            cols[name] = self.raw_controls[name]
        return pl.DataFrame(cols)


# Fitting


def _logit(share: float) -> float:
    share = min(max(share, 1e-6), 1.0 - 1e-6)
    return math.log(share / (1.0 - share))


def _unpack_one(v: np.ndarray, mean_spend: float) -> ChannelParams:
    u, w, z = v
    theta = 0.9 / (1.0 + math.exp(-u))
    ratio = 0.3 + 3.7 / (1.0 + math.exp(-w))
    s = 0.8 + 1.7 / (1.0 + math.exp(-z))
    return ChannelParams(theta=theta, k=float(mean_spend * ratio), s=float(s))


def _pack_one(p: ChannelParams, mean_spend: float) -> np.ndarray:
    return np.array(
        [_logit(p.theta / 0.9), _logit((p.k / mean_spend - 0.3) / 3.7), _logit((p.s - 0.8) / 1.7)]
    )


def _saturate(spend: np.ndarray, params: list[ChannelParams], max_lag: int) -> np.ndarray:
    out = np.empty_like(spend, dtype=float)
    for j, p in enumerate(params):
        out[:, j] = hill(geometric_adstock(spend[:, j], p.theta, max_lag), p.k, p.s)
    return out


Pseudo = tuple[np.ndarray, float, float]


class Solver:
    """Bounded nonlinear least squares for one design: y = exp(Z gamma) + H beta, beta >= 0,
    with a ridge on the seasonal part of gamma and an optional calibration pseudo observation.
    Warm started from the last solution, which is what makes the search affordable."""

    def __init__(self, y: np.ndarray, controls: np.ndarray, seasonal_mask: np.ndarray) -> None:
        self.y = y / SCALE
        self.z = controls
        self.pen_idx = np.flatnonzero(seasonal_mask)
        self.p = controls.shape[1]
        start = np.linalg.lstsq(controls, np.log(np.clip(self.y, 1e-6, None)), rcond=None)[0]
        start[0] += math.log(0.7)
        self.warm_gamma = start

    def solve(
        self, sat: np.ndarray, ridge: float, pseudo: Pseudo | None = None, rows: np.ndarray | None = None
    ) -> Solution:
        y = self.y if rows is None else self.y[rows]
        z = self.z if rows is None else self.z[rows]
        h = sat if rows is None else sat[rows]
        c = h.shape[1]
        p = self.p
        sqrt_ridge = math.sqrt(ridge)
        pen_idx = self.pen_idx
        n_pen = len(pen_idx)

        def residual(v: np.ndarray) -> np.ndarray:
            g, b = v[:p], v[p:]
            parts = [y - np.exp(z @ g) - h @ b, sqrt_ridge * g[pen_idx]]
            if pseudo is not None:
                row, target, weight = pseudo
                parts.append(np.array([math.sqrt(weight) * (row @ b - target / SCALE)]))
            return np.concatenate(parts)

        def jacobian(v: np.ndarray) -> np.ndarray:
            g = v[:p]
            e = np.exp(z @ g)
            top = np.hstack([-(e[:, None] * z), -h])
            pen = np.zeros((n_pen, p + c))
            pen[np.arange(n_pen), pen_idx] = sqrt_ridge
            blocks = [top, pen]
            if pseudo is not None:
                row, _, weight = pseudo
                extra = np.zeros((1, p + c))
                extra[0, p:] = math.sqrt(weight) * row
                blocks.append(extra)
            return np.vstack(blocks)

        v0 = np.concatenate([self.warm_gamma, np.full(c, 0.05)])
        lower = np.concatenate([np.full(p, -np.inf), np.zeros(c)])
        upper = np.full(p + c, np.inf)
        result = least_squares(
            residual, v0, jac=jacobian, bounds=(lower, upper), method="trf", max_nfev=60, xtol=1e-8
        )
        gamma, beta = result.x[:p], result.x[p:]
        if rows is None:
            self.warm_gamma = gamma
        fit = y - np.exp(z @ gamma) - h @ beta
        return Solution(gamma=gamma, beta=beta, rmse=float(math.sqrt(np.mean(fit**2))))


def _shape_penalty(params: list[ChannelParams], means: np.ndarray, spec: MMMSpec) -> float:
    """A stated penalty that keeps a transform near the shapes marketing responses have: half
    saturation near the channel's mean spend, a slope near the middle of its range, carryover
    of a few weeks at most. Without it the search wanders to the bounds to fit noise."""
    total = 0.0
    for p, m in zip(params, means, strict=True):
        total += math.log(p.k / m) ** 2 + ((p.s - 1.6) / 0.8) ** 2 + ((p.theta - 0.3) / 0.3) ** 2
    return spec.shape_penalty * total / len(params)


def _objective(solver: Solver, sat: np.ndarray, ridge: float, spec: MMMSpec, pseudo: Pseudo | None) -> float:
    """The search objective: rolling origin forecast error plus in sample error, both as shares
    of mean sales. The in sample term identifies a channel's shape; the forecast term stops a
    transform from fitting noise. Origins are spread over everything after the first year."""
    y = solver.y
    t = len(y)
    h = spec.validation_horizon_weeks
    origins = np.linspace(spec.validation_first_origin_week, t - h, spec.rolling_origins).astype(int)
    squared = []
    for cut in origins:
        sol = solver.solve(sat, ridge, pseudo, rows=np.arange(cut))
        pred = np.exp(solver.z[cut : cut + h] @ sol.gamma) + sat[cut : cut + h] @ sol.beta
        squared.append((y[cut : cut + h] - pred) ** 2)
    forecast = math.sqrt(np.mean(np.concatenate(squared)))
    in_sample = solver.solve(sat, ridge, pseudo).rmse
    return float((spec.validation_weight * forecast + in_sample) / np.mean(y))


def _pseudo_row(
    lift_results: list[LiftResult],
    sat: np.ndarray,
    weeks: np.ndarray,
    spec: MMMSpec,
    residual_sd: float,
    weight_scale: float,
) -> Pseudo | None:
    """The calibration pseudo observation: the modeled incremental revenue over the experiment's
    window and geos must match the experiment's estimate, weighted by the inverse of the
    experiment's variance relative to the fit's residual variance. The row multiplies the
    channel coefficients (in millions) and the target is in dollars."""
    if not lift_results:
        return None
    lift = lift_results[0]
    j = spec.channels.index(lift.channel)
    window = (weeks >= lift.window_start_week) & (weeks <= lift.window_end_week)
    row = np.zeros(len(spec.channels))
    row[j] = -lift.spend_change * lift.geo_share * sat[window, j].sum()
    weight = weight_scale * (residual_sd / max(lift.standard_error, 1e-9)) ** 2
    return row, lift.incremental_revenue, weight


def fit_own(
    panel: pl.DataFrame,
    spec: MMMSpec,
    *,
    data_source: str = "simulated",
    lift_results: list[LiftResult] | None = None,
    weight_scale: float = 1.0,
) -> OwnModel:
    lift_results = lift_results or []
    panel = panel.sort("week")
    weeks = panel["week"].to_numpy().astype(int)
    y = panel["sales"].to_numpy().astype(float)
    spend = np.column_stack([panel[f"spend_{c}"].to_numpy().astype(float) for c in spec.channels])
    controls, names = design_columns(panel, spec)
    seasonal_mask = np.array([n.startswith(("sin", "cos")) for n in names])
    solver = Solver(y, controls, seasonal_mask)
    means = spend.mean(axis=0)
    max_lag = spec.adstock_max_lag
    residual_sd = float(np.std(y)) * 0.05

    def pseudo_for(sat: np.ndarray) -> Pseudo | None:
        return _pseudo_row(lift_results, sat, weeks, spec, residual_sd, weight_scale)

    def score(trial: list[ChannelParams], ridge: float) -> float:
        sat = _saturate(spend, trial, max_lag)
        return _objective(solver, sat, ridge, spec, pseudo_for(sat)) + _shape_penalty(trial, means, spec)

    def in_sample(trial: list[ChannelParams], ridge: float) -> float:
        sat = _saturate(spend, trial, max_lag)
        return solver.solve(sat, ridge, pseudo_for(sat)).rmse / float(np.mean(solver.y)) + _shape_penalty(
            trial, means, spec
        )

    # 1. Coarse grid by coordinate descent, one channel at a time, on the in sample error (one
    # solve per point); the forecast term enters at the refinement, where it matters.
    params = [ChannelParams(theta=0.3, k=float(m), s=1.6) for m in means]
    ridge = spec.ridge_grid[1]
    best = in_sample(params, ridge)
    grid_evaluations = 0
    for _pass in range(spec.grid_passes):
        for j in range(len(spec.channels)):
            for theta in spec.grid_theta:
                for ratio in spec.grid_k_ratio:
                    for s in spec.grid_slope:
                        trial = list(params)
                        trial[j] = ChannelParams(theta=theta, k=float(ratio * means[j]), s=s)
                        err = in_sample(trial, ridge)
                        grid_evaluations += 1
                        if err < best:
                            best, params = err, trial

    # 2. The ridge penalty on the validation objective.
    ridge_errors = {lam: score(params, lam) for lam in spec.ridge_grid}
    ridge = min(ridge_errors, key=lambda lam: ridge_errors[lam])
    best = ridge_errors[ridge]

    # 3. Nelder-Mead from the grid optimum: one channel at a time, then all together.
    nm_evaluations = 0
    per_channel = max(spec.nelder_mead_evaluations // (3 * len(spec.channels) + 2), 20)
    for _pass in range(3):
        for j in range(len(spec.channels)):

            def one(v: np.ndarray, j: int = j) -> float:
                nonlocal nm_evaluations
                nm_evaluations += 1
                trial = list(params)
                trial[j] = _unpack_one(v, means[j])
                return score(trial, ridge)

            local = minimize(
                one,
                _pack_one(params[j], means[j]),
                method="Nelder-Mead",
                options={"maxfev": per_channel, "xatol": 1e-3, "fatol": 1e-7},
            )
            if local.fun < best:
                best = float(local.fun)
                params[j] = _unpack_one(local.x, means[j])

    def joint(v: np.ndarray) -> float:
        nonlocal nm_evaluations
        nm_evaluations += 1
        return score([_unpack_one(v[3 * j : 3 * j + 3], means[j]) for j in range(len(spec.channels))], ridge)

    start = np.concatenate([_pack_one(p, means[j]) for j, p in enumerate(params)])
    result = minimize(
        joint, start, method="Nelder-Mead", options={"maxfev": per_channel * 2, "xatol": 1e-3, "fatol": 1e-7}
    )
    if result.fun < best:
        params = [_unpack_one(result.x[3 * j : 3 * j + 3], means[j]) for j in range(len(spec.channels))]
        best = float(result.fun)

    # 4. The final fit; when calibrating, the residual scale sets the weight and the fit is redone.
    sat = _saturate(spend, params, max_lag)
    sol = solver.solve(sat, ridge, pseudo_for(sat))
    if lift_results:
        residual_sd = float(sol.rmse * SCALE)
        sol = solver.solve(sat, ridge, pseudo_for(sat))
    beta = sol.beta * SCALE

    # 5. Moving block bootstrap over weeks with the transforms fixed.
    t = len(y)
    block = spec.block_weeks
    r = rng(spec.seed, "own_block_bootstrap", data_source)
    n_blocks = math.ceil(t / block)
    replicates = np.zeros((spec.bootstrap_replicates, len(spec.channels)))
    pseudo = pseudo_for(sat)
    for i in range(spec.bootstrap_replicates):
        starts = r.integers(0, t - block + 1, n_blocks)
        idx = np.concatenate([np.arange(s0, s0 + block) for s0 in starts])[:t]
        replicates[i] = solver.solve(sat, ridge, pseudo, rows=idx).beta * SCALE

    calibration_residuals: dict[str, float] = {}
    if lift_results:
        lift = lift_results[0]
        j = spec.channels.index(lift.channel)
        window = (weeks >= lift.window_start_week) & (weeks <= lift.window_end_week)
        implied = float(-lift.spend_change * lift.geo_share * beta[j] * sat[window, j].sum())
        calibration_residuals = {
            "implied_lift": implied,
            "experiment_lift": lift.incremental_revenue,
            "residual": implied - lift.incremental_revenue,
            "weight_scale": weight_scale,
        }

    return OwnModel(
        spec=spec,
        data_source=data_source,
        weeks=weeks,
        sales=y,
        spend=spend,
        controls=controls,
        control_names=names,
        raw_controls={
            "price_index": panel["price_index"].to_numpy().astype(float),
            "promo": panel["promo"].to_numpy().astype(float),
            "holiday": panel["holiday"].to_numpy().astype(float),
        },
        params=params,
        ridge=ridge,
        gamma=sol.gamma,
        beta=beta,
        saturated=sat,
        bootstrap_beta=replicates,
        validation_error=best,
        search={
            "grid_evaluations": grid_evaluations,
            "nelder_mead_evaluations": nm_evaluations,
            "nelder_mead_converged": int(bool(result.success)),
            "ridge_grid_errors": ", ".join(f"{k:g}: {v:.4f}" for k, v in ridge_errors.items()),
        },
        lift_results=lift_results,
        calibration_weight_scale=weight_scale,
        calibration_residuals=calibration_residuals,
    )
