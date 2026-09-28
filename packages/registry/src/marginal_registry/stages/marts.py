"""Stage: the marts the site reads through DuckDB-WASM, and the site bundle.

Every chart on the site is a query over a parquet file written here from the results the
pipeline produced, never a number typed into a component. The bundle also carries the merged
manifest (for callouts and every printed figure), the policy, and the statement. Written to
web/public/data so the static export ships them.

Files:
  returns.parquet            return per channel by backend with intervals and the truth
  crosscheck.parquet         own beside bayes beside the truth, with the disagreement flag
  contributions.parquet      weekly baseline and channel contributions by backend
  curves.parquet             response curves by backend with the truth curve
  current_spend.parquet      current weekly spend and marginal returns per channel
  recovery.parquet           the recovery study by backend, condition and channel
  recovery_ranks.parquet     rank agreement by backend and condition with intervals over seeds
  attribution.parquet        every rule's share beside the truth and the calibrated model
  budget_plan.parquet        the allocation of each plan beside last year's mix
  budget_surface.parquet     the precomputed slider surface
  budget_comparison.parquet  every plan judged on the true curves
  budget_regret.parquet      the regret study summary
  allowance.parquet          the acquisition cost allowance and where it binds
  geo_series.parquet, geo_placebo.parquet, geo_power.parquet, geo_result.parquet
  calibration.parquet        before and after per backend
  email_effects.parquet, email_segments.parquet, email_srm.parquet
  qini.parquet, policy_value.parquet, quadrants.parquet, targeting_summary.parquet
  clv_deciles.parquet, clv_distribution.parquet, clv_segments.parquet
  kpi.parquet                the latest quarter: sales, baseline and incremental by channel
  manifest.json              the merged manifest
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import polars as pl
from marginal_core.config import CHANNEL_LABELS, CHANNELS, POLICY
from marginal_core.paths import Paths
from marginal_core.statements import BRAND, STATEMENT
from marginal_evaluation import bootstrap_interval

QUARTER_WEEKS = 13
RULE_LABELS = {
    "last_touch": "Last touch",
    "first_touch": "First touch",
    "linear": "Linear",
    "position_based": "Position based",
    "time_decay": "Time decay",
    "shapley": "Shapley",
}
POLICY_LABELS = {
    "t_learner": "T learner",
    "x_learner": "X learner",
    "sure_things": "Sure things",
    "everyone": "Everyone",
}
DATASET_LABELS = {
    "hillstrom": "Hillstrom email experiment (real, 2008)",
    "sim": f"{BRAND} customers (simulated, known truth)",
    "criteo": "Criteo uplift release (real, full v2.1)",
}


def run(paths: Paths) -> list[Path]:
    out = paths.web_data
    out.mkdir(parents=True, exist_ok=True)
    results = paths.results
    written: list[Path] = []

    def write(name: str, frame: pl.DataFrame) -> None:
        target = out / f"{name}.parquet"
        frame.write_parquet(target, compression="zstd")
        written.append(target)

    # Mix models.
    returns = pl.concat(
        [pl.read_parquet(results / "mmm" / f"{b}_returns.parquet") for b in ("own", "bayes")], how="vertical"
    ).with_columns(pl.col("channel").replace_strict(CHANNEL_LABELS).alias("channel_label"))
    write("returns", returns)
    write("crosscheck", _crosscheck(returns))
    contributions = pl.concat(
        [pl.read_parquet(results / "mmm" / f"{b}_contributions.parquet") for b in ("own", "bayes")],
        how="vertical",
    )
    write("contributions", contributions)
    curves = pl.concat(
        [pl.read_parquet(results / "mmm" / f"{b}_curves.parquet") for b in ("own", "bayes")], how="vertical"
    ).with_columns(pl.col("channel").replace_strict(CHANNEL_LABELS).alias("channel_label"))
    write("curves", curves)
    write("current_spend", _current_spend(returns, results))
    recovery = pl.concat(
        [pl.read_parquet(results / "recovery" / f"{b}_summary.parquet") for b in ("own", "bayes")],
        how="vertical",
    ).with_columns(
        pl.col("channel").replace_strict({**CHANNEL_LABELS, "all": "All channels"}).alias("channel_label")
    )
    write("recovery", recovery)
    ranks = pl.concat(
        [pl.read_parquet(results / "recovery" / f"{b}_ranks.parquet") for b in ("own", "bayes")],
        how="vertical",
    )
    write("recovery_ranks", _rank_summary(ranks))

    # Attribution.
    write("attribution", _attribution(results))

    # Budget.
    write("budget_plan", _budget_plans(results))
    surface = pl.read_parquet(results / "budget" / "surface.parquet").with_columns(
        pl.col("channel").replace_strict(CHANNEL_LABELS).alias("channel_label")
    )
    write("budget_surface", surface)
    write("budget_comparison", _budget_comparison(results))
    write("budget_regret", pl.read_parquet(results / "budget" / "regret_summary.parquet"))
    write("allowance", _allowance(results))

    # Experiments.
    write("geo_series", pl.read_parquet(results / "experiments" / "geo_series.parquet"))
    write("geo_placebo", pl.read_parquet(results / "experiments" / "geo_placebo.parquet"))
    write("geo_power", pl.read_parquet(results / "experiments" / "geo_power.parquet"))
    write("geo_result", _geo_result(results))
    write("calibration", _calibration(results))
    write("email_effects", pl.read_parquet(results / "experiments" / "email_effects.parquet"))
    write("email_segments", pl.read_parquet(results / "experiments" / "email_segments.parquet"))
    write("email_srm", _email_srm(results))

    # Targeting.
    qini = []
    values = []
    summaries = []
    for dataset in ("hillstrom", "sim", "criteo"):
        q = pl.read_parquet(results / "targeting" / f"{dataset}_qini.parquet")
        qini.append(q.with_columns(pl.lit(dataset).alias("dataset")))
        v = pl.read_parquet(results / "targeting" / f"{dataset}_policy_value.parquet")
        values.append(v.with_columns(pl.lit(dataset).alias("dataset")))
        summaries.extend(_targeting_summary(results, dataset))
    write("qini", _label_policies(pl.concat(qini, how="vertical")))
    write("policy_value", _label_policies(pl.concat(values, how="diagonal")))
    write("quadrants", _label_policies(pl.read_parquet(results / "targeting" / "sim_quadrants.parquet")))
    write("targeting_summary", _label_policies(pl.DataFrame(summaries)))

    # Lifetime value.
    write("clv_deciles", pl.read_parquet(results / "clv" / "holdout_by_decile.parquet"))
    write("clv_distribution", pl.read_parquet(results / "clv" / "clv_distribution.parquet"))
    write("clv_segments", pl.read_parquet(results / "clv" / "segments.parquet"))

    # The overview.
    write("kpi", _kpi(paths, contributions))

    # The bundle.
    manifest_path = results / "manifest.json"
    if manifest_path.exists():
        shutil.copyfile(manifest_path, out / "manifest.json")
        written.append(out / "manifest.json")
    bundle = {
        "brand": BRAND,
        "statement": STATEMENT,
        "channels": [{"key": c, "label": CHANNEL_LABELS[c]} for c in CHANNELS],
        "policy": POLICY.model_dump(),
        "files": [p.name for p in written],
    }
    (out / "bundle.json").write_text(json.dumps(bundle, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    written.append(out / "bundle.json")
    return written


def _crosscheck(returns: pl.DataFrame) -> pl.DataFrame:
    own = returns.filter(pl.col("backend") == "own").select(
        "channel",
        "channel_label",
        pl.col("roas").alias("own"),
        pl.col("roas_lower").alias("own_lower"),
        pl.col("roas_upper").alias("own_upper"),
        pl.col("roas_true").alias("truth"),
    )
    bayes = returns.filter(pl.col("backend") == "bayes").select(
        "channel",
        pl.col("roas").alias("bayes"),
        pl.col("roas_lower").alias("bayes_lower"),
        pl.col("roas_upper").alias("bayes_upper"),
    )
    joined = own.join(bayes, on="channel", how="left")
    return joined.with_columns(
        ((pl.col("own_lower") > pl.col("bayes_upper")) | (pl.col("bayes_lower") > pl.col("own_upper")))
        .fill_null(False)
        .alias("disagree"),
        ((pl.col("truth") >= pl.col("own_lower")) & (pl.col("truth") <= pl.col("own_upper"))).alias(
            "own_covers"
        ),
        ((pl.col("truth") >= pl.col("bayes_lower")) & (pl.col("truth") <= pl.col("bayes_upper")))
        .fill_null(False)
        .alias("bayes_covers"),
    )


def _current_spend(returns: pl.DataFrame, results: Path) -> pl.DataFrame:
    model = json.loads((results / "mmm" / "own_model.json").read_text(encoding="utf-8"))
    spend = {c["channel"]: float(c["weekly_spend_current"]) for c in model["channels"]}
    rows = []
    for channel in CHANNELS:
        row = {"channel": channel, "channel_label": CHANNEL_LABELS[channel], "spend_current": spend[channel]}
        for backend in ("own", "bayes"):
            sub = returns.filter((pl.col("backend") == backend) & (pl.col("channel") == channel))
            row[f"marginal_{backend}"] = float(sub["marginal_return"][0]) if sub.height else None
            if sub.height:
                row["marginal_true"] = float(sub["marginal_true"][0])
                row[f"half_life_{backend}"] = float(sub["half_life_weeks"][0])
                row["half_life_true"] = float(sub["half_life_true"][0])
        rows.append(row)
    return pl.DataFrame(rows)


def _rank_summary(ranks: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for (backend, condition), sub in ranks.group_by(["backend", "condition"], maintain_order=True):
        values = sub.sort("seed")["rank_agreement"].to_numpy()
        interval = bootstrap_interval(values, seed=0, stream=f"rank {backend} {condition}")
        rows.append(
            {
                "backend": str(backend),
                "condition": str(condition),
                "rho": float(sub["rho"][0]),
                "feedback": bool(sub["feedback"][0]),
                "seeds": int(sub.height),
                "rank_agreement": interval.estimate,
                "lower": interval.lower,
                "upper": interval.upper,
            }
        )
    return pl.DataFrame(rows).sort(["backend", "rho", "feedback"])


def _attribution(results: Path) -> pl.DataFrame:
    table = pl.read_parquet(results / "attribution" / "comparison.parquet")
    summary = json.loads((results / "attribution" / "summary.json").read_text(encoding="utf-8"))
    rows = []
    for row in table.iter_rows(named=True):
        for rule, label in RULE_LABELS.items():
            rows.append(
                {
                    "channel": row["channel"],
                    "channel_label": CHANNEL_LABELS[row["channel"]],
                    "answer": label,
                    "kind": "rule",
                    "share": float(row[f"share_{rule}"]),
                }
            )
        rows.append(
            {
                "channel": row["channel"],
                "channel_label": CHANNEL_LABELS[row["channel"]],
                "answer": "Truth (simulated)",
                "kind": "truth",
                "share": float(row["share_true"]),
            }
        )
        rows.append(
            {
                "channel": row["channel"],
                "channel_label": CHANNEL_LABELS[row["channel"]],
                "answer": str(summary["model_label"]),
                "kind": "model",
                "share": float(row["share_model"]),
            }
        )
    return pl.DataFrame(rows)


def _budget_plans(results: Path) -> pl.DataFrame:
    rows = []
    for label in ("calibrated", "uncalibrated", "truth"):
        plan = json.loads((results / "budget" / f"plan_{label}.json").read_text(encoding="utf-8"))
        for a in plan["allocation"]:
            rows.append(
                {
                    "plan": label,
                    "channel": a["channel"],
                    "channel_label": CHANNEL_LABELS[a["channel"]],
                    "spend": float(a["spend"]),
                    "last_year": float(a["last_year"]),
                    "change": float(a["change"]),
                    "expected_revenue": float(a["expected_revenue"]),
                    "marginal_return": float(a["marginal_return"]),
                    "marginal_profit": float(a["marginal_profit"]),
                    "at_bound": str(a["at_bound"]),
                    "implied_acquisition_cost": a["implied_acquisition_cost"],
                    "expected_profit": float(plan["expected_profit"]),
                    "profit_lower": float(plan["profit_lower"]),
                    "profit_upper": float(plan["profit_upper"]),
                    "model_version": str(plan["model_version"]),
                    "inputs_hash": str(plan["inputs_hash"]),
                }
            )
    return pl.DataFrame(rows)


def _budget_comparison(results: Path) -> pl.DataFrame:
    comparison = json.loads((results / "budget" / "comparison.json").read_text(encoding="utf-8"))
    labels = {
        "calibrated": "Calibrated model's plan",
        "uncalibrated": "Uncalibrated model's plan",
        "truth": "Truth optimal plan",
        "last_year": "Last year's mix",
        "equal_split": "Equal split",
    }
    rows = []
    for key, label in labels.items():
        c = comparison[key]
        rows.append(
            {
                "plan": key,
                "label": label,
                "true_profit_weekly": float(c["true_profit"]),
                "gain_weekly": float(c["gain_over_last_year"]),
                "gain_annual": float(c["gain_over_last_year"]) * 52,
                "expected_profit_weekly": c.get("expected_profit"),
            }
        )
    return pl.DataFrame(rows)


def _allowance(results: Path) -> pl.DataFrame:
    allowance = json.loads((results / "clv" / "allowance.json").read_text(encoding="utf-8"))
    plan = json.loads((results / "budget" / "plan_calibrated.json").read_text(encoding="utf-8"))
    rows = []
    for a in plan["allocation"]:
        rows.append(
            {
                "channel": a["channel"],
                "channel_label": CHANNEL_LABELS[a["channel"]],
                "allowance": float(allowance["allowance_by_channel"][a["channel"]]),
                "implied_acquisition_cost": a["implied_acquisition_cost"],
                "binds": a["at_bound"] in {"allowance", "allowance (infeasible)"},
                "at_bound": str(a["at_bound"]),
                "revenue_per_acquisition": float(allowance["revenue_per_acquisition"]),
            }
        )
    return pl.DataFrame(rows)


def _geo_result(results: Path) -> pl.DataFrame:
    result = json.loads((results / "experiments" / "geo_result.json").read_text(encoding="utf-8"))
    design = json.loads((results / "experiments" / "geo_design.json").read_text(encoding="utf-8"))
    registration = design.get("registration", {})
    did = result["did"]
    sc = result["synthetic_control"]
    return pl.DataFrame(
        [
            {
                "experiment_id": str(result["experiment_id"]),
                "plan_hash": str(result["plan_hash"]),
                "registered_at": str(registration.get("registered_at", "")),
                "registered_via": str(registration.get("registered_via", "")),
                "channel": str(design["design"]["channel"]),
                "channel_label": CHANNEL_LABELS[str(design["design"]["channel"])],
                "start_week": int(design["design"]["start_week"]),
                "end_week": int(design["design"]["end_week"]),
                "treated_geos": len(design["design"]["treated_geos"]),
                "control_geos": len(design["design"]["control_geos"]),
                "did_estimate": float(did["incremental_revenue"]),
                "did_lower": float(did["lower"]),
                "did_upper": float(did["upper"]),
                "sc_estimate": float(sc["incremental_revenue"]),
                "sc_lower": float(sc["lower"]),
                "sc_upper": float(sc["upper"]),
                "sc_p_value": float(sc["p_value"]),
                "sc_largest_weight": float(sc["largest_weight"]),
                "placebo_permutations": int(sc["placebo_permutations"]),
                "truth": float(result["truth"]),
                "srm_p_value": float(result["srm"]["p_value"]),
                "srm_passed": bool(result["srm"]["passed"]),
                "power_at_true_effect": float(design["design"].get("power_at_true_effect", float("nan"))),
            }
        ]
    )


def _calibration(results: Path) -> pl.DataFrame:
    manifest = json.loads((results / "manifests" / "calibrate.json").read_text(encoding="utf-8"))
    values = manifest["values"]
    rows = []
    for backend in ("own", "bayes"):
        path = results / "calibrate" / f"{backend}_before_after.json"
        if not path.exists():
            continue
        s = json.loads(path.read_text(encoding="utf-8"))

        def v(key: str) -> float | None:
            entry = values.get(f"calibrate.{backend}.recovery.{key}")  # noqa: B023
            return float(entry["value"]) if entry and entry["value"] is not None else None

        rows.append(
            {
                "backend": backend,
                "channel": s["channel"],
                "channel_label": CHANNEL_LABELS[s["channel"]],
                "roas_before": s["roas_before"],
                "roas_before_lower": s["roas_before_lower"],
                "roas_before_upper": s["roas_before_upper"],
                "roas_after": s["roas_after"],
                "roas_after_lower": s["roas_after_lower"],
                "roas_after_upper": s["roas_after_upper"],
                "roas_true": s["roas_true"],
                "implied_lift_before": s["implied_lift_before"],
                "implied_lift_after": s["implied_lift_after"],
                "experiment_lift": s["experiment_lift"],
                "truth_lift": s["truth_lift"],
                "covers_before": s["covers_before"],
                "covers_after": s["covers_after"],
                "recovery_seeds": v("seeds"),
                "recovery_error_before": v("error_before"),
                "recovery_error_after": v("error_after"),
                "recovery_coverage_before": v("coverage_before"),
                "recovery_coverage_after": v("coverage_after"),
                "tested_error_before": v("tested_error_before"),
                "tested_error_after": v("tested_error_after"),
            }
        )
    return pl.DataFrame(rows)


def _email_srm(results: Path) -> pl.DataFrame:
    analysis = json.loads((results / "experiments" / "email_analysis.json").read_text(encoding="utf-8"))
    srm = analysis["srm"]
    rows = []
    for arm, observed in srm["observed"].items():
        rows.append(
            {
                "arm": arm,
                "observed": int(observed),
                "expected": float(srm["expected"][arm]),
                "p_value": float(srm["p_value"]),
                "passed": bool(srm["passed"]),
                "alpha": float(srm["alpha"]),
            }
        )
    return pl.DataFrame(rows)


def _targeting_summary(results: Path, dataset: str) -> list[dict[str, object]]:
    summary = json.loads((results / "targeting" / f"{dataset}_summary.json").read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    for p in summary["policies"]:
        test = p["value_test"]
        rows.append(
            {
                "dataset": dataset,
                "dataset_label": DATASET_LABELS[dataset],
                "policy": p["policy"],
                "chosen_share": p["chosen_share"],
                "interior": bool(p["interior"]["interior"]),
                "interior_reason": str(p["interior"]["reason"]),
                "qini": p["qini"]["estimate"],
                "qini_lower": p["qini"]["lower"],
                "qini_upper": p["qini"]["upper"],
                "top_decile_uplift": p["top_decile_uplift"],
                "profit_per_thousand_test": test["profit_per_thousand"],
                "profit_per_thousand_contacted_test": test["profit_per_thousand_contacted"],
                "profit_per_thousand_validation": p["value_validation"]["profit_per_thousand"],
                "pehe": p.get("pehe"),
                "oracle_regret": p.get("oracle_regret"),
                "cost_per_contact": summary["settings"]["cost_per_contact"],
                "margin_on_spend": summary["settings"]["margin_on_spend"],
                "test_rows": summary["rows"]["test"],
            }
        )
    return rows


def _label_policies(frame: pl.DataFrame) -> pl.DataFrame:
    if "policy" in frame.columns:
        frame = frame.with_columns(
            pl.col("policy").replace_strict(POLICY_LABELS, default=pl.col("policy")).alias("policy_label")
        )
    if "dataset" in frame.columns and "dataset_label" not in frame.columns:
        frame = frame.with_columns(
            pl.col("dataset").replace_strict(DATASET_LABELS, default=pl.col("dataset")).alias("dataset_label")
        )
    return frame


def _kpi(paths: Paths, contributions: pl.DataFrame) -> pl.DataFrame:
    national = pl.read_parquet(paths.sim / "national.parquet")
    last = national.sort("week").tail(QUARTER_WEEKS)
    rows: list[dict[str, object]] = []
    sales = float(last["sales"].sum())
    rows.append({"series": "sales", "label": "Sales", "backend": "truth", "value": sales, "truth": sales})
    baseline_true = float(last["baseline_true"].sum())
    for backend in ("own", "bayes"):
        sub = contributions.filter(pl.col("backend") == backend).sort("week").tail(QUARTER_WEEKS)
        if sub.height == 0:
            continue
        rows.append(
            {
                "series": "baseline",
                "label": "Baseline",
                "backend": backend,
                "value": float(sub["baseline"].sum()),
                "truth": baseline_true,
            }
        )
        for channel in CHANNELS:
            rows.append(
                {
                    "series": channel,
                    "label": CHANNEL_LABELS[channel],
                    "backend": backend,
                    "value": float(sub[channel].sum()),
                    "truth": float(last[f"incremental_true_{channel}"].sum()),
                }
            )
    spend_total = float(sum(last[f"spend_{c}"].sum() for c in CHANNELS))
    rows.append(
        {
            "series": "spend",
            "label": "Media spend",
            "backend": "truth",
            "value": spend_total,
            "truth": spend_total,
        }
    )
    frame = pl.DataFrame(rows)
    weeks = last["week"].to_list()
    return frame.with_columns(
        pl.lit(int(weeks[0])).alias("first_week"),
        pl.lit(int(weeks[-1])).alias("last_week"),
        pl.lit(QUARTER_WEEKS).alias("weeks"),
    )
