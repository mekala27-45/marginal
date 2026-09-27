"""The Criteo uplift dataset as a typed frame, cached as parquet beside the raw file.

Twelve anonymized features, a treatment flag (about 85 percent treated), and visit,
conversion and exposure outcomes. The row id is the row's position in the public file.
The features are stored as 32 bit floats: 13.9 million rows at 64 bits is more memory
than the pipeline machine has, and the learners do not use the extra precision.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
from marginal_core.model import StrictModel

FEATURES = [f"f{i}" for i in range(12)]
RAW_COLUMNS = [*FEATURES, "treatment", "conversion", "visit", "exposure"]


class CriteoSummary(StrictModel):
    rows: int
    treated_share: float
    visit_rate: float
    conversion_rate: float
    exposure_rate: float


def load(raw: Path, cache: Path | None = None) -> pl.LazyFrame:
    if cache is not None and cache.exists():
        return pl.scan_parquet(cache)
    schema: dict[str, type[pl.DataType]] = {f: pl.Float32 for f in FEATURES}
    schema.update({"treatment": pl.Int8, "conversion": pl.Int8, "visit": pl.Int8, "exposure": pl.Int8})
    lazy = pl.scan_csv(raw, schema=schema).with_row_index("row_id")
    if cache is not None:
        lazy.sink_parquet(cache)
        return pl.scan_parquet(cache)
    return lazy


def summary(lazy: pl.LazyFrame) -> CriteoSummary:
    stats = lazy.select(
        pl.len().alias("rows"),
        pl.col("treatment").mean().alias("treated_share"),
        pl.col("visit").mean().alias("visit_rate"),
        pl.col("conversion").mean().alias("conversion_rate"),
        pl.col("exposure").mean().alias("exposure_rate"),
    ).collect()
    row = stats.row(0, named=True)
    return CriteoSummary(
        rows=int(row["rows"]),
        treated_share=float(row["treated_share"]),
        visit_rate=float(row["visit_rate"]),
        conversion_rate=float(row["conversion_rate"]),
        exposure_rate=float(row["exposure_rate"]),
    )
