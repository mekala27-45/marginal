"""The Hillstrom email experiment as a typed frame.

64,000 customers who bought in the prior twelve months, randomized in thirds to a men's
merchandise email, a women's merchandise email, or no email, with visit, conversion and
spend over the following two weeks. The customer id is the row's position in the public
file; it exists so every seeded split sorts on a stated key.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
from marginal_core.model import StrictModel

ARMS = {"No E-Mail": "control", "Mens E-Mail": "mens", "Womens E-Mail": "womens"}
RAW_COLUMNS = [
    "recency",
    "history_segment",
    "history",
    "mens",
    "womens",
    "zip_code",
    "newbie",
    "channel",
    "segment",
    "visit",
    "conversion",
    "spend",
]
FEATURES = [
    "recency",
    "history",
    "mens",
    "womens",
    "newbie",
    "zip_urban",
    "zip_suburban",
    "channel_web",
    "channel_phone",
]


class HillstromSummary(StrictModel):
    rows: int
    arms: dict[str, int]
    visit_rate: float
    conversion_rate: float
    mean_spend: float


def load(path: Path) -> pl.DataFrame:
    frame = pl.read_csv(path, schema_overrides={"history": pl.Float64, "spend": pl.Float64})
    if frame.columns != RAW_COLUMNS:
        raise ValueError(f"unexpected Hillstrom columns {frame.columns}")
    frame = frame.with_row_index("customer_id")
    frame = frame.with_columns(
        pl.col("segment").replace_strict(ARMS).alias("arm"),
        (pl.col("zip_code") == "Urban").cast(pl.Int8).alias("zip_urban"),
        (pl.col("zip_code") == "Surburban").cast(pl.Int8).alias("zip_suburban"),
        (pl.col("channel") == "Web").cast(pl.Int8).alias("channel_web"),
        (pl.col("channel") == "Phone").cast(pl.Int8).alias("channel_phone"),
        pl.col("history_segment").str.slice(0, 1).cast(pl.Int8).alias("history_decile"),
    )
    return frame.sort("customer_id")


def summary(frame: pl.DataFrame) -> HillstromSummary:
    arms = {
        row["arm"]: int(row["len"]) for row in frame.group_by("arm").len().sort("arm").iter_rows(named=True)
    }
    return HillstromSummary(
        rows=frame.height,
        arms=arms,
        visit_rate=_mean(frame, "visit"),
        conversion_rate=_mean(frame, "conversion"),
        mean_spend=_mean(frame, "spend"),
    )


def _mean(frame: pl.DataFrame, column: str) -> float:
    value = frame[column].mean()
    if not isinstance(value, int | float):
        raise TypeError(f"{column} has no numeric mean")
    return float(value)
