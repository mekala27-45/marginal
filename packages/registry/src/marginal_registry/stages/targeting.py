"""Stage: uplift targeting on Hillstrom, on the simulator, and on Criteo.

Every dataset goes through marginal_targeting.run_protocol: split by customer (sorted, seeded),
fit on the training split, choose the share to contact on the validation split, report on the
test split. Four policies are compared on the same customers: the T learner, the X learner,
the sure things rule and everyone. Writes under results/targeting:
  hillstrom_qini.parquet, sim_qini.parquet, criteo_qini.parquet
      Qini curves on the test split per policy, with the paired bootstrap band, the random
      diagonal and the observed uplift among the contacted
  hillstrom_policy_value.parquet, sim_policy_value.parquet, criteo_policy_value.parquet
      policy value curves per policy on the validation and the test split
  sim_quadrants.parquet
      the share of each true quadrant each policy contacts at its chosen share
  hillstrom_summary.json, sim_summary.json, criteo_summary.json
      settings, split sizes, per policy records and the paired Qini differences
and results/manifests/targeting.json.

Hillstrom is the men's email against no email (the women's arm is dropped), outcome conversion,
valued by the spend it causes. The simulator is the demonstration customers under the coin
assignment (randomized_view, not the sure things assignment), where PEHE, the quadrants and the
oracle regret can be read because both potential outcomes are known. Criteo is the full v2.1 release, every row: the learners are fit on a seeded
2,000,000 row subsample of the training split and every test row is scored. Criteo publishes no
value per visit and no cost per impression, so its policy value is incremental visits per
thousand users, with no cost assumed.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from marginal_contracts import criteo, hillstrom, source
from marginal_core.config import POLICY
from marginal_core.manifest import Manifest, Scalar, Scribe
from marginal_core.paths import Paths
from marginal_sim.customers import FEATURES as SIM_FEATURES
from marginal_sim.customers import QUADRANTS, randomized_view
from marginal_targeting import (
    LEARNERS,
    SHARE_GRID,
    LearnerParams,
    ProtocolResult,
    contact_mask,
    oracle_regret,
    pehe,
    quadrant_shares_contacted,
    run_protocol,
)
from marginal_targeting.learners import SPLIT_NAMES, SPLIT_SHARES

ORIGIN = "marginal_targeting.protocol"
POLICY_LABELS = {
    "t_learner": "T learner",
    "x_learner": "X learner",
    "sure_things": "Sure things",
    "everyone": "Everyone",
}
# The manifest names the backend behind each figure: the two learners by name, the sure things
# ranking as a rule (contact the likeliest converters), and everyone as no model at all.
MANIFEST_MODEL = {
    "t_learner": "t_learner",
    "x_learner": "x_learner",
    "sure_things": "rules",
    "everyone": "none",
}
QUADRANT_LABELS = {
    "persuadable": "Persuadables",
    "sure_thing": "Sure things",
    "lost_cause": "Lost causes",
    "sleeping_dog": "Sleeping dogs",
}

SIM_REVENUE_PER_CONVERSION = 55.0
"""Revenue a simulated conversion brings, in dollars. The simulator records conversions, not
spend, so the policy value needs a stated price; the brand's contribution margin turns it into
profit."""

CRITEO_TRAIN_ROWS = 2_000_000
"""Training customers the Criteo learners see. The training split holds about 8.4 million rows,
more than 200 small trees need to converge; the test split is scored whole."""

CRITEO_BUDGET_SECONDS = 15 * 60
CRITEO_COLUMNS = ["row_id", *criteo.FEATURES, "treatment", "visit"]

Note = Callable[[str], None]


def run(paths: Paths, as_of: str, seed: int) -> Manifest:
    out = paths.results / "targeting"
    out.mkdir(parents=True, exist_ok=True)
    paths.logs.mkdir(parents=True, exist_ok=True)
    log = paths.logs / "targeting.log"

    def note(message: str) -> None:
        with log.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%H:%M:%S')} {message}\n")

    manifest = Manifest(as_of=as_of, seed=seed)
    _settings(manifest)
    _hillstrom(paths, out, manifest, seed, note)
    _simulator(paths, out, manifest, seed, note)
    _criteo(paths, out, manifest, seed, note)
    manifest.save(paths.results / "manifests" / "targeting.json")
    return manifest


# Hillstrom


def _hillstrom(paths: Paths, out: Path, manifest: Manifest, seed: int, note: Note) -> None:
    frame = hillstrom.load(paths.external / source("hillstrom").filename)
    mens = frame.filter(pl.col("arm") != "womens").with_columns(
        (pl.col("arm") == "mens").cast(pl.Int8).alias("treated")
    )
    note(f"hillstrom: {mens.height} customers in the men's email and control arms")
    result = run_protocol(
        mens,
        hillstrom.FEATURES,
        "treated",
        "conversion",
        "spend",
        "customer_id",
        seed,
        LEARNERS,
        POLICY.email_cost_per_contact,
        POLICY.email_margin_on_spend,
        progress=lambda m: note(f"hillstrom: {m}"),
    )
    _write(out, "hillstrom", result, {"treatment": "men's email against no email; women's arm dropped"})

    rows = result.rows
    population_test = (
        f"Hillstrom men's email against no email, test split of {rows.test:,} customers "
        f"(models fit on {rows.train:,}, shares chosen on {rows.validation:,})"
    )
    population_validation = f"Hillstrom men's email against no email, validation split of {rows.validation:,}"
    _policies(manifest, "hillstrom", result, "real:hillstrom", population_test, population_validation, "usd0")
    w = Scribe(manifest, source="real:hillstrom", population=population_test, origin=ORIGIN)
    w.put("targeting.hillstrom.rows_train", rows.train, "int")
    w.put("targeting.hillstrom.rows_validation", rows.validation, "int")
    w.put("targeting.hillstrom.rows_test", rows.test, "int")
    w.put("targeting.hillstrom.treatment", "the men's merchandise email against no email", "text")
    w.put("targeting.hillstrom.outcome", "conversion in the two weeks after the email", "text")
    w.put("targeting.hillstrom.cost_per_contact", POLICY.email_cost_per_contact, "usd2")
    w.put("targeting.hillstrom.margin_on_spend", POLICY.email_margin_on_spend, "pct0")
    w.put("targeting.hillstrom.value_unit", "incremental profit per thousand customers on the list", "text")


# The simulator


def _simulator(paths: Paths, out: Path, manifest: Manifest, seed: int, note: Note) -> None:
    truth = pl.read_parquet(paths.sim / "customers_truth.parquet")
    view = randomized_view(truth).with_columns(
        (pl.col("converted") * SIM_REVENUE_PER_CONVERSION).alias("revenue")
    )
    note(f"sim: {view.height} customers in the randomized view")
    result = run_protocol(
        view,
        SIM_FEATURES,
        "treated",
        "converted",
        "revenue",
        "customer_id",
        seed,
        LEARNERS,
        POLICY.email_cost_per_contact,
        POLICY.contribution_margin,
        progress=lambda m: note(f"sim: {m}"),
    )

    # The truth is joined only now, after every choice was made on what an analyst could see.
    test = result.test_scores.join(
        truth.select("customer_id", "tau_true", "y0", "y1", "quadrant"), on="customer_id", how="left"
    ).sort("customer_id")
    if test["quadrant"].null_count():
        raise ValueError("a test customer is missing from the truth table")
    tau = test["tau_true"].to_numpy()
    y0, y1 = test["y0"].to_numpy(), test["y1"].to_numpy()
    quadrant = test["quadrant"].to_numpy()
    errors = {name: pehe(test[name].to_numpy(), tau) for name in result.settings.learners}

    contacted: dict[str, dict[str, float]] = {}
    regret: dict[str, int] = {}
    rows_out: list[dict[str, Any]] = []
    for p in result.policies:
        mask = contact_mask(test[p.policy].to_numpy(), p.chosen_share)
        contacted[p.policy] = quadrant_shares_contacted(mask, quadrant)
        regret[p.policy] = oracle_regret(mask, y0, y1)
        rows_out += _quadrant_rows(p.policy, p.chosen_share, mask, quadrant)
    # The oracle contacts exactly the persuadables: every conversion the email can cause, and no
    # contact spent on a customer whose outcome it cannot change or would reverse.
    oracle = (y0 == 0) & (y1 == 1)
    oracle_share = float(oracle.mean())
    oracle_contacted = quadrant_shares_contacted(oracle, quadrant)
    rows_out += _quadrant_rows("oracle", oracle_share, oracle, quadrant)
    pl.DataFrame(rows_out).write_parquet(out / "sim_quadrants.parquet")
    counts = {q: int((quadrant == q).sum()) for q in QUADRANTS}
    _write(
        out,
        "sim",
        result,
        {
            "revenue_per_conversion": SIM_REVENUE_PER_CONVERSION,
            "pehe": errors,
            "quadrant_shares_contacted": contacted,
            "oracle_regret": regret,
            "oracle_conversions": int(oracle.sum()),
            "test_quadrant_counts": counts,
        },
    )

    rows = result.rows
    population_test = (
        f"simulated customers, randomized email, test split of {rows.test:,} "
        f"(models fit on {rows.train:,}, shares chosen on {rows.validation:,})"
    )
    population_validation = f"simulated customers, randomized email, validation split of {rows.validation:,}"
    _policies(manifest, "sim", result, "simulated", population_test, population_validation, "usd0")
    w = Scribe(manifest, source="simulated", population=population_test, origin=ORIGIN)
    w.put("targeting.sim.rows_train", rows.train, "int")
    w.put("targeting.sim.rows_validation", rows.validation, "int")
    w.put("targeting.sim.rows_test", rows.test, "int")
    w.put("targeting.sim.revenue_per_conversion", SIM_REVENUE_PER_CONVERSION, "usd0")
    w.put("targeting.sim.margin", POLICY.contribution_margin, "pct0")
    w.put("targeting.sim.cost_per_contact", POLICY.email_cost_per_contact, "usd2")
    w.put("targeting.sim.oracle_conversions", int(oracle.sum()), "int")
    w.put("targeting.sim.value_unit", "incremental profit per thousand customers on the list", "text")
    for q in QUADRANTS:
        w.put(f"targeting.sim.test_quadrant_share.{q}", counts[q] / rows.test, "pct1")
    for name, error in errors.items():
        Scribe(
            manifest,
            source="simulated",
            model=MANIFEST_MODEL[name],
            population=population_test,
            origin=ORIGIN,
        ).put(f"targeting.sim.pehe.{name}", error, "float3")
    for p in result.policies:
        s = Scribe(
            manifest,
            source="simulated",
            model=MANIFEST_MODEL[p.policy],
            population=f"{population_test}, contacted at the share chosen on validation",
            origin=ORIGIN,
        )
        for q in QUADRANTS:
            s.put(f"targeting.sim.quadrant.{p.policy}.{q}", contacted[p.policy][q], "pct1")
        s.put(f"targeting.sim.regret.{p.policy}", regret[p.policy], "int")
    table_rows: list[list[Scalar]] = [
        [
            POLICY_LABELS[p.policy],
            p.chosen_share,
            *[contacted[p.policy][q] for q in QUADRANTS],
            regret[p.policy],
        ]
        for p in result.policies
    ]
    table_rows.append(
        [
            "Oracle (known truth)",
            oracle_share,
            *[oracle_contacted[q] for q in QUADRANTS],
            oracle_regret(oracle, y0, y1),
        ]
    )
    Scribe(
        manifest,
        source="simulated",
        population=f"{population_test}; the oracle contacts exactly the persuadables",
        origin=ORIGIN,
    ).table(
        "targeting.sim.quadrants",
        ["Policy", "Share contacted", *[QUADRANT_LABELS[q] for q in QUADRANTS], "Regret (conversions)"],
        ["text", "pct1", "pct1", "pct1", "pct1", "pct1", "int"],
        table_rows,
    )


def _quadrant_rows(policy: str, share: float, mask: np.ndarray, labels: np.ndarray) -> list[dict[str, Any]]:
    rows = []
    for q in QUADRANTS:
        members = labels == q
        rows.append(
            {
                "policy": policy,
                "share_contacted": share,
                "quadrant": q,
                "customers": int(members.sum()),
                "contacted": int(mask[members].sum()),
                "share_of_quadrant_contacted": float(mask[members].mean()) if members.any() else None,
            }
        )
    return rows


# Criteo


def _criteo(paths: Paths, out: Path, manifest: Manifest, seed: int, note: Note) -> None:
    start = time.perf_counter()
    cache = paths.external / "criteo.parquet"
    # The cached parquet holds the features as 32 bit floats; without it, the raw file is read
    # once and cached, which is the slow path criteo.load exists for.
    lazy = (
        pl.scan_parquet(cache)
        if cache.exists()
        else criteo.load(paths.external / source("criteo").filename, cache)
    )
    lazy = lazy.select(CRITEO_COLUMNS).with_columns(pl.col(criteo.FEATURES).cast(pl.Float32))
    rows_total = int(lazy.select(pl.len()).collect().item())
    note(f"criteo: {rows_total} rows, every one of them split and the test split scored whole")
    result = run_protocol(
        lazy,
        criteo.FEATURES,
        "treatment",
        "visit",
        None,
        "row_id",
        seed,
        LEARNERS,
        cost_per_contact=0.0,
        margin_on_spend=1.0,
        train_rows=CRITEO_TRAIN_ROWS,
        progress=lambda m: note(f"criteo: {m}"),
    )
    rows = result.rows
    if rows.train + rows.validation + rows.test != rows_total:
        raise ValueError("the Criteo splits do not add up to every row")
    # The clock covers reading, splitting, fitting, scoring and the bootstrap; writing the three
    # files that follow takes well under a second.
    seconds = time.perf_counter() - start
    note(f"criteo: {seconds:.0f} seconds against a budget of {CRITEO_BUDGET_SECONDS}")
    _write(
        out,
        "criteo",
        result,
        {
            "rows_total": rows_total,
            "value_unit": "incremental visits per thousand users, no cost assumed",
            "seconds": round(seconds, 1),
            "budget_seconds": CRITEO_BUDGET_SECONDS,
        },
    )

    population_test = (
        f"Criteo v2.1, every row: test split of {rows.test:,} users "
        f"(models fit on a seeded {rows.train_used:,} of {rows.train:,} training rows, "
        f"shares chosen on {rows.validation:,})"
    )
    population_validation = f"Criteo v2.1, validation split of {rows.validation:,} users"
    _policies(manifest, "criteo", result, "real:criteo", population_test, population_validation, "float1")
    w = Scribe(manifest, source="real:criteo", population=population_test, origin=ORIGIN)
    w.put("targeting.criteo.rows_total", rows_total, "int")
    w.put("targeting.criteo.rows_train", rows.train, "int")
    w.put("targeting.criteo.rows_train_used", rows.train_used, "int")
    w.put("targeting.criteo.rows_validation", rows.validation, "int")
    w.put("targeting.criteo.rows_test", rows.test, "int")
    w.put("targeting.criteo.seconds", round(seconds), "int")
    w.put("targeting.criteo.budget_seconds", CRITEO_BUDGET_SECONDS, "int")
    w.put("targeting.criteo.learners", "T learner and X learner, both fit", "text")
    w.put("targeting.criteo.outcome", "visit (conversion is too rare to rank on)", "text")
    w.put(
        "targeting.criteo.value_unit",
        "incremental visits per thousand users on the list; Criteo publishes no value per visit "
        "and no cost per impression, so no cost is assumed",
        "text",
    )


# Shared writers


def _write(out: Path, dataset: str, result: ProtocolResult, extra: dict[str, Any]) -> None:
    result.qini.write_parquet(out / f"{dataset}_qini.parquet")
    result.policy_value.write_parquet(out / f"{dataset}_policy_value.parquet")
    payload = {"dataset": dataset, **result.summary(), **extra}
    (out / f"{dataset}_summary.json").write_text(
        json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


def _policies(
    manifest: Manifest,
    dataset: str,
    result: ProtocolResult,
    data_source: str,
    population_test: str,
    population_validation: str,
    value_fmt: str,
) -> None:
    """The per policy keys, the policies table and the paired differences for one dataset.

    Every figure but the chosen share (and the value it had on validation) is from the test
    split; the provenance says which split each one was read on.
    """
    for p in result.policies:
        model = MANIFEST_MODEL[p.policy]
        key = f"targeting.{dataset}.{p.policy}"
        on_test = Scribe(manifest, source=data_source, model=model, population=population_test, origin=ORIGIN)
        on_test.put(f"{key}.qini", p.qini.estimate, "float3")
        on_test.put(f"{key}.qini_lower", p.qini.lower, "float3")
        on_test.put(f"{key}.qini_upper", p.qini.upper, "float3")
        on_test.put(f"{key}.top_decile_uplift", p.top_decile_uplift, "pct2")
        on_test.put(f"{key}.policy_value_test", p.value_test.profit_per_thousand, value_fmt)
        on_test.put(
            f"{key}.policy_value_test_per_thousand_contacted",
            p.value_test.profit_per_thousand_contacted,
            value_fmt,
        )
        on_validation = Scribe(
            manifest, source=data_source, model=model, population=population_validation, origin=ORIGIN
        )
        on_validation.put(f"{key}.chosen_share", p.chosen_share, "pct1")
        on_validation.put(f"{key}.policy_value_validation", p.value_validation.profit_per_thousand, value_fmt)
        on_validation.put(f"{key}.interior", "interior" if p.interior.interior else "degenerate", "text")
        on_validation.put(f"{key}.interior_reason", p.interior.reason, "text")

    both = Scribe(
        manifest,
        source=data_source,
        population=f"{population_test}; T and X learners, the sure things rule and everyone",
        origin=ORIGIN,
    )
    both.table(
        f"targeting.{dataset}.policies",
        [
            "Policy",
            "Qini coefficient",
            "Lower",
            "Upper",
            "Chosen share",
            "Value on validation",
            "Value on test",
        ],
        ["text", "float3", "float3", "float3", "pct1", value_fmt, value_fmt],
        [
            [
                POLICY_LABELS[p.policy],
                p.qini.estimate,
                p.qini.lower,
                p.qini.upper,
                p.chosen_share,
                p.value_validation.profit_per_thousand,
                p.value_test.profit_per_thousand,
            ]
            for p in result.policies
        ],
    )
    pairs = [d for d in result.differences if "everyone" not in (d.first, d.second)]
    both.table(
        f"targeting.{dataset}.qini_differences",
        ["Comparison", "Difference", "Lower", "Upper"],
        ["text", "float3", "float3", "float3"],
        [
            [
                f"{POLICY_LABELS[d.first]} minus {POLICY_LABELS[d.second]}",
                d.interval.estimate,
                d.interval.lower,
                d.interval.upper,
            ]
            for d in pairs
        ],
    )


def _settings(manifest: Manifest) -> None:
    params = LearnerParams()
    w = Scribe(manifest, source="static", population="the targeting protocol settings", origin=ORIGIN)
    w.put("targeting.learner.n_estimators", params.n_estimators, "int")
    w.put("targeting.learner.learning_rate", params.learning_rate, "float2")
    w.put("targeting.learner.num_leaves", params.num_leaves, "int")
    w.put("targeting.learner.min_child_samples", params.min_child_samples, "int")
    for name, share in zip(SPLIT_NAMES, SPLIT_SHARES, strict=True):
        w.put(f"targeting.split.{name}", share, "pct0")
    w.put("targeting.share_grid.first", SHARE_GRID[0], "pct0")
    w.put("targeting.share_grid.step", SHARE_GRID[1] - SHARE_GRID[0], "pct0")
    w.put("targeting.share_grid.last", SHARE_GRID[-1], "pct0")
    w.put("targeting.bootstrap_replicates", POLICY.bootstrap_replicates, "int")
    w.put("targeting.level", POLICY.interval_level, "pct0")
