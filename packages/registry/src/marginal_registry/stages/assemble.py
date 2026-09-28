"""Stage: merge every stage's manifest into results/manifest.json.

Stages write their own manifests under results/manifests so a rerun of one stage never
touches another's figures. This stage merges them in a fixed order, adds the policy
constants and the palette validator's summary as static values, and writes the one file
every document renders from.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from marginal_core.config import CHANNEL_LABELS, CHANNELS, POLICY
from marginal_core.manifest import Manifest, Scalar, Scribe
from marginal_core.paths import Paths

ORDER = (
    "data",
    "simulate",
    "recovery_own",
    "recovery_bayes",
    "experiments",
    "calibrate",
    "clv",
    "budget",
    "targeting",
    "attribution",
)
"""The stage order the pipeline runs in. Lifetime value runs before the budget because the
optimizer reads the acquisition cost allowance it writes; the Makefile's pipeline target and
scripts/reset_and_rederive.py follow this tuple, and a test holds them to it."""


def run(paths: Paths, as_of: str, seed: int) -> Manifest:
    merged = Manifest(as_of=as_of, seed=seed)
    folder = paths.results / "manifests"
    present: list[str] = []
    for name in ORDER:
        path = folder / f"{name}.json"
        if path.exists():
            merged.merge(Manifest.load(path))
            present.append(name)
    _policy(merged)
    _palette(merged, paths.root)
    _crosscheck(merged)
    _deploy(merged, paths.results / "deploy" / "verification.json")
    merged.put(
        "build.stages_present",
        ", ".join(present) if present else "none",
        "text",
        source="static",
        population="stage manifests found",
        origin="marginal_registry.stages.assemble",
    )
    merged.save(paths.manifest)
    return merged


def _policy(manifest: Manifest) -> None:
    w = Scribe(
        manifest, source="static", population="the measurement policy", origin="marginal_core.config.POLICY"
    )
    fmts = {
        "contribution_margin": "pct0",
        "email_cost_per_contact": "usd2",
        "email_margin_on_spend": "pct0",
        "clv_horizon_months": "int",
        "clv_discount_rate_annual": "pct0",
        "clv_payback_share": "pct0",
        "lift_test_length_weeks": "int",
        "lift_test_pre_period_weeks": "int",
        "lift_test_channel": "text",
        "lift_test_spend_change": "spct1",
        "srm_alpha": "float3",
        "placebo_permutations": "int",
        "bootstrap_replicates": "int",
        "bootstrap_block_weeks": "int",
        "rolling_origins": "int",
        "interval_level": "pct0",
        "recovery_seeds_own": "int",
        "recovery_seeds_bayes": "int",
        "budget_max_change_share": "pct0",
        "budget_floor_share": "pct0",
        "budget_ceiling_share": "pct0",
        "optimizer_starts": "int",
        "attribution_half_life_days": "float1",
        "attribution_position_first": "pct0",
        "attribution_position_last": "pct0",
    }
    for field, fmt in fmts.items():
        value = getattr(POLICY, field)
        if field == "lift_test_channel":
            value = CHANNEL_LABELS[str(value)]
        w.put(f"policy.{field}", value, fmt)
    w.put("policy.channel_count", len(CHANNELS), "int")
    w.put("policy.contribution_margin_breakeven", 1.0 / POLICY.contribution_margin, "float2")
    w.put("policy.channel_order", ", ".join(CHANNEL_LABELS[c] for c in CHANNELS), "text")


def _palette(manifest: Manifest, root: Path) -> None:
    script = root / "scripts" / "validate_palette.js"
    config = root / "web" / "src" / "theme" / "palette.json"
    w = Scribe(
        manifest,
        source="static",
        population="web/src/theme/palette.json",
        origin="scripts/validate_palette.js",
    )
    if not script.exists() or not config.exists():
        w.put("palette.validated", "not run", "text")
        return
    proc = subprocess.run(
        ["node", str(script), "--config", str(config)], capture_output=True, text=True, check=False
    )
    try:
        summary = json.loads(proc.stdout)
    except json.JSONDecodeError:
        w.put("palette.validated", "validator did not return a summary", "text")
        return
    w.put("palette.failures", int(summary["failures"]), "int")
    w.put("palette.validated", "green" if summary["failures"] == 0 else "failing", "text")
    for mode in ("light", "dark"):
        m = summary["modes"][mode]
        w.put(f"palette.{mode}.worst_adjacent_cvd", m["worstAdjacentCvd"], "float1")
        w.put(f"palette.{mode}.worst_adjacent_normal", m["worstAdjacentNormal"], "float1")
        w.put(f"palette.{mode}.worst_slot_contrast", m["worstSlotContrast"], "float2")
        w.put(f"palette.{mode}.worst_card_contrast", m["worstCardContrast"], "float2")
        w.put(f"palette.{mode}.first_three_all_pairs_cvd", m["firstThreeAllPairsCvd"], "float1")


def _crosscheck(manifest: Manifest) -> None:
    """Both backends on the demonstration brand in one table, the truth in the last column, and a
    flag where their intervals do not overlap."""
    if (
        "mmm.own.roas.paid_search" not in manifest.values
        or "mmm.bayes.roas.paid_search" not in manifest.values
    ):
        return
    rows: list[list[Scalar]] = []
    disagreements: list[str] = []
    for channel in CHANNELS:
        own = float(manifest.raw(f"mmm.own.roas.{channel}"))  # type: ignore[arg-type]
        own_lower = float(manifest.raw(f"mmm.own.roas_lower.{channel}"))  # type: ignore[arg-type]
        own_upper = float(manifest.raw(f"mmm.own.roas_upper.{channel}"))  # type: ignore[arg-type]
        bayes = float(manifest.raw(f"mmm.bayes.roas.{channel}"))  # type: ignore[arg-type]
        bayes_lower = float(manifest.raw(f"mmm.bayes.roas_lower.{channel}"))  # type: ignore[arg-type]
        bayes_upper = float(manifest.raw(f"mmm.bayes.roas_upper.{channel}"))  # type: ignore[arg-type]
        truth = float(manifest.raw(f"sim.truth.roas.{channel}"))  # type: ignore[arg-type]
        disagree = own_lower > bayes_upper or bayes_lower > own_upper
        if disagree:
            disagreements.append(CHANNEL_LABELS[channel])
        rows.append(
            [
                CHANNEL_LABELS[channel],
                own,
                own_lower,
                own_upper,
                bayes,
                bayes_lower,
                bayes_upper,
                truth,
                "yes" if disagree else "no",
            ]
        )
    w = Scribe(
        manifest,
        source="simulated",
        model="both",
        population="demonstration brand",
        origin="marginal_registry.stages.assemble",
    )
    w.table(
        "mmm.crosscheck",
        [
            "Channel",
            "own",
            "own lower",
            "own upper",
            "bayes",
            "bayes lower",
            "bayes upper",
            "Truth (simulated)",
            "Disagree",
        ],
        ["text", "float2", "float2", "float2", "float2", "float2", "float2", "float2", "text"],
        rows,
    )
    w.put("mmm.crosscheck.disagreements", ", ".join(disagreements) if disagreements else "none", "text")
    w.put("mmm.crosscheck.disagreement_count", len(disagreements), "int")


def _deploy(manifest: Manifest, path: Path) -> None:
    """The separate client verification of the live API, recorded as it was seen."""
    w = Scribe(
        manifest,
        source="recorded",
        population="the live API, checked from a separate client",
        origin="deploy/verify.ps1",
    )
    if not path.exists():
        w.put("deploy.status", "API not deployed", "text")
        return
    seen = json.loads(path.read_text(encoding="utf-8"))
    w.put("deploy.status", "deployed" if seen.get("passed") else "verification failed", "text")
    w.put("deploy.base_url", str(seen["base_url"]), "text")
    w.put("deploy.client", str(seen["client"]), "text")
    w.put("deploy.checked_at", str(seen["checked_at"]), "text")
    w.put("deploy.health_status", str(seen["health"]["status"]), "text")
    w.put("deploy.health_database", str(seen["health"]["database"]), "text")
    w.put("deploy.model_version", str(seen["health"]["model_version"]), "text")
    w.put("deploy.experiment_id", str(seen["experiment_id"]), "text")
    w.put("deploy.plan_hash", str(seen["plan_hash"]), "text")
    w.put("deploy.result_read_back", float(seen["result_read_back"]), "usd0")
    w.put("deploy.plan_id", str(seen["plan_id"]), "text")
    w.put("deploy.plan_expected_profit", float(seen["plan_expected_profit"]), "usd0")
    w.put("deploy.audit_entries", int(seen["audit_entries"]), "int")
    w.put("deploy.audit_before_response", "yes" if seen["audit_before_response"] else "no", "text")
    w.put("deploy.statement_present", "yes" if seen["statement_present"] else "no", "text")
    w.put("deploy.passed", "yes" if seen["passed"] else "no", "text")
