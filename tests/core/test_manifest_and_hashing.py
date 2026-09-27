from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest
from marginal_core.formats import format_value
from marginal_core.hashing import design_hash
from marginal_core.manifest import Manifest
from marginal_core.seeds import rng, seeded_permutation, seeded_split
from marginal_core.statements import STATEMENT, contains_statement, statement_markdown


def _manifest() -> Manifest:
    m = Manifest(as_of="2026-09-27", seed=12)
    m.put(
        "mmm.own.roas.email",
        2.4137,
        "float2",
        source="simulated",
        model="own",
        population="156 weeks",
        origin="test",
    )
    m.put_table(
        "mmm.cross_check",
        ["Channel", "own", "bayes", "Truth"],
        ["text", "float2", "float2", "float2"],
        [["Email", 2.41, 2.39, 2.50]],
        source="simulated",
        model="both",
        population="demonstration seed",
        origin="test",
    )
    return m


def test_manifest_formats_and_labels() -> None:
    m = _manifest()
    assert m.text("mmm.own.roas.email") == "2.41"
    assert "model own" in m.label("mmm.own.roas.email")
    assert "seed 12" in m.label("mmm.own.roas.email")
    assert m.table_markdown("mmm.cross_check").startswith("| Channel | own | bayes | Truth |")


def test_manifest_rejects_duplicate_and_undotted_keys() -> None:
    m = _manifest()
    with pytest.raises(ValueError, match="written twice"):
        m.put("mmm.own.roas.email", 1, "int", source="simulated", population="p", origin="o")
    with pytest.raises(ValueError, match="dotted"):
        m.put("nodots", 1, "int", source="simulated", population="p", origin="o")


def test_manifest_rejects_unknown_source_model_and_format() -> None:
    m = _manifest()
    with pytest.raises(ValueError, match="unknown source"):
        m.put("a.b", 1, "int", source="vendor", population="p", origin="o")
    with pytest.raises(ValueError, match="unknown model"):
        m.put("a.c", 1, "int", source="simulated", model="magic", population="p", origin="o")
    with pytest.raises(KeyError, match="unknown format"):
        m.put("a.d", 1, "money", source="simulated", population="p", origin="o")


def test_manifest_round_trips_and_cleans_floats(tmp_path: Path) -> None:
    m = _manifest()
    m.put("x.nan", float("nan"), "float2", source="static", population="p", origin="o")
    m.put("x.long", 1 / 3, "float4", source="static", population="p", origin="o")
    path = tmp_path / "manifest.json"
    m.save(path)
    again = Manifest.load(path)
    assert again.raw("x.nan") is None
    assert again.text("x.nan") == "not applicable"
    assert again.raw("x.long") == 0.3333333333
    assert json.loads(path.read_text())["values"]["x.long"]["value"] == 0.3333333333


def test_manifest_seeds_and_condition_in_label() -> None:
    m = Manifest(as_of="2026-09-27", seed=1)
    m.put(
        "r.bias",
        0.1,
        "float3",
        source="simulated",
        model="own",
        population="p",
        origin="o",
        seeds=20,
        condition="rho 0.9, feedback on",
    )
    assert "20 seeds" in m.label("r.bias")
    assert "condition rho 0.9, feedback on" in m.label("r.bias")


def test_formats() -> None:
    assert format_value(0.1234, "pct1") == "12.3%"
    assert format_value(-0.0004, "spct1") == "0.0%"
    assert format_value(1234567, "usd0") == "$1,234,567"
    assert format_value(None, "int") == "not applicable"
    assert format_value("own", "text") == "own"


def test_design_hash_is_order_independent_and_sensitive() -> None:
    a = design_hash({"geos": [1, 2, 3], "weeks": 8, "channel": "email"})
    b = design_hash({"weeks": 8, "channel": "email", "geos": [1, 2, 3]})
    c = design_hash({"geos": [1, 2, 3], "weeks": 9, "channel": "email"})
    assert a == b
    assert a != c
    assert len(a) == 16


def test_statement_helpers() -> None:
    assert statement_markdown().startswith("> ")
    assert contains_statement("x " + " ".join(STATEMENT.split()) + " y")
    assert not contains_statement("A page without it")


def test_seeded_split_does_not_depend_on_row_order() -> None:
    frame = pl.DataFrame({"customer_id": list(range(1000)), "y": [i % 3 for i in range(1000)]})
    shuffled = frame.sample(fraction=1.0, shuffle=True, seed=99)
    a = seeded_split(frame, "customer_id", 7, [0.6, 0.2, 0.2], ["train", "valid", "test"])
    b = seeded_split(shuffled, "customer_id", 7, [0.6, 0.2, 0.2], ["train", "valid", "test"])
    assert a["split"].to_list() == b["split"].to_list()
    counts = a["split"].value_counts().sort("split")
    assert counts.filter(pl.col("split") == "train")["count"][0] > 500


def test_seeded_streams_differ_and_repeat() -> None:
    assert rng(1, "a").random() != rng(1, "b").random()
    assert rng(1, "a").random() == rng(1, "a").random()
    assert seeded_permutation(5, 3, "x").tolist() == seeded_permutation(5, 3, "x").tolist()
