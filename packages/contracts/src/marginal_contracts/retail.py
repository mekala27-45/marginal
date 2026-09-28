"""Online Retail II as a purchase history: one row per customer per day.

The workbook's two sheets overlap: both hold 1 to 9 December 2010, so the first sheet is cut
at the boundary and the rows it dropped are published. Cancellations are removed by the
invoice prefix (an invoice starting with C is a credit note), rows without a customer id are
excluded and the exclusion rate is published, and non positive quantities or prices that
survive both filters are dropped as adjustments. The calibration window runs from the first
transaction to 30 November 2010; the holdout runs from 1 December 2010 to the end of the file.
"""

from __future__ import annotations

import datetime as dt
import zipfile
from pathlib import Path

import polars as pl
from marginal_core.model import StrictModel

CALIBRATION_END = dt.date(2010, 11, 30)
HOLDOUT_START = dt.date(2010, 12, 1)
SHEETS = ("Year 2009-2010", "Year 2010-2011")
SHEET_BOUNDARY = dt.date(2010, 12, 1)


class RetailSummary(StrictModel):
    raw_rows: int
    overlap_rows: int
    cancellation_rows: int
    no_customer_rows: int
    no_customer_rate: float
    adjustment_rows: int
    kept_rows: int
    customers: int
    purchases: int
    first_date: str
    last_date: str
    calibration_end: str
    holdout_start: str


def read_workbook(zip_path: Path, cache: Path | None = None) -> pl.DataFrame:
    """The two sheets as one frame of transactions, cached as parquet beside the zip."""
    if cache is not None and cache.exists():
        return pl.read_parquet(cache)
    with zipfile.ZipFile(zip_path) as archive:
        name = next(n for n in archive.namelist() if n.endswith(".xlsx"))
        workbook = zip_path.parent / name
        if not workbook.exists():
            archive.extract(name, zip_path.parent)
    # Invoice and StockCode are read as text explicitly: calamine infers a numeric column from
    # the first rows and turns every credit note (an invoice starting with C) into a null.
    text = {"Invoice": pl.String, "StockCode": pl.String, "Description": pl.String, "Country": pl.String}
    frames = [
        pl.read_excel(workbook, sheet_name=sheet, engine="calamine", schema_overrides=text).with_columns(
            pl.lit(index).cast(pl.Int8).alias("sheet")
        )
        for index, sheet in enumerate(SHEETS)
    ]
    frame = pl.concat(frames, how="vertical_relaxed")
    frame = frame.rename({"Customer ID": "customer_id"})
    frame = frame.with_columns(
        pl.col("Invoice").cast(pl.Utf8),
        pl.col("StockCode").cast(pl.Utf8),
        pl.col("Quantity").cast(pl.Float64),
        pl.col("Price").cast(pl.Float64),
        pl.col("customer_id").cast(pl.Float64),
        pl.col("InvoiceDate").cast(pl.Datetime),
    )
    if cache is not None:
        frame.write_parquet(cache)
    return frame


def drop_sheet_overlap(frame: pl.DataFrame) -> tuple[pl.DataFrame, int]:
    """The first sheet ends on 9 December 2010 and the second begins on 1 December 2010; the
    first sheet's copy of those nine days is dropped so no invoice line is counted twice."""
    if "sheet" not in frame.columns:
        return frame, 0
    overlap = (pl.col("sheet") == 0) & (pl.col("InvoiceDate").dt.date() >= SHEET_BOUNDARY)
    dropped = int(frame.filter(overlap).height)
    return frame.filter(~overlap).drop("sheet"), dropped


def clean(frame: pl.DataFrame) -> tuple[pl.DataFrame, RetailSummary]:
    raw_rows = frame.height
    frame, overlap_rows = drop_sheet_overlap(frame)
    cancellations = frame.filter(pl.col("Invoice").str.starts_with("C"))
    kept = frame.filter(~pl.col("Invoice").str.starts_with("C"))
    no_customer = kept.filter(pl.col("customer_id").is_null())
    kept = kept.filter(pl.col("customer_id").is_not_null())
    adjustments = kept.filter((pl.col("Quantity") <= 0) | (pl.col("Price") <= 0))
    kept = kept.filter((pl.col("Quantity") > 0) & (pl.col("Price") > 0))
    kept = kept.with_columns(
        (pl.col("Quantity") * pl.col("Price")).alias("revenue"),
        pl.col("InvoiceDate").dt.date().alias("day"),
        pl.col("customer_id").cast(pl.Int64),
    )
    purchases = (
        kept.group_by(["customer_id", "day"])
        .agg(pl.col("revenue").sum().alias("revenue"), pl.len().alias("lines"))
        .sort(["customer_id", "day"])
    )
    summary = RetailSummary(
        raw_rows=raw_rows,
        overlap_rows=overlap_rows,
        cancellation_rows=cancellations.height,
        no_customer_rows=no_customer.height,
        no_customer_rate=no_customer.height / max(raw_rows - overlap_rows - cancellations.height, 1),
        adjustment_rows=adjustments.height,
        kept_rows=kept.height,
        customers=purchases["customer_id"].n_unique(),
        purchases=purchases.height,
        first_date=str(purchases["day"].min()),
        last_date=str(purchases["day"].max()),
        calibration_end=str(CALIBRATION_END),
        holdout_start=str(HOLDOUT_START),
    )
    return purchases, summary


def split_windows(purchases: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    calibration = purchases.filter(pl.col("day") <= CALIBRATION_END)
    holdout = purchases.filter(pl.col("day") >= HOLDOUT_START)
    return calibration, holdout
