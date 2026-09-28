"""The holdout check: what the models predicted for the holdout window against what happened.

Customers are ordered by calibration frequency, ties broken by customer id, and cut into ten
groups of equal size (to within one customer). The order is fixed by the data, not by the order
rows arrive in, and equal groups keep every row of the table on the same footing; the price is
that the large block of customers without a repeat purchase spans several deciles, which the
frequency_low and frequency_high columns show.

Per decile and over all customers the table gives predicted and actual holdout purchase days
and revenue, and the mean absolute error per customer of each. Totals show bias; the mean
absolute error shows how far off a single customer's prediction is, which a total can hide.

The calibration plot orders customers by predicted purchases instead (ties again by customer id)
and cuts them into ten equal groups, giving mean predicted against mean actual purchases per
group: a well calibrated model puts the points on the diagonal.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import polars as pl

DECILES = 10
HOLDOUT_COLUMNS = ("customer_id", "frequency", "holdout_purchases", "holdout_revenue")


def _aligned(values: npt.ArrayLike, rows: int, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.shape != (rows,):
        raise ValueError(f"{name} holds {array.size} values for {rows} customers")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} holds missing or infinite values")
    return array


def _groups(rows: int, groups: int) -> np.ndarray:
    """Group numbers 1 to ``groups`` for rows already in order, sizes equal to within one."""
    if rows < groups:
        raise ValueError(f"{rows} customers cannot fill {groups} groups")
    return np.arange(rows, dtype=np.int64) * groups // rows + 1


def _check(frame: pl.DataFrame, columns: tuple[str, ...]) -> None:
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise KeyError(f"the holdout frame lacks {missing}")


def _summaries() -> list[pl.Expr]:
    return [
        pl.col("frequency").min().cast(pl.Int64).alias("frequency_low"),
        pl.col("frequency").max().cast(pl.Int64).alias("frequency_high"),
        pl.len().cast(pl.Int64).alias("customers"),
        pl.col("predicted_purchases").sum(),
        pl.col("holdout_purchases").sum().cast(pl.Int64).alias("actual_purchases"),
        pl.col("predicted_revenue").sum(),
        pl.col("holdout_revenue").sum().cast(pl.Float64).alias("actual_revenue"),
        (pl.col("predicted_purchases") - pl.col("holdout_purchases")).abs().mean().alias("mae_purchases"),
        (pl.col("predicted_revenue") - pl.col("holdout_revenue")).abs().mean().alias("mae_revenue"),
    ]


def holdout_by_decile(
    frame_with_holdout: pl.DataFrame,
    predicted_purchases: npt.ArrayLike,
    predicted_revenue: npt.ArrayLike,
) -> pl.DataFrame:
    """Predicted against actual holdout purchases and revenue per decile of calibration frequency.

    The predictions are aligned with the rows of ``frame_with_holdout``. Returns eleven rows,
    deciles "1" to "10" and then "all".
    """
    _check(frame_with_holdout, HOLDOUT_COLUMNS)
    rows = frame_with_holdout.height
    work = (
        frame_with_holdout.select(HOLDOUT_COLUMNS)
        .with_columns(
            pl.Series("predicted_purchases", _aligned(predicted_purchases, rows, "predicted purchases")),
            pl.Series("predicted_revenue", _aligned(predicted_revenue, rows, "predicted revenue")),
        )
        .sort(["frequency", "customer_id"])
    )
    work = work.with_columns(pl.Series("decile", _groups(rows, DECILES)))
    per_decile = (
        work.group_by("decile").agg(_summaries()).sort("decile").with_columns(pl.col("decile").cast(pl.Utf8))
    )
    overall = work.select(_summaries()).select(pl.lit("all").alias("decile"), pl.all())
    return pl.concat([per_decile, overall], how="vertical")


def calibration_plot(
    frame_with_holdout: pl.DataFrame, predicted_purchases: npt.ArrayLike, bins: int = DECILES
) -> pl.DataFrame:
    """Mean predicted against mean actual holdout purchases in ``bins`` equal groups by prediction."""
    _check(frame_with_holdout, ("customer_id", "holdout_purchases"))
    rows = frame_with_holdout.height
    work = (
        frame_with_holdout.select("customer_id", "holdout_purchases")
        .with_columns(pl.Series("predicted", _aligned(predicted_purchases, rows, "predicted purchases")))
        .sort(["predicted", "customer_id"])
    )
    work = work.with_columns(pl.Series("bin", _groups(rows, bins)))
    return (
        work.group_by("bin")
        .agg(
            pl.len().cast(pl.Int64).alias("customers"),
            pl.col("predicted").min().alias("predicted_low"),
            pl.col("predicted").max().alias("predicted_high"),
            pl.col("predicted").mean().alias("mean_predicted"),
            pl.col("holdout_purchases").cast(pl.Float64).mean().alias("mean_actual"),
        )
        .sort("bin")
    )
