"""Exact Shapley credit over channel subsets.

The game is played on the seven channels. A coalition is a set of channels, and its worth is
the number of conversions that would have been counted if only those channels had existed: the
conversions on paths whose channel set lies inside the coalition. With seven channels there are
128 coalitions, so the Shapley value is computed exactly from the definition, not sampled. The
values sum to the conversion count (every path has at least one touch, so the empty coalition
is worth nothing), which is the property the tests hold the module to.
"""

from __future__ import annotations

import math

import numpy as np
import polars as pl
from marginal_core.config import CHANNELS

COALITIONS = 1 << len(CHANNELS)


def path_channel_sets(touches: pl.DataFrame, users: pl.DataFrame) -> pl.DataFrame:
    """One row per path: its channel set as a bit mask over the fixed channel order, and
    whether it converted."""
    bit_of = {c: 1 << i for i, c in enumerate(CHANNELS)}
    bits = touches.select(
        "user_id", pl.col("channel").replace_strict(bit_of, return_dtype=pl.Int64).alias("mask")
    )
    masks = bits.group_by("user_id").agg(pl.col("mask").unique().sum().alias("mask"))
    return (
        users.select("user_id", "converted")
        .join(masks, on="user_id", how="left")
        .with_columns(pl.col("mask").fill_null(0))
        .sort("user_id")
    )


def coalition_table(paths: pl.DataFrame) -> pl.DataFrame:
    """Every coalition with the paths whose channel set is exactly it, their conversions, and the
    coalition's worth (conversions on paths whose set lies inside it)."""
    exact_paths = np.zeros(COALITIONS, dtype=np.int64)
    exact_conversions = np.zeros(COALITIONS, dtype=np.int64)
    counts = paths.group_by("mask").agg(
        pl.len().alias("paths"), pl.col("converted").sum().alias("conversions")
    )
    for row in counts.iter_rows(named=True):
        exact_paths[int(row["mask"])] = int(row["paths"])
        exact_conversions[int(row["mask"])] = int(row["conversions"])
    worth = np.zeros(COALITIONS, dtype=np.int64)
    for mask in range(COALITIONS):
        sub = mask
        total = 0
        while True:
            total += exact_conversions[sub]
            if sub == 0:
                break
            sub = (sub - 1) & mask
        worth[mask] = total
    names = [
        " + ".join(c for i, c in enumerate(CHANNELS) if mask >> i & 1) or "none" for mask in range(COALITIONS)
    ]
    return pl.DataFrame(
        {
            "mask": np.arange(COALITIONS),
            "coalition": names,
            "size": [bin(mask).count("1") for mask in range(COALITIONS)],
            "paths_exact": exact_paths,
            "conversions_exact": exact_conversions,
            "worth": worth,
        }
    )


def shapley_credit(coalitions: pl.DataFrame) -> pl.DataFrame:
    """The exact Shapley value of each channel from the coalition worths."""
    worth = coalitions.sort("mask")["worth"].to_numpy().astype(float)
    n = len(CHANNELS)
    credit = np.zeros(n)
    for i in range(n):
        bit = 1 << i
        for mask in range(COALITIONS):
            if mask & bit:
                continue
            size = bin(mask).count("1")
            weight = math.factorial(size) * math.factorial(n - size - 1) / math.factorial(n)
            credit[i] += weight * (worth[mask | bit] - worth[mask])
    return pl.DataFrame({"channel": list(CHANNELS), "credit": credit})


def shapley(touches: pl.DataFrame, users: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Credit per channel and the coalition table it was computed from."""
    coalitions = coalition_table(path_channel_sets(touches, users))
    return shapley_credit(coalitions), coalitions
