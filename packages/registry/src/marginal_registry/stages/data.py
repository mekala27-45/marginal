"""Stage: the three public datasets, verified, loaded and reduced to committed aggregates.

Writes:
  data/hillstrom/summary.json          arm counts and outcome rates (the raw rows stay external)
  data/retail/purchases.parquet        one row per customer per day, the frame lifetime value fits on
  data/retail/summary.json             what the cleaning removed and why
  data/criteo/summary.json             row count, treated share and outcome rates
  results/manifests/data.json          every figure the documents quote about the data
"""

from __future__ import annotations

import json
from pathlib import Path

from marginal_contracts import SOURCES, Verification, fetch_all, report, source
from marginal_contracts import criteo as criteo_mod
from marginal_contracts import hillstrom as hillstrom_mod
from marginal_contracts import retail as retail_mod
from marginal_core.manifest import Manifest, Scalar, Scribe
from marginal_core.paths import Paths


class DataNotVerified(RuntimeError):
    pass


def run(paths: Paths, as_of: str, seed: int, *, attempt_download: bool = True) -> Manifest:
    external = paths.external
    results = fetch_all(external, attempt_download=attempt_download)
    print(report(results))
    missing = [r for r in results if not r.verified]
    if missing:
        raise DataNotVerified(
            "not every dataset is verified; place the files at the paths above and rerun `make data`"
        )
    manifest = Manifest(as_of=as_of, seed=seed)
    _provenance(manifest, results)
    _hillstrom(paths, manifest)
    _retail(paths, manifest)
    _criteo(paths, manifest)
    out = paths.results / "manifests" / "data.json"
    manifest.save(out)
    return manifest


def _provenance(manifest: Manifest, results: list[Verification]) -> None:
    rows: list[list[Scalar]] = []
    for item in SOURCES:
        status = next(r for r in results if r.key == item.key)
        rows.append(
            [
                item.title,
                item.filename,
                item.license,
                (status.md5 or "none published"),
                (status.sha256 or "")[:16],
                item.rows_expected,
            ]
        )
        manifest.put(
            f"data.{item.key}.sha256",
            status.sha256,
            "text",
            source="static",
            population="the file this build verified",
            origin="marginal_contracts.sources.verify",
        )
        manifest.put(
            f"data.{item.key}.md5",
            status.md5 or "none published",
            "text",
            source="static",
            population="the file this build verified",
            origin="marginal_contracts.sources.verify",
        )
        manifest.put(
            f"data.{item.key}.license",
            item.license,
            "text",
            source="static",
            population="declared terms",
            origin="marginal_contracts.sources",
        )
        manifest.put(
            f"data.{item.key}.url",
            item.url,
            "text",
            source="static",
            population="declared source",
            origin="marginal_contracts.sources",
        )
        manifest.put(
            f"data.{item.key}.citation",
            item.citation,
            "text",
            source="static",
            population="declared source",
            origin="marginal_contracts.sources",
        )
    manifest.put_table(
        "data.provenance",
        ["Dataset", "File", "License", "Published MD5", "SHA-256 (first 16)", "Rows"],
        ["text", "text", "text", "text", "text", "int"],
        rows,
        source="static",
        population="the three public releases",
        origin="marginal_contracts.sources",
    )


def _hillstrom(paths: Paths, manifest: Manifest) -> None:
    frame = hillstrom_mod.load(paths.external / source("hillstrom").filename)
    summary = hillstrom_mod.summary(frame)
    out = paths.data / "hillstrom"
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary.model_dump(), indent=1, sort_keys=True) + "\n")
    w = Scribe(
        manifest,
        source="real:hillstrom",
        population="64,000 recent buyers, 2008",
        origin="marginal_contracts.hillstrom",
    )
    w.put("data.hillstrom.rows", summary.rows, "int")
    for arm, count in summary.arms.items():
        w.put(f"data.hillstrom.arm.{arm}", count, "int")
    w.put("data.hillstrom.visit_rate", summary.visit_rate, "pct2")
    w.put("data.hillstrom.conversion_rate", summary.conversion_rate, "pct2")
    w.put("data.hillstrom.mean_spend", summary.mean_spend, "usd2")


def _retail(paths: Paths, manifest: Manifest) -> None:
    zip_path = paths.external / source("retail").filename
    transactions = retail_mod.read_workbook(
        zip_path, cache=paths.external / "online_retail_ii_sheets.parquet"
    )
    purchases, summary = retail_mod.clean(transactions)
    out = paths.data / "retail"
    out.mkdir(parents=True, exist_ok=True)
    purchases.write_parquet(out / "purchases.parquet")
    (out / "summary.json").write_text(json.dumps(summary.model_dump(), indent=1, sort_keys=True) + "\n")
    w = Scribe(
        manifest,
        source="real:retail",
        population="UK online gift retailer, 2009 to 2011",
        origin="marginal_contracts.retail",
    )
    w.put("data.retail.raw_rows", summary.raw_rows, "int")
    w.put("data.retail.overlap_rows", summary.overlap_rows, "int")
    w.put("data.retail.cancellation_rows", summary.cancellation_rows, "int")
    w.put("data.retail.no_customer_rows", summary.no_customer_rows, "int")
    w.put("data.retail.no_customer_rate", summary.no_customer_rate, "pct1")
    w.put("data.retail.adjustment_rows", summary.adjustment_rows, "int")
    w.put("data.retail.kept_rows", summary.kept_rows, "int")
    w.put("data.retail.customers", summary.customers, "int")
    w.put("data.retail.purchases", summary.purchases, "int")
    w.put("data.retail.first_date", summary.first_date, "text")
    w.put("data.retail.last_date", summary.last_date, "text")
    w.put("data.retail.calibration_end", summary.calibration_end, "text")
    w.put("data.retail.holdout_start", summary.holdout_start, "text")


def _criteo(paths: Paths, manifest: Manifest) -> None:
    raw = paths.external / source("criteo").filename
    lazy = criteo_mod.load(raw, cache=paths.external / "criteo.parquet")
    summary = criteo_mod.summary(lazy)
    out = paths.data / "criteo"
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary.model_dump(), indent=1, sort_keys=True) + "\n")
    w = Scribe(
        manifest, source="real:criteo", population="the full v2.1 release", origin="marginal_contracts.criteo"
    )
    w.put("data.criteo.rows", summary.rows, "int")
    w.put("data.criteo.treated_share", summary.treated_share, "pct1")
    w.put("data.criteo.visit_rate", summary.visit_rate, "pct2")
    w.put("data.criteo.conversion_rate", summary.conversion_rate, "pct2")
    w.put("data.criteo.exposure_rate", summary.exposure_rate, "pct2")


def load_summaries(paths: Paths) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for key in ("hillstrom", "retail", "criteo"):
        path: Path = paths.data / key / "summary.json"
        if path.exists():
            out[key] = json.loads(path.read_text())
    return out
