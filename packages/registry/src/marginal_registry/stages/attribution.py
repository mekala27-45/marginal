"""Stage: attribution rules beside the truth and the calibrated mix model.

Writes under results/attribution:
  comparison.parquet   one row per channel: credit and share under each of the six rules, the
                       true incremental share, and the calibrated own model's share
  grades.parquet       per rule: mean and largest share error, rank agreement, the channel it
                       over credits most and by how much
  coalitions.parquet   the 128 coalitions the Shapley values were computed from
  summary.json         the callout figures
and results/manifests/attribution.json. The mix model's share comes from the calibrated own
export when the calibration stage has run, otherwise the uncalibrated one, and the manifest
says which.
"""

from __future__ import annotations

import json

import polars as pl
from marginal_attribution import RULE_LABELS, RULES, comparison, grade, over_credit
from marginal_core.config import CHANNEL_LABELS, POLICY
from marginal_core.manifest import Manifest, Scalar, Scribe
from marginal_core.paths import Paths
from marginal_mmm import ModelExport

ORIGIN = "marginal_attribution"


def run(paths: Paths, as_of: str, seed: int, **options: str) -> Manifest:
    out = paths.results / "attribution"
    out.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(as_of=as_of, seed=seed)
    touches = pl.read_parquet(paths.sim / "paths.parquet")
    users = pl.read_parquet(paths.sim / "path_users.parquet")
    model, model_label = _model(paths)

    table, coalitions = comparison(touches, users, model)
    grades = grade(table)
    table.write_parquet(out / "comparison.parquet")
    coalitions.write_parquet(out / "coalitions.parquet")
    pl.DataFrame([g.model_dump() for g in grades]).write_parquet(out / "grades.parquet")

    conversions = int(users["converted"].sum())
    incremental_expected = float(table["credit_true_expected"].sum())
    last_share, true_share, points = over_credit(table, "last_touch", POLICY.lift_test_channel)
    worst = max(grades, key=lambda g: g.over_credit_points)
    coalitions_observed = int((coalitions["paths_exact"] > 0).sum())
    sums_to_conversions = bool(abs(float(table["credit_shapley"].sum()) - conversions) < 1e-6)
    summary = {
        "paths": int(users.height),
        "conversions": conversions,
        "incremental_conversions_expected": incremental_expected,
        "model_version": model.version,
        "model_label": model_label,
        "over_credit_channel": POLICY.lift_test_channel,
        "last_touch_share": last_share,
        "true_share": true_share,
        "over_credit_points": points,
        "worst_rule": worst.rule,
        "worst_points": worst.over_credit_points,
        "coalitions_observed": coalitions_observed,
        "shapley_sums_to_conversions": sums_to_conversions,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    population = f"{users.height:,} user paths, demonstration seed"
    rules = Scribe(manifest, source="simulated", model="rules", population=population, origin=ORIGIN)
    rules.put("attribution.paths", users.height, "int")
    rules.put("attribution.conversions", conversions, "int")
    rules.put("attribution.incremental_conversions_expected", incremental_expected, "int")
    rules.put("attribution.incremental_share_of_conversions", incremental_expected / conversions, "pct0")
    rules.put("attribution.half_life_days", POLICY.attribution_half_life_days, "float1")
    rules.put("attribution.shapley.coalitions", coalitions.height, "int")
    rules.put("attribution.shapley.coalitions_observed", coalitions_observed, "int")
    rules.put(
        "attribution.shapley.sums_to_conversions",
        "yes" if sums_to_conversions else "no",
        "text",
    )
    for rule in RULES:
        for row in table.iter_rows(named=True):
            rules.put(f"attribution.share.{rule}.{row['channel']}", row[f"share_{rule}"], "pct1")
    for row in table.iter_rows(named=True):
        rules.put(f"attribution.share.true.{row['channel']}", row["share_true"], "pct1")

    # The callout: the channel every rule over credits, by how much, and what the model says.
    channel = POLICY.lift_test_channel
    model_row = table.filter(pl.col("channel") == channel).row(0, named=True)
    rules.put("attribution.over_credit.channel", CHANNEL_LABELS[channel], "text")
    rules.put("attribution.over_credit.last_touch_share", last_share, "pct1")
    rules.put("attribution.over_credit.true_share", true_share, "pct1")
    rules.put("attribution.over_credit.points", points, "float1")
    rules.put("attribution.over_credit.ratio", last_share / true_share if true_share > 0 else None, "float1")
    rules.put("attribution.over_credit.worst_rule", RULE_LABELS[worst.rule], "text")
    rules.put("attribution.over_credit.worst_points", worst.over_credit_points, "float1")
    rules.put(
        "attribution.over_credit.every_rule",
        "yes" if all(g.over_credits_most == channel for g in grades) else "no",
        "text",
    )

    own = Scribe(manifest, source="simulated", model="own", population="demonstration brand", origin=ORIGIN)
    own.put("attribution.model_version", model.version, "text")
    own.put("attribution.model_label", model_label, "text")
    own.put("attribution.over_credit.model_share", model_row["share_model"], "pct1")
    for row in table.iter_rows(named=True):
        own.put(f"attribution.share.model.{row['channel']}", row["share_model"], "pct1")

    mixed = Scribe(manifest, source="simulated", model="both", population=population, origin=ORIGIN)
    columns = ["Channel", *[RULE_LABELS[r] for r in RULES], "Truth (simulated)", model_label]
    formats = ["text"] + ["pct1"] * (len(RULES) + 2)
    rows: list[list[Scalar]] = []
    for row in table.iter_rows(named=True):
        rows.append(
            [
                CHANNEL_LABELS[str(row["channel"])],
                *[float(row[f"share_{r}"]) for r in RULES],
                float(row["share_true"]),
                float(row["share_model"]),
            ]
        )
    mixed.table("attribution.comparison", columns, formats, rows)
    grade_rows: list[list[Scalar]] = [
        [
            RULE_LABELS[g.rule],
            g.mean_abs_error_points,
            g.max_abs_error_points,
            g.rank_agreement,
            CHANNEL_LABELS[g.over_credits_most],
            g.over_credit_points,
            g.over_credit_ratio,
        ]
        for g in grades
    ]
    rules.table(
        "attribution.grades",
        [
            "Rule",
            "Mean share error (points)",
            "Largest share error (points)",
            "Rank agreement with truth",
            "Over credits most",
            "By (points)",
            "Ratio to truth",
        ],
        ["text", "float1", "float1", "float2", "text", "float1", "float1"],
        grade_rows,
    )
    for g in grades:
        rules.put(f"attribution.grade.{g.rule}.mean_abs_error_points", g.mean_abs_error_points, "float1")
        rules.put(f"attribution.grade.{g.rule}.rank_agreement", g.rank_agreement, "float2")
    manifest.save(paths.results / "manifests" / "attribution.json")
    return manifest


def _model(paths: Paths) -> tuple[ModelExport, str]:
    calibrated = paths.results / "calibrate" / "own_calibrated_model.json"
    if calibrated.exists():
        return ModelExport.model_validate(
            json.loads(calibrated.read_text(encoding="utf-8"))
        ), "Calibrated model"
    uncalibrated = paths.results / "mmm" / "own_model.json"
    return ModelExport.model_validate(
        json.loads(uncalibrated.read_text(encoding="utf-8"))
    ), "Uncalibrated model"
