"""Lifetime value, the frequency segments and the acquisition cost allowance.

Lifetime value is the discounted expected revenue a customer brings over the horizon: BG/NBD's
expected purchase days in each month times Gamma-Gamma's expected spend per purchase day,
discounted at the end of each month at the monthly rate equivalent to the annual one,
(1 + annual) ** (1 / 12) - 1. A month is 30.4375 days, a year of 365.25 days over twelve, so
twelve months cover one year of the day based model. The value is revenue, not profit: the
contribution margin enters in the allowance and nowhere else.

The allowance is the most a channel may spend to acquire one customer: mean lifetime value
times the contribution margin times the payback share. At the allowance, acquiring a customer
costs that share of the margin the customer brings over the horizon, and the rest is profit.
It is computed per segment, over all customers, and per channel as the mix weighted mean of the
segment allowances, with the mixes in CHANNEL_SEGMENT_MIX.

The mixes are stated assumptions, not measurements: the retail history records no channel and
the demonstration brand's channels are simulated. They say what kind of customer each channel
tends to bring, search and email more buyers who come back, display and affiliate codes more
one time buyers, and a channel's allowance moves linearly with its mix. A segment is the
customer's calibration frequency, which also reflects how long they have been a customer;
reading it as the kind of customer a channel acquires is the simplification the mixes rest on.
"""

from __future__ import annotations

import numpy as np
import polars as pl
from marginal_core.config import CHANNELS
from marginal_core.model import StrictModel

from marginal_clv.bgnbd import BGNBD
from marginal_clv.gamma_gamma import GammaGamma

DAYS_PER_MONTH = 30.4375


class Segment(StrictModel):
    slug: str
    label: str
    low: int
    high: int | None
    """Largest calibration frequency in the segment; None for no upper limit."""

    @property
    def description(self) -> str:
        if self.high is None:
            return f"{self.low} or more repeat purchases"
        if self.low == self.high:
            return "no repeat purchase" if self.low == 0 else f"{self.low} repeat purchases"
        return f"{self.low} to {self.high} repeat purchases"


SEGMENTS: tuple[Segment, ...] = (
    Segment(slug="one_time", label="one time", low=0, high=0),
    Segment(slug="occasional", label="occasional", low=1, high=2),
    Segment(slug="regular", label="regular", low=3, high=5),
    Segment(slug="frequent", label="frequent", low=6, high=None),
)
SEGMENT_SLUGS = tuple(s.slug for s in SEGMENTS)

CHANNEL_SEGMENT_MIX: dict[str, dict[str, float]] = {
    # Searchers arrive with intent and a fair share come back.
    "paid_search": {"one_time": 0.30, "occasional": 0.30, "regular": 0.25, "frequent": 0.15},
    # Social prospecting finds impulse buyers; fewer of them return.
    "paid_social": {"one_time": 0.45, "occasional": 0.30, "regular": 0.17, "frequent": 0.08},
    # Video reaches broadly and slowly; its buyers sit between social and search.
    "online_video": {"one_time": 0.40, "occasional": 0.32, "regular": 0.18, "frequent": 0.10},
    # Retargeting closes the sale for people already shopping, many of them once.
    "display_retargeting": {"one_time": 0.50, "occasional": 0.28, "regular": 0.15, "frequent": 0.07},
    # Email reaches people who asked to hear from the brand, the most loyal mix.
    "email": {"one_time": 0.20, "occasional": 0.30, "regular": 0.30, "frequent": 0.20},
    # Promo codes attract deal seekers, the most one time buyers.
    "affiliate_promo": {"one_time": 0.55, "occasional": 0.27, "regular": 0.12, "frequent": 0.06},
    # Catalog households buy again more than most prospects.
    "direct_mail": {"one_time": 0.25, "occasional": 0.30, "regular": 0.28, "frequent": 0.17},
}
"""Share of each channel's new customers in each segment. Stated, not measured; see the module
docstring. Each mix sums to one and every channel in marginal_core.config.CHANNELS has one."""


class SegmentAllowance(StrictModel):
    segment: str
    label: str
    customers: int
    mean_clv: float
    allowance: float


class ChannelAllowance(StrictModel):
    channel: str
    mix: dict[str, float]
    mean_clv: float
    """Mix weighted mean lifetime value of the customers the channel brings."""
    allowance: float


class Allowance(StrictModel):
    margin: float
    payback_share: float
    overall: SegmentAllowance
    segments: list[SegmentAllowance]
    channels: list[ChannelAllowance]

    @property
    def by_segment(self) -> dict[str, float]:
        return {s.segment: s.allowance for s in self.segments}

    @property
    def by_channel(self) -> dict[str, float]:
        return {c.channel: c.allowance for c in self.channels}


def check_mixes(mixes: dict[str, dict[str, float]]) -> None:
    """Every channel has a mix over exactly the segments, with non negative shares summing to one."""
    if set(mixes) != set(CHANNELS):
        raise ValueError(f"the channel mixes cover {sorted(mixes)}, not the channels {list(CHANNELS)}")
    for channel, mix in mixes.items():
        if set(mix) != set(SEGMENT_SLUGS):
            raise ValueError(
                f"the {channel} mix covers {sorted(mix)}, not the segments {list(SEGMENT_SLUGS)}"
            )
        if any(share < 0 for share in mix.values()):
            raise ValueError(f"the {channel} mix has a negative share")
        if abs(sum(mix.values()) - 1.0) > 1e-9:
            raise ValueError(f"the {channel} mix sums to {sum(mix.values())}, not one")


def monthly_discount_rate(discount_rate_annual: float) -> float:
    if discount_rate_annual <= -1.0:
        raise ValueError("an annual discount rate must be above minus one")
    rate: float = (1.0 + discount_rate_annual) ** (1.0 / 12.0) - 1.0
    return rate


def customer_lifetime_value(
    bgnbd: BGNBD,
    gamma_gamma: GammaGamma,
    frame: pl.DataFrame,
    horizon_months: int,
    discount_rate_annual: float,
) -> pl.DataFrame:
    """Discounted expected revenue per customer over the horizon, one row per customer of ``frame``.

    ``frame`` carries customer_id, frequency, recency, T and monetary, as rfm_frame makes them.
    """
    if horizon_months < 1:
        raise ValueError("the horizon is at least one month")
    monthly = monthly_discount_rate(discount_rate_annual)
    months = np.arange(1, horizon_months + 1, dtype=np.float64)
    # Expected purchase days up to the end of each month, one row per month; the differences
    # are the purchases expected within each month.
    cumulative = bgnbd.expected_purchases(
        (months * DAYS_PER_MONTH)[:, None], frame["frequency"], frame["recency"], frame["T"]
    )
    within = np.diff(cumulative, axis=0, prepend=0.0)
    discount = (1.0 + monthly) ** -months
    spend = gamma_gamma.conditional_expected_average_profit(frame["frequency"], frame["monetary"])
    clv = spend * (discount[:, None] * within).sum(axis=0)
    return pl.DataFrame(
        {
            "customer_id": frame["customer_id"],
            "expected_purchases_horizon": cumulative[-1],
            "expected_average_spend": spend,
            "clv": clv,
        }
    )


def _member(segment: Segment) -> pl.Expr:
    inside = pl.col("frequency") >= segment.low
    if segment.high is not None:
        inside = inside & (pl.col("frequency") <= segment.high)
    return inside


def segments(frame: pl.DataFrame) -> pl.DataFrame:
    """``frame`` with each customer's segment (slug) and segment_label, by calibration frequency."""
    if "frequency" not in frame.columns:
        raise KeyError("segments are assigned by the frequency column")
    labelled = frame.with_columns(
        pl.coalesce([pl.when(_member(s)).then(pl.lit(s.slug)) for s in SEGMENTS]).alias("segment"),
        pl.coalesce([pl.when(_member(s)).then(pl.lit(s.label)) for s in SEGMENTS]).alias("segment_label"),
    )
    if labelled["segment"].null_count():
        raise ValueError("a customer has a frequency outside every segment")
    return labelled


def acquisition_allowance(clv_frame: pl.DataFrame, margin: float, payback_share: float) -> Allowance:
    """The allowance per segment, overall and per channel from the customers' lifetime values.

    ``clv_frame`` carries a clv column and either a segment column or the frequency to assign one.
    """
    if not 0.0 < margin <= 1.0:
        raise ValueError(f"the margin must be in (0, 1], got {margin}")
    if not 0.0 < payback_share <= 1.0:
        raise ValueError(f"the payback share must be in (0, 1], got {payback_share}")
    check_mixes(CHANNEL_SEGMENT_MIX)
    frame = clv_frame if "segment" in clv_frame.columns else segments(clv_frame)
    if frame.height == 0:
        raise ValueError("no customers to value")
    values = frame["clv"].to_numpy()
    if not np.all(np.isfinite(values)):
        raise ValueError("a lifetime value is missing or infinite")

    def record(slug: str, label: str, clv: np.ndarray) -> SegmentAllowance:
        mean_clv = float(clv.mean())
        return SegmentAllowance(
            segment=slug,
            label=label,
            customers=int(clv.size),
            mean_clv=mean_clv,
            allowance=mean_clv * margin * payback_share,
        )

    labels = frame["segment"].to_numpy()
    per_segment = []
    for s in SEGMENTS:
        members = values[labels == s.slug]
        if members.size == 0:
            raise ValueError(f"no customer is in the {s.label} segment, so no channel mix can weight it")
        per_segment.append(record(s.slug, s.label, members))
    by_slug = {s.segment: s for s in per_segment}
    channels = [
        ChannelAllowance(
            channel=channel,
            mix=dict(CHANNEL_SEGMENT_MIX[channel]),
            mean_clv=sum(
                share * by_slug[slug].mean_clv for slug, share in CHANNEL_SEGMENT_MIX[channel].items()
            ),
            allowance=sum(
                share * by_slug[slug].allowance for slug, share in CHANNEL_SEGMENT_MIX[channel].items()
            ),
        )
        for channel in CHANNELS
    ]
    return Allowance(
        margin=margin,
        payback_share=payback_share,
        overall=record("all", "all customers", values),
        segments=per_segment,
        channels=channels,
    )


def revenue_per_acquisition(frame: pl.DataFrame) -> float:
    """Mean revenue on the first purchase day across customers: what an acquisition brings that day.

    The budget optimizer divides a channel's incremental revenue by this to count the customers
    the channel acquires, and compares spend per customer with the channel's allowance.
    """
    if "first_revenue" not in frame.columns or frame.height == 0:
        raise ValueError("revenue per acquisition needs the first_revenue of at least one customer")
    first = frame["first_revenue"].to_numpy()
    if not np.all(np.isfinite(first)) or np.any(first <= 0):
        raise ValueError("a first purchase revenue is missing or not positive")
    return float(first.mean())
