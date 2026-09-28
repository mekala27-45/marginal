"""Per customer summaries of a purchase history: the inputs BG/NBD and Gamma-Gamma are fit on.

A purchase is a purchase day. The committed Online Retail II table already holds one row per
customer per day, and the functions here aggregate to that grain again in case a caller passes
invoice rows: the models describe how often a customer comes back, and a second basket on the
same afternoon is not a return visit. Time is counted in whole days.

Over the calibration window, for each customer who bought in it:

    frequency      repeat purchase days, the purchase days after the first
    recency        days from the first purchase day to the last
    T              days from the first purchase day to the end of the window (the customer's age)
    monetary       mean revenue per repeat purchase day, null without a repeat purchase. The
                   first day is left out, as the Gamma-Gamma convention requires: the model
                   describes repeat spend, and the first basket reflects how the customer was
                   acquired as much as what they spend
    first_revenue  revenue on the first purchase day, the revenue an acquisition brings

The window's end is inclusive, so a customer whose only purchase fell on the last day has T
of zero and contributes nothing to the likelihood but is still counted and valued.
"""

from __future__ import annotations

import datetime as dt

import polars as pl

REQUIRED = ("customer_id", "day", "revenue")


def _purchase_days(purchases: pl.DataFrame) -> pl.DataFrame:
    missing = [c for c in REQUIRED if c not in purchases.columns]
    if missing:
        raise KeyError(f"the purchase table lacks {missing}")
    return (
        purchases.group_by(["customer_id", "day"]).agg(pl.col("revenue").sum()).sort(["customer_id", "day"])
    )


def rfm_frame(purchases: pl.DataFrame, calibration_end: dt.date) -> pl.DataFrame:
    """Frequency, recency, age and repeat spend per customer over the calibration window.

    One row per customer with at least one purchase day on or before ``calibration_end``,
    sorted by customer_id.
    """
    days = _purchase_days(purchases.filter(pl.col("day") <= calibration_end))
    if days.height == 0:
        raise ValueError(f"no purchases on or before the calibration end {calibration_end}")
    by_day = pl.col("revenue").sort_by("day")
    return (
        days.group_by("customer_id")
        .agg(
            pl.col("day").min().alias("first_day"),
            pl.col("day").max().alias("last_day"),
            pl.len().cast(pl.Int64).alias("purchase_days"),
            by_day.first().alias("first_revenue"),
            # The mean of an empty slice is null, which is what a customer without a repeat
            # purchase day should carry.
            by_day.slice(1).mean().alias("monetary"),
        )
        .with_columns(
            (pl.col("purchase_days") - 1).alias("frequency"),
            (pl.col("last_day") - pl.col("first_day")).dt.total_days().cast(pl.Int64).alias("recency"),
            (pl.lit(calibration_end) - pl.col("first_day")).dt.total_days().cast(pl.Int64).alias("T"),
        )
        .select(
            "customer_id",
            "first_day",
            "purchase_days",
            "frequency",
            "recency",
            "T",
            "monetary",
            "first_revenue",
        )
        .sort("customer_id")
    )


def holdout_frame(purchases: pl.DataFrame, holdout_start: dt.date, holdout_end: dt.date) -> pl.DataFrame:
    """Purchase days and revenue per calibration customer inside the holdout window.

    The calibration customers are the customers with a purchase day before ``holdout_start``;
    every one of them gets a row, with zeros when they did not buy in the holdout. A customer
    whose first purchase falls inside the holdout is not here: the models predict the future
    of customers they have seen, and a newcomer has no calibration history to predict from.
    ``holdout_days`` is the number of days in the window, both ends included, which is the
    prediction horizon when the holdout starts the day after the calibration window ends.
    """
    if holdout_end < holdout_start:
        raise ValueError(f"the holdout ends ({holdout_end}) before it starts ({holdout_start})")
    customers = (
        purchases.filter(pl.col("day") < holdout_start).select("customer_id").unique().sort("customer_id")
    )
    if customers.height == 0:
        raise ValueError(f"no customer bought before the holdout start {holdout_start}")
    inside = _purchase_days(purchases.filter(pl.col("day").is_between(holdout_start, holdout_end)))
    counts = inside.group_by("customer_id").agg(
        pl.len().cast(pl.Int64).alias("holdout_purchases"),
        pl.col("revenue").sum().alias("holdout_revenue"),
    )
    days = (holdout_end - holdout_start).days + 1
    return (
        customers.join(counts, on="customer_id", how="left")
        .with_columns(
            pl.col("holdout_purchases").fill_null(0),
            pl.col("holdout_revenue").fill_null(0.0),
            pl.lit(days, dtype=pl.Int64).alias("holdout_days"),
        )
        .sort("customer_id")
    )
