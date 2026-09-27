"""The `bayes` backend: the model family of `own`, fit as a Bayesian model by PyMC-Marketing's
`MMM`, with posterior intervals in place of the block bootstrap.

The library fits in scaled units: sales divided by the largest week's sales, and each
channel's spend divided by that channel's largest week. In those units

    sales_t = intercept + controls_t . gamma + yearly seasonality_t
              + sum over channels of beta * Hill(adstock(spend)_t; kappa, s) + noise

Adstock is `GeometricAdstock` with normalized weights, so a constant weekly spend adstocks to
itself. The library's `l_max` counts weights (lags 0 to l_max - 1) where `own` and the
simulator count lags (0 to max_lag), so `l_max` is `spec.adstock_max_lag + 1` to cover the
same thirteen lags. The library's `alpha` is the geometric retention rate theta.

Saturation is `HillSaturation`, beta * x^s / (kappa^s + x^s). That is the repository's Hill
curve with the coefficient in front, so beta is the channel's ceiling and kappa its half
saturation point, the convention `own` uses; `LogisticSaturation` was not needed.

The baseline is an intercept, the controls of `design_columns` without its intercept (trend,
log price, promotion, holiday, each centered so the intercept is the baseline at average
conditions), and the library's yearly Fourier seasonality of order `spec.fourier_order` in
place of the design's sin and cos columns. It is additive here, where `own` exponentiates
it; the recovery study grades what that difference costs.

The channel priors are in PRIORS; the intercept, controls, seasonality and noise keep the
library's defaults on the scaled sales (Normal(0, 2), Normal(0, 2), Laplace(0, 1) and a
HalfNormal(2) noise scale). Sampling is NUTS with a diagonal mass matrix, on one core so
chains run in sequence and a seed fixes every draw.

Outputs are in dollars. Contributions are the posterior means of the library's
`*_original_scale` deterministics. The response curve at a steady weekly spend S is
recomputed in numpy from posterior mean parameters: S is divided by the channel's scale on
the way in, the Hill value is multiplied by beta and by the sales scale on the way out, and
no carryover factor is needed because the adstock weights sum to one. The return is the
posterior median of incremental revenue over spend, so it always sits inside its interval.
"""

from __future__ import annotations

import copy
import math
import time
import warnings
from dataclasses import dataclass, field

import arviz as az
import numpy as np
import pandas as pd
import polars as pl
import xarray as xr
from pymc_extras.prior import Prior
from pymc_marketing.mmm import MMM, GeometricAdstock, HillSaturation

from marginal_mmm.interface import ChannelReturn, LiftResult, MMMSpec, design_columns
from marginal_mmm.transforms import half_life, hill

DATE = "date"
CONTROLS = ("trend", "log_price", "promo", "holiday")
CHANNEL_PARAMETERS = ("adstock_alpha", "saturation_beta", "saturation_kappa", "saturation_slope")
INIT = "jitter+adapt_diag"
"""PyMC's default, stated so the record says what ran. A dense mass matrix was tried and did
worse: what slows the sampler is curvature that changes across the Hill curves' posterior,
which no single matrix fits."""

# The channel priors, keyed by the library's variable names. `Prior` comes from an untyped
# package, so mypy sees these values as Any.
PRIORS: dict[str, Prior] = {
    # The ceiling, as a share of the largest week's sales.
    "saturation_beta": Prior("HalfNormal", sigma=0.25, dims="channel"),
    # Half saturation, as a multiple of the channel's mean weekly spend: centered on the mean
    # week, the shape `own` assumes. `_priors` moves the center into the library's units, a
    # share of the channel's largest week.
    "saturation_kappa": Prior("LogNormal", mu=0.0, sigma=0.4, dims="channel"),
    # The Hill slope: S shaped, rarely below one or above two and a half.
    "saturation_slope": Prior("Gamma", mu=1.6, sigma=0.4, dims="channel"),
    # Weekly retention: a few weeks of carryover at most.
    "adstock_alpha": Prior("Beta", alpha=2, beta=3, dims="channel"),
}


def describe_priors() -> str:
    stated = "; ".join(
        f"{name} {prior.distribution}({', '.join(f'{k}={v}' for k, v in prior.parameters.items())})"
        for name, prior in PRIORS.items()
    )
    return f"{stated} (beta in largest weeks of sales, kappa in mean weeks of the channel's spend)"


def _priors(spend: np.ndarray) -> dict[str, Prior]:
    """PRIORS in the library's units. The half saturation prior is stated in mean weeks of the
    channel's spend and the library measures spend in largest weeks, so its log center moves by
    the log of each channel's mean week over its largest week (the library's scale, floored at
    one dollar as the library floors it)."""
    priors = copy.deepcopy(PRIORS)
    kappa = priors["saturation_kappa"]
    share = spend.mean(axis=0) / np.maximum(np.abs(spend).max(axis=0), 1.0)
    # A channel that never spent has no mean week; a tiny share keeps the prior defined.
    center = kappa.parameters["mu"] + np.log(np.clip(share, 1e-3, None))
    priors["saturation_kappa"] = Prior(
        kappa.distribution,
        mu=xr.DataArray(center, dims=("channel",)),
        sigma=kappa.parameters["sigma"],
        dims="channel",
    )
    return priors


@dataclass
class BayesModel:
    spec: MMMSpec
    data_source: str
    frame: pl.DataFrame  # the panel the model was fit on, sorted by week, for refits
    weeks: np.ndarray
    sales: np.ndarray
    spend: np.ndarray  # T x C, dollars
    channel_scale: np.ndarray  # C, the library's divisor for each channel's spend
    target_scale: float  # the library's divisor for sales
    alpha: np.ndarray  # C, posterior mean retention rate
    kappa: np.ndarray  # C, posterior mean half saturation, in scaled spend
    slope: np.ndarray  # C, posterior mean Hill slope
    beta: np.ndarray  # C, posterior mean ceiling, in scaled sales
    contribution_draws: np.ndarray  # S x T x C, dollars, every posterior draw
    baseline: np.ndarray  # T, posterior mean, dollars
    fitted: np.ndarray  # T, posterior mean, dollars
    sampling: dict[str, float | int | str]
    mmm: MMM = field(repr=False, compare=False)  # the fitted library object, for plots and the trace
    lift_results: list[LiftResult] = field(default_factory=list)
    calibration_residuals: dict[str, float] = field(default_factory=dict)

    @property
    def backend(self) -> str:
        return "bayes"

    @property
    def spec_hash(self) -> str:
        return self.spec.hash

    @property
    def channels(self) -> tuple[str, ...]:
        return self.spec.channels

    @property
    def contribution_mean(self) -> np.ndarray:
        return np.asarray(self.contribution_draws.mean(axis=0))

    # Outputs

    def contributions(self) -> pl.DataFrame:
        mean = self.contribution_mean
        cols: dict[str, np.ndarray] = {"week": self.weeks, "baseline": self.baseline}
        for j, c in enumerate(self.channels):
            cols[c] = mean[:, j]
        cols["fitted"] = self.fitted
        cols["sales"] = self.sales
        cols["residual"] = self.sales - self.fitted
        return pl.DataFrame(cols)

    def response_curve(self, channel: str, spend_grid: np.ndarray) -> np.ndarray:
        """Weekly incremental revenue at a steady weekly spend, at the posterior mean parameters."""
        j = self.channels.index(channel)
        scaled = np.asarray(spend_grid, dtype=float) / self.channel_scale[j]
        return np.asarray(self.target_scale * self.beta[j] * hill(scaled, self.kappa[j], self.slope[j]))

    def ceiling_draws(self) -> np.ndarray:
        """Posterior draws of each channel's ceiling in dollars (draws by channel), for a plan's
        expected outcome interval."""
        idata = self.mmm.idata
        if idata is None:
            raise RuntimeError("the model has no trace")
        posterior = idata["posterior"]
        columns = [f"spend_{c}" for c in self.channels]
        beta = (
            posterior["saturation_beta"]
            .sel(channel=columns)
            .stack(sample=("chain", "draw"))
            .transpose("sample", "channel")
        )
        return np.asarray(beta.to_numpy(), dtype=float) * self.target_scale

    def marginal_return(self, channel: str, at_spend: float) -> float:
        """The slope of the response curve by a central difference, one sided at zero spend."""
        x = max(float(at_spend), 0.0)
        step = max(1e-4 * x, 1.0)
        low, high = max(x - step, 0.0), x + step
        curve = self.response_curve(channel, np.array([low, high]))
        return float((curve[1] - curve[0]) / (high - low))

    def intervals(self) -> list[ChannelReturn]:
        """Per channel over the last year. The return is the posterior median of incremental
        revenue over spend, so it always sits inside its interval; the incremental revenue is
        that return times the spend, the posterior median of the channel's contribution."""
        start = max(len(self.weeks) - self.spec.last_year_weeks, 0)
        n = len(self.weeks) - start
        tail = 1.0 - (1.0 - self.spec.level) / 2.0
        out = []
        for j, c in enumerate(self.channels):
            spend = float(self.spend[start:, j].sum())
            inc_draws = self.contribution_draws[:, start:, j].sum(axis=1)
            draws = inc_draws / spend if spend > 0 else np.zeros(len(inc_draws))
            roas = float(np.median(draws))
            theta = float(self.alpha[j])
            out.append(
                ChannelReturn(
                    channel=c,
                    roas=roas,
                    roas_lower=float(np.quantile(draws, 1.0 - tail)),
                    roas_upper=float(np.quantile(draws, tail)),
                    marginal_return=self.marginal_return(c, spend / n),
                    carryover=theta,
                    half_life_weeks=half_life(theta),
                    half_saturation=float(self.kappa[j] * self.channel_scale[j]),
                    slope=float(self.slope[j]),
                    spend_last_year=spend,
                    incremental_last_year=roas * spend,
                )
            )
        return out

    def diagnostics(self) -> dict[str, float | int | str]:
        resid = self.sales - self.fitted
        ss_res = float(np.sum(resid**2))
        ss_tot = float(np.sum((self.sales - self.sales.mean()) ** 2))
        out: dict[str, float | int | str] = {
            "backend": "bayes",
            "spec_hash": self.spec_hash,
            "data_source": self.data_source,
            "unexplained_variance_share": ss_res / ss_tot if ss_tot > 0 else 0.0,
            "residual_share_of_sales": float(np.mean(np.abs(resid)) / np.mean(self.sales)),
            "calibrated": int(bool(self.lift_results)),
        }
        out.update(self.sampling)
        out.update({f"calibration_{k}": v for k, v in self.calibration_residuals.items()})
        return out

    def calibrate(self, lift_results: list[LiftResult]) -> BayesModel:
        return fit_bayes(self.panel(), self.spec, data_source=self.data_source, lift_results=lift_results)

    def implied_lift(self, lift: LiftResult) -> float:
        """What the model says the experiment should have found: the channel's posterior mean
        contribution over the window, scaled to the treated geos, times the spend change (a
        holdout removes it all)."""
        j = self.channels.index(lift.channel)
        window = (self.weeks >= lift.window_start_week) & (self.weeks <= lift.window_end_week)
        return float(-lift.spend_change * lift.geo_share * self.contribution_mean[window, j].sum())

    def panel(self) -> pl.DataFrame:
        return self.frame


# Fitting


def _dates(panel: pl.DataFrame) -> pd.DatetimeIndex:
    """Calendar weeks for the library's yearly seasonality. A panel without them gets weekly
    dates from a fixed Monday, which moves the seasonal phase but not the fit."""
    if "week_start" in panel.columns:
        return pd.DatetimeIndex(pd.to_datetime(panel["week_start"].to_numpy()))
    return pd.DatetimeIndex(
        pd.Timestamp("2000-01-03") + pd.to_timedelta(7 * panel["week"].to_numpy(), unit="D")
    )


def _library_data(panel: pl.DataFrame, spec: MMMSpec) -> tuple[pd.DataFrame, pd.Series[float]]:
    design, names = design_columns(panel, spec)
    x = pd.DataFrame({DATE: _dates(panel)})
    for c in spec.channels:
        x[f"spend_{c}"] = panel[f"spend_{c}"].to_numpy().astype(float)
    for name in CONTROLS:
        column = design[:, names.index(name)]
        x[name] = column - column.mean()
    y = pd.Series(panel["sales"].to_numpy().astype(float), name="sales")
    return x, y


def _build(spec: MMMSpec, channel_columns: list[str], spend: np.ndarray) -> MMM:
    with warnings.catch_warnings():
        # The legacy class is the one this backend is written against; the library announces its
        # removal in 0.20 in favour of pymc_marketing.mmm.multidimensional.MMM.
        warnings.filterwarnings("ignore", message=r"\s*The MMM class is deprecated", category=FutureWarning)
        return MMM(
            date_column=DATE,
            channel_columns=channel_columns,
            control_columns=list(CONTROLS),
            adstock=GeometricAdstock(l_max=spec.adstock_max_lag + 1, normalize=True),
            saturation=HillSaturation(),
            yearly_seasonality=spec.fourier_order if spec.fourier_order > 0 else None,
            model_config=_priors(spend),
        )


def _lift_rows(
    lift_results: list[LiftResult], weeks: np.ndarray, spend: np.ndarray, spec: MMMSpec
) -> pd.DataFrame:
    """One row per experiment in national weekly dollars; the library divides x and delta_x by
    the channel's scale and delta_y and sigma by the sales scale itself. x is the channel's mean
    weekly spend over the window, and the experiment's revenue is turned into a national weekly
    change by dividing by the treated geos' share and the window's weeks."""
    rows = []
    for lift in lift_results:
        j = spec.channels.index(lift.channel)
        window = (weeks >= lift.window_start_week) & (weeks <= lift.window_end_week)
        n = int(window.sum())
        if n == 0:
            raise ValueError(f"experiment {lift.experiment_id}: no panel week falls in its window")
        if lift.spend_change == 0.0:
            raise ValueError(
                f"experiment {lift.experiment_id}: a zero spend change says nothing about the curve"
            )
        if lift.incremental_revenue <= 0.0:
            # The library's lift likelihood is a Gamma on the size of the change and requires the
            # change in revenue to have the sign of the change in spend.
            raise ValueError(
                f"experiment {lift.experiment_id}: the bayes backend needs a positive incremental revenue"
            )
        x = float(spend[window, j].mean())
        per_week = lift.geo_share * n
        rows.append(
            {
                "channel": f"spend_{lift.channel}",
                "x": x,
                "delta_x": lift.spend_change * x,
                "delta_y": math.copysign(lift.incremental_revenue / per_week, lift.spend_change),
                "sigma": lift.standard_error / per_week,
            }
        )
    return pd.DataFrame(rows)


def _check_lift_scaling(mmm: MMM) -> None:
    """The library scales lift rows with the transformers it fits beside the model, not with the
    scales inside the graph; the two must agree or the rows land in the wrong units."""
    channel = np.asarray(mmm.channel_transformer["scaler"].scale_, dtype=float)
    target = float(np.asarray(mmm.target_transformer["scaler"].scale_, dtype=float)[0])
    if not (
        np.allclose(channel, np.asarray(mmm.channel_scale, dtype=float))
        and math.isclose(target, mmm.target_scale)
    ):
        raise RuntimeError(
            "PyMC-Marketing scales lift rows differently from its model; the rows would be misread"
        )


def _channel_mean(posterior: xr.Dataset, name: str, channel_columns: list[str]) -> np.ndarray:
    return np.asarray(
        posterior[name].sel(channel=channel_columns).mean(("chain", "draw")).to_numpy(), dtype=float
    )


def fit_bayes(
    panel: pl.DataFrame,
    spec: MMMSpec,
    *,
    data_source: str = "simulated",
    lift_results: list[LiftResult] | None = None,
) -> BayesModel:
    lift_results = list(lift_results or [])
    keep = [
        "week",
        "week_start",
        "sales",
        *[f"spend_{c}" for c in spec.channels],
        "price_index",
        "promo",
        "holiday",
    ]
    frame = panel.sort("week").select([c for c in keep if c in panel.columns])
    x, y = _library_data(frame, spec)
    channel_columns = [f"spend_{c}" for c in spec.channels]
    weeks = frame["week"].to_numpy().astype(int)
    spend = x[channel_columns].to_numpy(dtype=float)

    mmm = _build(spec, channel_columns, spend)
    mmm.build_model(x, y)
    if lift_results:
        _check_lift_scaling(mmm)
        mmm.add_lift_test_measurements(_lift_rows(lift_results, weeks, spend, spec))

    started = time.perf_counter()
    idata = mmm.fit(
        x,
        y,
        progressbar=False,
        random_seed=spec.seed,
        chains=spec.chains,
        draws=spec.draws,
        tune=spec.tune,
        target_accept=spec.target_accept,
        cores=1,
        init=INIT,
    )
    wall = time.perf_counter() - started

    posterior = idata["posterior"]
    stats = idata["sample_stats"]
    target_scale = float(mmm.target_scale)
    contributions = (
        posterior["channel_contribution_original_scale"]
        .sel(channel=channel_columns)
        .transpose("chain", "draw", "date", "channel")
        .to_numpy()
    )
    contribution_draws = np.asarray(contributions, dtype=float).reshape(-1, len(weeks), len(channel_columns))
    baseline = float(posterior["intercept"].mean()) * target_scale + np.asarray(
        posterior["control_contribution_original_scale"].sum("control").mean(("chain", "draw")).to_numpy(),
        dtype=float,
    )
    if "yearly_seasonality_contribution_original_scale" in posterior:
        baseline = baseline + np.asarray(
            posterior["yearly_seasonality_contribution_original_scale"].mean(("chain", "draw")).to_numpy(),
            dtype=float,
        )
    fitted = np.asarray(posterior["y_original_scale"].mean(("chain", "draw")).to_numpy(), dtype=float)

    divergences = int(stats["diverging"].sum())
    # arviz leaves rhat unannotated.
    rhat = az.rhat(idata, var_names=list(CHANNEL_PARAMETERS))  # type: ignore[no-untyped-call]
    max_rhat = max(float(rhat[name].max()) for name in CHANNEL_PARAMETERS)
    # A rhat that is not a number means a chain never moved, which is a failure, not a pass.
    over = {
        "divergences": divergences > spec.max_divergences,
        "max_rhat": not math.isfinite(max_rhat) or max_rhat > spec.max_rhat,
    }
    failed = [name for name, is_over in over.items() if is_over]
    library = stats.attrs.get("inference_library", "pymc")
    version = stats.attrs.get("inference_library_version", "")
    sampling: dict[str, float | int | str] = {
        "chains": int(posterior.sizes["chain"]),
        "draws": int(posterior.sizes["draw"]),
        "tune": int(stats.attrs.get("tuning_steps", spec.tune)),
        "divergences": divergences,
        "max_rhat": max_rhat,
        "sampler": f"{library} {version} NUTS, {INIT}",
        "sampling_seconds": round(float(stats.attrs.get("sampling_time", wall)), 1),
        "fit_status": "failed ceilings" if failed else "ok",
        "failed_ceilings": ", ".join(failed),
        "saturation": "hill",
        "adstock": f"geometric, normalized, lags 0 to {spec.adstock_max_lag}",
        "priors": describe_priors(),
    }

    model = BayesModel(
        spec=spec,
        data_source=data_source,
        frame=frame,
        weeks=weeks,
        sales=y.to_numpy(dtype=float),
        spend=spend,
        channel_scale=np.asarray(mmm.channel_scale, dtype=float),
        target_scale=target_scale,
        alpha=_channel_mean(posterior, "adstock_alpha", channel_columns),
        kappa=_channel_mean(posterior, "saturation_kappa", channel_columns),
        slope=_channel_mean(posterior, "saturation_slope", channel_columns),
        beta=_channel_mean(posterior, "saturation_beta", channel_columns),
        contribution_draws=contribution_draws,
        baseline=baseline,
        fitted=fitted,
        sampling=sampling,
        mmm=mmm,
        lift_results=lift_results,
    )
    if lift_results:
        lift = lift_results[0]
        implied = model.implied_lift(lift)
        model.calibration_residuals = {
            "implied_lift": implied,
            "experiment_lift": lift.incremental_revenue,
            "residual": implied - lift.incremental_revenue,
            "rows": float(len(lift_results)),
        }
    return model
