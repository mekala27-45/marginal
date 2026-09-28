"""The five heuristic credit rules: last touch, first touch, linear, position based, time decay.

Each rule takes the touch table (one row per touch, with the user, the position on the path
and the days before the path ended) and the users table (with the conversion flag), and hands
every converting path's one conversion out across its touches. A rule is a reporting
convention: it sees the path and the outcome, never what would have happened without a touch.
"""

from __future__ import annotations

import numpy as np
import polars as pl
from marginal_core.config import CHANNELS, POLICY

RULES: tuple[str, ...] = ("last_touch", "first_touch", "linear", "position_based", "time_decay", "shapley")
RULE_LABELS: dict[str, str] = {
    "last_touch": "Last touch",
    "first_touch": "First touch",
    "linear": "Linear",
    "position_based": "Position based",
    "time_decay": "Time decay",
    "shapley": "Shapley",
}


def converting_touches(touches: pl.DataFrame, users: pl.DataFrame) -> pl.DataFrame:
    """The touches on converting paths, with the path length and the last position beside each."""
    converted = users.filter(pl.col("converted") == 1).select("user_id")
    frame = touches.join(converted, on="user_id", how="inner").sort(["user_id", "position"])
    return frame.with_columns(
        pl.len().over("user_id").alias("path_length"),
        pl.col("position").max().over("user_id").alias("last_position"),
    )


def touch_weights(frame: pl.DataFrame, rule: str) -> pl.Series:
    """The share of the path's conversion each touch receives under a rule; sums to one per path."""
    n = frame["path_length"].to_numpy().astype(float)
    position = frame["position"].to_numpy().astype(float)
    last = frame["last_position"].to_numpy().astype(float)
    is_first = position == 0
    is_last = position == last
    if rule == "last_touch":
        weights = is_last.astype(float)
    elif rule == "first_touch":
        weights = is_first.astype(float)
    elif rule == "linear":
        weights = 1.0 / n
    elif rule == "position_based":
        first_share = POLICY.attribution_position_first
        last_share = POLICY.attribution_position_last
        middle_share = 1.0 - first_share - last_share
        weights = np.where(
            n == 1,
            1.0,
            np.where(
                n == 2,
                0.5,
                np.where(
                    is_first, first_share, np.where(is_last, last_share, middle_share / np.maximum(n - 2, 1))
                ),
            ),
        )
    elif rule == "time_decay":
        days = frame["days_before_end"].to_numpy().astype(float)
        raw = np.power(0.5, days / POLICY.attribution_half_life_days)
        totals = frame.with_columns(pl.Series("raw", raw)).select(pl.col("raw").sum().over("user_id"))["raw"]
        weights = raw / totals.to_numpy()
    else:
        raise ValueError(f"unknown rule {rule!r}")
    return pl.Series("weight", np.asarray(weights, dtype=float))


def credit_by_channel(frame: pl.DataFrame, rule: str) -> pl.DataFrame:
    """Conversions credited to each channel under a rule, in the fixed channel order."""
    weighted = frame.with_columns(touch_weights(frame, rule))
    credit = weighted.group_by("channel").agg(pl.col("weight").sum().alias("credit"))
    return _in_channel_order(credit, "credit")


def _in_channel_order(frame: pl.DataFrame, column: str) -> pl.DataFrame:
    base = pl.DataFrame({"channel": list(CHANNELS)})
    joined = base.join(frame, on="channel", how="left").with_columns(pl.col(column).fill_null(0.0))
    return joined.select(["channel", column])
