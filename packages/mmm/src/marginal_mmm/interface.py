"""One interface for both mix model backends.

    fit(panel, spec) -> Model
    contributions(model) -> frame of week by channel
    response_curve(model, channel, spend_grid) -> incremental revenue at each steady spend
    marginal_return(model, channel, at_spend) -> the slope there
    intervals(model) -> per channel return with its interval
    calibrate(model, lift_results) -> a refit that honours the experiments

Every output carries the backend, the spec hash and the data source that produced it.
"""

from __future__ import annotations

from typing import Literal, Protocol

import numpy as np
import polars as pl
from marginal_core.config import CHANNELS, POLICY
from marginal_core.hashing import design_hash
from marginal_core.model import StrictModel

Backend = Literal["own", "bayes"]


class MMMSpec(StrictModel):
    backend: Backend = "own"
    channels: tuple[str, ...] = CHANNELS
    adstock_max_lag: int = 13
    fourier_order: int = 3
    rolling_origins: int = POLICY.rolling_origins
    validation_horizon_weeks: int = 13
    validation_first_origin_week: int = 52
    validation_weight: float = 1.0
    shape_penalty: float = 0.001
    """Weight of the stated penalty that keeps transforms near marketing response shapes."""
    """Weight of the forecast error against the in sample error in the transform search."""
    bootstrap_replicates: int = POLICY.bootstrap_replicates
    block_weeks: int = POLICY.bootstrap_block_weeks
    grid_theta: tuple[float, ...] = (0.1, 0.3, 0.5, 0.7)
    grid_k_ratio: tuple[float, ...] = (0.5, 0.8, 1.2, 2.0)
    grid_slope: tuple[float, ...] = (1.0, 1.6, 2.4)
    grid_passes: int = 1
    ridge_grid: tuple[float, ...] = (0.0001, 0.001, 0.01, 0.1)
    nelder_mead_evaluations: int = 1000
    level: float = POLICY.interval_level
    last_year_weeks: int = 52
    seed: int = 0
    # bayes only
    chains: int = 2
    draws: int = 400
    tune: int = 400
    target_accept: float = 0.9
    max_divergences: int = 20
    max_rhat: float = 1.05

    @property
    def hash(self) -> str:
        return design_hash(self.model_dump(mode="json"))


class LiftResult(StrictModel):
    """A posted experiment result: the incremental revenue the channel caused in the tested
    geos over the test window, with its standard error, and the geos' share of the market."""

    channel: str
    window_start_week: int
    window_end_week: int
    geo_share: float
    incremental_revenue: float
    standard_error: float
    spend_change: float
    experiment_id: str
    plan_hash: str


class ChannelReturn(StrictModel):
    channel: str
    roas: float
    roas_lower: float
    roas_upper: float
    marginal_return: float
    carryover: float
    half_life_weeks: float
    half_saturation: float
    slope: float
    spend_last_year: float
    incremental_last_year: float


class Model(Protocol):
    spec: MMMSpec
    data_source: str

    @property
    def backend(self) -> str: ...

    @property
    def spec_hash(self) -> str: ...

    def contributions(self) -> pl.DataFrame: ...

    def response_curve(self, channel: str, spend_grid: np.ndarray) -> np.ndarray: ...

    def marginal_return(self, channel: str, at_spend: float) -> float: ...

    def intervals(self) -> list[ChannelReturn]: ...

    def diagnostics(self) -> dict[str, float | int | str]: ...

    def calibrate(self, lift_results: list[LiftResult]) -> Model: ...


def fit(panel: pl.DataFrame, spec: MMMSpec, *, data_source: str = "simulated") -> Model:
    if spec.backend == "own":
        from marginal_mmm.own import fit_own

        model: Model = fit_own(panel, spec, data_source=data_source)
        return model
    if spec.backend == "bayes":
        from marginal_mmm.bayes import fit_bayes

        bayes_model: Model = fit_bayes(panel, spec, data_source=data_source)
        return bayes_model
    raise ValueError(f"unknown backend {spec.backend!r}")


def contributions(model: Model) -> pl.DataFrame:
    return model.contributions()


def response_curve(model: Model, channel: str, spend_grid: np.ndarray) -> np.ndarray:
    return model.response_curve(channel, spend_grid)


def marginal_return(model: Model, channel: str, at_spend: float) -> float:
    return model.marginal_return(channel, at_spend)


def intervals(model: Model) -> list[ChannelReturn]:
    return model.intervals()


def calibrate(model: Model, lift_results: list[LiftResult]) -> Model:
    return model.calibrate(lift_results)


def design_columns(panel: pl.DataFrame, spec: MMMSpec) -> tuple[np.ndarray, list[str]]:
    """The baseline design shared by both backends: an intercept, trend, log price, promotion,
    holiday and Fourier seasonality. The `own` backend exponentiates the linear index, so the
    baseline is multiplicative in these drivers the way organic demand is."""
    t = panel["week"].to_numpy().astype(float)
    cols: list[np.ndarray] = [
        np.ones(len(t)),
        t / len(t),
        np.log(panel["price_index"].to_numpy().astype(float)),
        panel["promo"].to_numpy().astype(float),
        panel["holiday"].to_numpy().astype(float),
    ]
    names: list[str] = ["intercept", "trend", "log_price", "promo", "holiday"]
    for k in range(1, spec.fourier_order + 1):
        cols.append(np.sin(2 * np.pi * k * t / 52.18))
        names.append(f"sin_{k}")
        cols.append(np.cos(2 * np.pi * k * t / 52.18))
        names.append(f"cos_{k}")
    return np.column_stack(cols), names


class CurveParams(StrictModel):
    """One channel's fitted response curve in dollars: revenue at a steady weekly spend S is
    ceiling times Hill(S; half_saturation, slope). The draws carry the ceiling's uncertainty
    (bootstrap replicates for own, posterior draws for bayes) so a plan's expected outcome has
    an interval."""

    channel: str
    ceiling: float
    half_saturation: float
    slope: float
    carryover: float
    weekly_spend_current: float
    spend_last_year: float
    ceiling_draws: list[float]

    def response(self, spend: np.ndarray | float) -> np.ndarray:
        from marginal_mmm.transforms import hill

        return np.asarray(
            self.ceiling * hill(np.asarray(spend, dtype=float), self.half_saturation, self.slope)
        )

    def marginal(self, spend: float) -> float:
        from marginal_mmm.transforms import hill_slope

        return float(self.ceiling * hill_slope(spend, self.half_saturation, self.slope))


class ModelExport(StrictModel):
    """Everything the optimizer and the API need from a fitted model, without the model."""

    backend: str
    spec_hash: str
    data_source: str
    calibrated: bool
    version: str
    channels: list[CurveParams]

    def curve(self, channel: str) -> CurveParams:
        for c in self.channels:
            if c.channel == channel:
                return c
        raise KeyError(channel)


def export_model(model: Model, version: str) -> ModelExport:
    """The fitted response curves of either backend as one record."""
    from marginal_mmm.own import OwnModel

    channels: list[CurveParams] = []
    returns = model.intervals()
    if isinstance(model, OwnModel):
        for j, r in enumerate(returns):
            channels.append(
                CurveParams(
                    channel=r.channel,
                    ceiling=float(model.beta[j]),
                    half_saturation=r.half_saturation,
                    slope=r.slope,
                    carryover=r.carryover,
                    weekly_spend_current=r.spend_last_year / model.spec.last_year_weeks,
                    spend_last_year=r.spend_last_year,
                    ceiling_draws=[float(v) for v in model.bootstrap_beta[:, j]],
                )
            )
    else:
        draws = model.ceiling_draws()  # type: ignore[attr-defined]
        for j, r in enumerate(returns):
            channels.append(
                CurveParams(
                    channel=r.channel,
                    ceiling=float(model.response_curve(r.channel, np.array([1e12]))[0]),
                    half_saturation=r.half_saturation,
                    slope=r.slope,
                    carryover=r.carryover,
                    weekly_spend_current=r.spend_last_year / model.spec.last_year_weeks,
                    spend_last_year=r.spend_last_year,
                    ceiling_draws=[float(v) for v in draws[:, j]],
                )
            )
    return ModelExport(
        backend=model.backend,
        spec_hash=model.spec_hash,
        data_source=model.data_source,
        calibrated=bool(model.diagnostics().get("calibrated", 0)),
        version=version,
        channels=channels,
    )
