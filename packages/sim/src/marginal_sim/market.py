"""The market with known truth: forty geos, 156 weeks, seven paid channels.

Sales in a geo week are organic baseline demand plus each channel's incremental revenue,
where the channel's adstocked spend density passes through a Hill saturation curve whose
parameters are known. Two things make the panel hard the way real markets are hard, and
both are switches on the spec: channels' weekly spend shocks are correlated (brands plan
flights together), and display and retargeting spend follows last week's demand.

Adstock is normalized geometric decay over a fixed number of lags, so a constant weekly
spend S adstocks to S and the national response curve is A times H(S) in spend units.
"""

from __future__ import annotations

import datetime as dt
import math

import numpy as np
import polars as pl
from marginal_core.config import CHANNELS
from marginal_core.model import StrictModel
from marginal_core.seeds import rng

from marginal_sim.spec import ChannelTruth, MarketSpec


class TruthParams(StrictModel):
    channel: str
    carryover: float
    half_life_weeks: float
    half_saturation: float
    slope: float
    ceiling: float
    """A: the weekly incremental revenue the channel approaches at unbounded spend."""
    mean_weekly_spend: float
    roas_at_mean: float


class Market(StrictModel):
    spec: MarketSpec
    truth: list[TruthParams]
    achieved_spend_correlation: float
    week_dates: list[dt.date]


def hill(x: np.ndarray, k: float, s: float) -> np.ndarray:
    xs = np.power(np.clip(x, 0.0, None), s)
    return np.asarray(xs / (k**s + xs))


def hill_derivative(x: float, k: float, s: float) -> float:
    if x <= 0:
        return 0.0
    return float(s * (k**s) * x ** (s - 1) / (k**s + x**s) ** 2)


def adstock(x: np.ndarray, theta: float, max_lag: int) -> np.ndarray:
    """Normalized geometric adstock along the last axis."""
    weights = np.array([theta**lag for lag in range(max_lag + 1)])
    weights /= weights.sum()
    out = np.zeros_like(x, dtype=float)
    for lag, w in enumerate(weights):
        if lag == 0:
            out += w * x
        else:
            out[..., lag:] += w * x[..., :-lag]
    return out


def truth_params(channel: ChannelTruth) -> TruthParams:
    k = channel.half_saturation_ratio * channel.mean_weekly_spend
    h_mean = float(hill(np.array([channel.mean_weekly_spend]), k, channel.slope)[0])
    ceiling = channel.roas_at_mean * channel.mean_weekly_spend / h_mean
    return TruthParams(
        channel=channel.channel,
        carryover=channel.carryover,
        half_life_weeks=math.log(0.5) / math.log(channel.carryover),
        half_saturation=k,
        slope=channel.slope,
        ceiling=ceiling,
        mean_weekly_spend=channel.mean_weekly_spend,
        roas_at_mean=channel.roas_at_mean,
    )


def response(params: TruthParams, spend: np.ndarray) -> np.ndarray:
    """The true weekly incremental revenue at a steady weekly spend."""
    return params.ceiling * hill(np.asarray(spend, dtype=float), params.half_saturation, params.slope)


def marginal_return(params: TruthParams, spend: float) -> float:
    return params.ceiling * hill_derivative(spend, params.half_saturation, params.slope)


def _season(
    weeks: int, first_week: dt.date, amplitude: float, holiday_lift: float
) -> tuple[np.ndarray, np.ndarray]:
    t = np.arange(weeks)
    dates = [first_week + dt.timedelta(weeks=int(i)) for i in t]
    base = 1.0 + amplitude * np.sin(2 * np.pi * (t - 5) / 52.18)
    holiday = np.zeros(weeks)
    for i, day in enumerate(dates):
        week_of_year = day.isocalendar().week
        if 47 <= week_of_year <= 51:
            holiday[i] = holiday_lift * (1.0 - abs(week_of_year - 49) / 3.0)
        elif week_of_year in (1, 52):
            holiday[i] = -0.10
    return base + holiday, holiday


def simulate_market(spec: MarketSpec) -> tuple[pl.DataFrame, pl.DataFrame, Market]:
    """Returns the geo panel, the national panel with the truth beside it, and the market record."""
    g, w = spec.geos, spec.weeks
    channels = list(CHANNELS)
    c = len(channels)
    params = [truth_params(ch) for ch in spec.channels]
    means = np.array([p.mean_weekly_spend for p in params])

    season, holiday = _season(w, spec.first_week, spec.seasonal_amplitude, spec.holiday_lift)
    trend = np.power(1.0 + spec.trend_per_year, np.arange(w) / 52.0)

    price_rng = rng(spec.seed, "price")
    price = np.ones(w)
    for t in range(1, w):
        price[t] = 1.0 + 0.85 * (price[t - 1] - 1.0) + price_rng.normal(0, 0.015)
    promo = (rng(spec.seed, "promo").random(w) < 0.15).astype(float)
    price = price * (1.0 - 0.10 * promo)

    comp_rng = rng(spec.seed, "competitor")
    competitor = np.zeros(w)
    for t in range(1, w):
        competitor[t] = 0.7 * competitor[t - 1] + comp_rng.normal(0, spec.competitor_noise)

    baseline_national = (
        spec.baseline_weekly_revenue
        * season
        * trend
        * np.power(price, spec.price_elasticity)
        * (1.0 + spec.promo_lift * promo)
        * (1.0 + competitor)
    )

    weights = rng(spec.seed, "geo_weights").lognormal(0.0, 0.6, g)
    weights = weights / weights.sum()
    geo_noise = rng(spec.seed, "geo_baseline_noise").normal(0.0, spec.sales_noise, (g, w))
    baseline_geo = weights[:, None] * baseline_national[None, :] * (1.0 + geo_noise)

    # Planned national spend: a shared seasonal plan plus correlated weekly shocks.
    rho = spec.spend_correlation
    cov = spec.spend_shock_sd**2 * ((1.0 - rho) * np.eye(c) + rho * np.ones((c, c)))
    shocks = rng(spec.seed, "spend_shocks").multivariate_normal(np.zeros(c), cov, size=w).T  # c x w
    seasonal_plan = 1.0 + spec.spend_seasonality * (season - 1.0)
    planned = means[:, None] * seasonal_plan[None, :] * np.exp(shocks - spec.spend_shock_sd**2 / 2.0)

    # Demand feedback on display and retargeting: this week's spend follows last week's baseline.
    if spec.demand_feedback:
        idx = channels.index("display_retargeting")
        relative = baseline_national / baseline_national.mean() - 1.0
        follow = np.ones(w)
        follow[1:] = 1.0 + spec.feedback_coefficient * relative[:-1]
        planned[idx] = planned[idx] * np.clip(follow, 0.2, None)

    national_spend = planned  # c x w
    achieved = np.corrcoef(np.log(national_spend))
    achieved_mean = float((achieved.sum() - c) / (c * (c - 1)))

    # Geo allocation proportional to size with a little noise, rescaled to the national total.
    alloc_noise = 1.0 + rng(spec.seed, "geo_spend_noise").normal(0.0, spec.geo_spend_noise, (g, c, w))
    geo_spend = weights[:, None, None] * national_spend[None, :, :] * alloc_noise
    geo_spend *= national_spend[None, :, :] / geo_spend.sum(axis=0, keepdims=True)

    # A geo lift test changes one channel's spend in the treated geos over the window, after the
    # plan is allocated, so everything else about the market (its noise included) is unchanged.
    if spec.intervention is not None:
        iv = spec.intervention
        j = channels.index(iv.channel)
        geo_idx = np.array(iv.geos, dtype=int)
        window = np.arange(iv.start_week, iv.end_week + 1)
        geo_spend[np.ix_(geo_idx, np.array([j]), window)] *= iv.spend_multiplier
        national_spend = geo_spend.sum(axis=0)

    # Response: adstock the spend density, saturate, scale by size.
    density = geo_spend / weights[:, None, None]
    incremental = np.zeros((g, c, w))
    for j, p in enumerate(params):
        stocked = adstock(density[:, j, :], p.carryover, spec.adstock_max_lag)
        incremental[:, j, :] = weights[:, None] * p.ceiling * hill(stocked, p.half_saturation, p.slope)

    measurement = rng(spec.seed, "sales_noise").normal(0.0, spec.sales_noise / 2.0, (g, w))
    sales = (baseline_geo + incremental.sum(axis=1)) * (1.0 + measurement)

    dates = [spec.first_week + dt.timedelta(weeks=i) for i in range(w)]
    geo_rows = {
        "geo": np.repeat(np.arange(g), w),
        "week": np.tile(np.arange(w), g),
        "week_start": np.tile(np.array(dates, dtype="datetime64[D]"), g),
        "geo_weight": np.repeat(weights, w),
        "sales": sales.reshape(-1),
        "baseline_true": baseline_geo.reshape(-1),
    }
    for j, name in enumerate(channels):
        geo_rows[f"spend_{name}"] = geo_spend[:, j, :].reshape(-1)
        geo_rows[f"incremental_true_{name}"] = incremental[:, j, :].reshape(-1)
    geo_panel = pl.DataFrame(geo_rows).with_columns(pl.col("week_start").cast(pl.Date))

    national_rows = {
        "week": np.arange(w),
        "week_start": np.array(dates, dtype="datetime64[D]"),
        "sales": sales.sum(axis=0),
        "baseline_true": baseline_geo.sum(axis=0),
        "price_index": price,
        "promo": promo,
        "holiday": holiday,
        "season_true": season,
        "trend_true": trend,
        "competitor_true": competitor,
    }
    for j, name in enumerate(channels):
        national_rows[f"spend_{name}"] = national_spend[j]
        national_rows[f"incremental_true_{name}"] = incremental[:, j, :].sum(axis=0)
    national = pl.DataFrame(national_rows).with_columns(pl.col("week_start").cast(pl.Date))

    market = Market(spec=spec, truth=params, achieved_spend_correlation=achieved_mean, week_dates=dates)
    return geo_panel, national, market


def national_truth_table(national: pl.DataFrame, market: Market, last_weeks: int = 52) -> pl.DataFrame:
    """Per channel: realised spend and incremental revenue, the return, and the marginal return
    at last year's average weekly spend."""
    tail = national.tail(last_weeks)
    rows = []
    for p in market.truth:
        spend = float(tail[f"spend_{p.channel}"].sum())
        inc = float(tail[f"incremental_true_{p.channel}"].sum())
        weekly = spend / last_weeks
        rows.append(
            {
                "channel": p.channel,
                "spend_last_year": spend,
                "incremental_last_year": inc,
                "roas_true": inc / spend if spend else 0.0,
                "weekly_spend_current": weekly,
                "marginal_return_true": marginal_return(p, weekly),
                "carryover": p.carryover,
                "half_life_weeks": p.half_life_weeks,
                "half_saturation": p.half_saturation,
                "slope": p.slope,
                "ceiling": p.ceiling,
            }
        )
    return pl.DataFrame(rows)
