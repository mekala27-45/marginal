from __future__ import annotations

import datetime as dt
import gzip
from pathlib import Path

import polars as pl
import pytest
from marginal_contracts import SOURCES, criteo, fetch_all, hillstrom, retail, source, verify
from marginal_core.hashing import file_md5, file_sha256


def test_every_source_declares_terms_and_a_checksum() -> None:
    assert [s.key for s in SOURCES] == ["hillstrom", "retail", "criteo"]
    for item in SOURCES:
        assert item.sha256 and len(item.sha256) == 64
        assert item.license and item.terms and item.citation
    assert source("criteo").license.startswith("CC BY-NC-SA")


def test_verify_reports_missing_and_mismatching_copies(tmp_path: Path) -> None:
    item = source("hillstrom")
    missing = verify(tmp_path, item)
    assert not missing.present and not missing.verified and item.filename in missing.detail
    (tmp_path / item.filename).write_bytes(b"not the file")
    wrong = verify(tmp_path, item)
    assert wrong.present and not wrong.verified and "mismatch" in wrong.detail


def test_verify_accepts_a_matching_copy(tmp_path: Path) -> None:
    item = source("retail").model_copy(update={"sha256": None, "md5": None})
    path = tmp_path / item.filename
    path.write_bytes(b"payload")
    item = item.model_copy(update={"sha256": file_sha256(path), "md5": file_md5(path)})
    assert verify(tmp_path, item).verified


def test_fetch_all_without_download_never_touches_the_network(tmp_path: Path) -> None:
    results = fetch_all(tmp_path, attempt_download=False)
    assert len(results) == 3 and not any(r.verified for r in results)


def _hillstrom_file(tmp_path: Path) -> Path:
    rows = [
        "recency,history_segment,history,mens,womens,zip_code,newbie,channel,segment,visit,conversion,spend",
        "10,2) $100 - $200,142.44,1,0,Surburban,0,Phone,Womens E-Mail,0,0,0.0",
        "6,3) $200 - $350,329.08,1,1,Rural,1,Web,No E-Mail,1,0,0.0",
        "7,1) $0 - $100,80.5,0,1,Urban,0,Multichannel,Mens E-Mail,1,1,29.99",
    ]
    path = tmp_path / "h.csv.gz"
    with gzip.open(path, "wt") as handle:
        handle.write("\n".join(rows) + "\n")
    return path


def test_hillstrom_loader_codes_arms_and_features(tmp_path: Path) -> None:
    frame = hillstrom.load(_hillstrom_file(tmp_path))
    assert frame["arm"].to_list() == ["womens", "control", "mens"]
    assert frame["customer_id"].to_list() == [0, 1, 2]
    assert frame["zip_urban"].to_list() == [0, 0, 1]
    assert frame["channel_web"].to_list() == [0, 1, 0]
    assert frame["history_decile"].to_list() == [2, 3, 1]
    summary = hillstrom.summary(frame)
    assert summary.arms == {"control": 1, "mens": 1, "womens": 1}
    assert summary.conversion_rate == pytest.approx(1 / 3)


def test_hillstrom_loader_rejects_a_different_schema(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv.gz"
    with gzip.open(path, "wt") as handle:
        handle.write("a,b\n1,2\n")
    with pytest.raises(ValueError, match="unexpected Hillstrom columns"):
        hillstrom.load(path)


def _transactions() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "Invoice": ["489434", "489434", "C489435", "489436", "489437", "489438"],
            "StockCode": ["85048", "79323P", "85048", "22041", "22041", "22041"],
            "Description": ["a", "b", "a", "c", "c", "c"],
            "Quantity": [12.0, 12.0, -12.0, 1.0, 0.0, 2.0],
            "InvoiceDate": [
                dt.datetime(2009, 12, 1, 7, 45),
                dt.datetime(2009, 12, 1, 7, 45),
                dt.datetime(2009, 12, 2, 9, 0),
                dt.datetime(2010, 12, 1, 9, 0),
                dt.datetime(2010, 12, 2, 9, 0),
                dt.datetime(2011, 1, 2, 9, 0),
            ],
            "Price": [6.95, 6.75, 6.95, 2.1, 2.1, 2.1],
            "customer_id": [13085.0, 13085.0, 13085.0, 13085.0, 13085.0, None],
            "Country": ["United Kingdom"] * 6,
        }
    )


def test_retail_cleaning_removes_credit_notes_missing_ids_and_adjustments() -> None:
    purchases, summary = retail.clean(_transactions())
    assert summary.cancellation_rows == 1
    assert summary.no_customer_rows == 1
    assert summary.adjustment_rows == 1
    assert summary.kept_rows == 3
    assert summary.customers == 1
    assert purchases.height == 2
    assert purchases["revenue"].to_list() == pytest.approx([12 * 6.95 + 12 * 6.75, 2.1])
    calibration, holdout = retail.split_windows(purchases)
    assert calibration.height == 1 and holdout.height == 1
    assert summary.no_customer_rate == pytest.approx(1 / 5)


def test_criteo_loader_and_summary(tmp_path: Path) -> None:
    header = ",".join(criteo.RAW_COLUMNS)
    lines = [
        header,
        ",".join(["0.5"] * 12 + ["1", "0", "1", "0"]),
        ",".join(["0.1"] * 12 + ["0", "1", "1", "1"]),
    ]
    raw = tmp_path / "c.csv.gz"
    with gzip.open(raw, "wt") as handle:
        handle.write("\n".join(lines) + "\n")
    cache = tmp_path / "c.parquet"
    lazy = criteo.load(raw, cache=cache)
    assert cache.exists()
    summary = criteo.summary(lazy)
    assert summary.rows == 2 and summary.treated_share == 0.5 and summary.visit_rate == 1.0
    again = criteo.load(raw, cache=cache).collect()
    assert again["row_id"].to_list() == [0, 1]
    assert again.schema["f0"] == pl.Float32


@pytest.mark.external
def test_real_files_verify_and_the_derived_summaries_match_them(root: Path) -> None:
    import json

    results = fetch_all(root / "data" / "external", attempt_download=False)
    assert all(r.verified for r in results)
    summary = json.loads((root / "data" / "hillstrom" / "summary.json").read_text())
    assert summary["rows"] == 64000
    assert sum(summary["arms"].values()) == 64000
    retail_summary = json.loads((root / "data" / "retail" / "summary.json").read_text())
    assert retail_summary["raw_rows"] == 1067371
    assert retail_summary["cancellation_rows"] > 19000
    criteo_summary = json.loads((root / "data" / "criteo" / "summary.json").read_text())
    assert criteo_summary["rows"] == 13979592
