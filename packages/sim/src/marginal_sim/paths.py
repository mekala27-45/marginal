"""User paths through the channels with the incremental credit of each touch known.

Each user carries a latent intent. Conversion probability is one minus the product of
the user's chance of not converting on their own and each touch's chance of not tipping
them, so every touch has a true incremental effect. Display and retargeting and paid
search touches are placed on high intent users, which is exactly the trap attribution
falls into: those channels appear on the paths of people who were about to convert, and
a last touch rule hands them the credit.

The true incremental credit of a touch is the conversion probability with every touch
minus the probability with that touch removed, holding the others. Summed over a channel
and divided by the sum over all touches, that is the channel's true incremental share.
"""

from __future__ import annotations

import numpy as np
import polars as pl
from marginal_core.config import CHANNELS
from marginal_core.seeds import rng

from marginal_sim.spec import PathSpec

# The true per touch effect: the probability a touch tips a user who would not otherwise convert.
TOUCH_EFFECT: dict[str, float] = {
    "paid_search": 0.060,
    "paid_social": 0.045,
    "online_video": 0.025,
    "display_retargeting": 0.012,
    "email": 0.070,
    "affiliate_promo": 0.040,
    "direct_mail": 0.030,
}

# How often each channel appears on a path, before intent targeting.
TOUCH_MIX: dict[str, float] = {
    "paid_search": 0.22,
    "paid_social": 0.20,
    "online_video": 0.10,
    "display_retargeting": 0.22,
    "email": 0.12,
    "affiliate_promo": 0.08,
    "direct_mail": 0.06,
}

INTENT_TARGETED = ("display_retargeting", "paid_search")


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return np.asarray(1.0 / (1.0 + np.exp(-x)))


def simulate_paths(spec: PathSpec) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Returns the touch table (one row per touch) and the per path truth (one row per user)."""
    r = rng(spec.seed, "paths")
    n = spec.users
    intent = r.normal(0.0, spec.intent_sd, n)
    base_logit = np.log(spec.base_conversion / (1.0 - spec.base_conversion))
    p_base = _sigmoid(base_logit + intent)

    lengths = np.clip(r.poisson(spec.mean_touches - 1, n) + 1, 1, 9)
    channels = list(CHANNELS)
    mix = np.array([TOUCH_MIX[c] for c in channels])
    targeted = np.array([c in INTENT_TARGETED for c in channels])

    user_ids: list[np.ndarray] = []
    positions: list[np.ndarray] = []
    chosen: list[np.ndarray] = []
    for i in range(n):
        weights = mix * np.where(targeted, np.exp(spec.intent_targeting * intent[i]), 1.0)
        weights = weights / weights.sum()
        picks = r.choice(len(channels), size=int(lengths[i]), p=weights)
        user_ids.append(np.full(int(lengths[i]), i))
        positions.append(np.arange(int(lengths[i])))
        chosen.append(picks)
    user = np.concatenate(user_ids)
    position = np.concatenate(positions)
    channel_idx = np.concatenate(chosen)
    effects = np.array([TOUCH_EFFECT[channels[j]] for j in channel_idx])

    # Conversion: 1 - (1 - p_base) * prod(1 - effect) over the path.
    survival = np.ones(n)
    np.multiply.at(survival, user, 1.0 - effects)
    p_convert = 1.0 - (1.0 - p_base) * survival
    u = rng(spec.seed, "path_outcomes").random(n)
    converted = (u < p_convert).astype(np.int8)

    # Credit of a touch: p(all) - p(without it).
    p_without = 1.0 - (1.0 - p_base[user]) * survival[user] / (1.0 - effects)
    credit = p_convert[user] - p_without

    # Timing: exponential gaps between touches, cumulated within each user, then expressed as
    # days before the path's last touch so time decay rules have something to decay over.
    gaps = rng(spec.seed, "path_timing").exponential(2.5, len(user))
    cum = np.cumsum(gaps)
    first_index = np.searchsorted(user, np.arange(n))
    starts = cum[first_index] - gaps[first_index]
    days = cum - starts[user]
    last_day = np.zeros(n)
    np.maximum.at(last_day, user, days)
    days_before_conversion = last_day[user] - days

    touches = pl.DataFrame(
        {
            "user_id": user,
            "position": position,
            "channel": [channels[j] for j in channel_idx],
            "days_before_end": days_before_conversion,
            "touch_effect_true": effects,
            "credit_true": credit,
        }
    ).sort(["user_id", "position"])
    users = pl.DataFrame(
        {
            "user_id": np.arange(n),
            "intent_true": intent,
            "p_base_true": p_base,
            "p_convert_true": p_convert,
            "converted": converted,
            "touches": lengths,
        }
    )
    return touches, users


def true_incremental_share(touches: pl.DataFrame) -> pl.DataFrame:
    """Each channel's share of the summed true credit across every touch."""
    total = float(touches["credit_true"].sum())
    shares = (
        touches.group_by("channel")
        .agg(pl.col("credit_true").sum().alias("credit_true"), pl.len().alias("touches"))
        .with_columns((pl.col("credit_true") / total).alias("share_true"))
    )
    order = {c: i for i, c in enumerate(CHANNELS)}
    return (
        shares.with_columns(pl.col("channel").replace_strict(order).alias("order"))
        .sort("order")
        .drop("order")
    )
