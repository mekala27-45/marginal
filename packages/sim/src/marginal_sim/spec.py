"""What the simulator is told, and the truth it writes down.

A market spec fixes the seed and the two switches the recovery study varies: how strongly
channel spend moves together, and whether the retargeting channel's spend follows demand.
Everything else (the channel means, the true carryover, saturation and return) is a stated
default so the demonstration brand and every recovery seed share one economy.
"""

from __future__ import annotations

import datetime as dt

from marginal_core.config import CHANNELS
from marginal_core.model import StrictModel


class ChannelTruth(StrictModel):
    channel: str
    mean_weekly_spend: float
    """Planned national spend per week in dollars."""
    carryover: float
    """Geometric retention rate theta; the half life is log(0.5) / log(theta) weeks."""
    half_saturation_ratio: float
    """The half saturation point as a multiple of mean weekly spend."""
    slope: float
    """Hill slope s."""
    roas_at_mean: float
    """True incremental revenue per dollar at mean spend, which fixes the ceiling A."""


DEFAULT_CHANNELS: tuple[ChannelTruth, ...] = (
    ChannelTruth(
        channel="paid_search",
        mean_weekly_spend=130_000,
        carryover=0.20,
        half_saturation_ratio=0.9,
        slope=1.6,
        roas_at_mean=3.2,
    ),
    ChannelTruth(
        channel="paid_social",
        mean_weekly_spend=110_000,
        carryover=0.35,
        half_saturation_ratio=1.1,
        slope=1.8,
        roas_at_mean=2.4,
    ),
    ChannelTruth(
        channel="online_video",
        mean_weekly_spend=60_000,
        carryover=0.65,
        half_saturation_ratio=1.4,
        slope=1.5,
        roas_at_mean=1.6,
    ),
    ChannelTruth(
        channel="display_retargeting",
        mean_weekly_spend=70_000,
        carryover=0.30,
        half_saturation_ratio=0.7,
        slope=2.2,
        roas_at_mean=1.4,
    ),
    ChannelTruth(
        channel="email",
        mean_weekly_spend=15_000,
        carryover=0.15,
        half_saturation_ratio=0.6,
        slope=2.4,
        roas_at_mean=8.0,
    ),
    ChannelTruth(
        channel="affiliate_promo",
        mean_weekly_spend=40_000,
        carryover=0.25,
        half_saturation_ratio=1.0,
        slope=1.7,
        roas_at_mean=2.8,
    ),
    ChannelTruth(
        channel="direct_mail",
        mean_weekly_spend=55_000,
        carryover=0.72,
        half_saturation_ratio=1.3,
        slope=1.4,
        roas_at_mean=1.9,
    ),
)

assert tuple(c.channel for c in DEFAULT_CHANNELS) == CHANNELS


class Intervention(StrictModel):
    """A change to one channel's spend in some geos over a window: a geo lift test."""

    channel: str
    geos: tuple[int, ...]
    start_week: int
    end_week: int
    spend_multiplier: float
    """Zero for a holdout, above one for an increase."""


class MarketSpec(StrictModel):
    seed: int
    intervention: Intervention | None = None
    spend_correlation: float = 0.6
    """Target correlation between channels' weekly spend shocks: 0.2, 0.6 or 0.9 in the study."""
    demand_feedback: bool = True
    """Whether display and retargeting spend follows last week's demand."""
    feedback_coefficient: float = 1.5
    """Retargeting spend moves this many percent for each percent last week's baseline was above its mean."""
    geos: int = 40
    weeks: int = 156
    first_week: dt.date = dt.date(2023, 10, 2)
    baseline_weekly_revenue: float = 1_750_000
    """Organic revenue per week at the mean of every driver."""
    seasonal_amplitude: float = 0.18
    trend_per_year: float = 0.05
    holiday_lift: float = 0.35
    price_elasticity: float = -1.2
    promo_lift: float = 0.08
    competitor_noise: float = 0.01
    sales_noise: float = 0.02
    spend_shock_sd: float = 0.25
    """Standard deviation of the log spend shock per channel per week."""
    spend_seasonality: float = 0.30
    """How much planned spend follows the demand season, the same for every channel."""
    geo_spend_noise: float = 0.06
    adstock_max_lag: int = 13
    channels: tuple[ChannelTruth, ...] = DEFAULT_CHANNELS

    @property
    def condition(self) -> str:
        return f"rho {self.spend_correlation:.1f}, feedback {'on' if self.demand_feedback else 'off'}"


class CustomerSpec(StrictModel):
    seed: int
    customers: int = 200_000
    treated_share_random: float = 0.5
    policy_contact_share: float = 0.30
    """The stated targeting policy contacts this share, chosen by predicted baseline conversion."""


class PathSpec(StrictModel):
    seed: int
    users: int = 60_000
    mean_touches: float = 3.2
    base_conversion: float = 0.04
    """Conversion probability with no touches for a user of average intent."""
    intent_sd: float = 1.1
    """Spread of latent intent on the log odds scale; retargeting and paid search follow it."""
    intent_targeting: float = 1.6
    """How strongly display and retargeting and paid search touches are placed on high intent users."""


CONDITIONS: tuple[tuple[float, bool], ...] = tuple(
    (rho, feedback) for rho in (0.2, 0.6, 0.9) for feedback in (False, True)
)


def condition_name(rho: float, feedback: bool) -> str:
    return f"rho {rho:.1f}, feedback {'on' if feedback else 'off'}"


def demonstration_spec(seed: int) -> MarketSpec:
    """The demonstration brand: spend planned together and retargeting that follows demand."""
    return MarketSpec(seed=seed, spend_correlation=0.6, demand_feedback=True)
