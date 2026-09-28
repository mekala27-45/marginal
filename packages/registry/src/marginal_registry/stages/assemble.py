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
from marginal_core.manifest import Manifest, Scribe
from marginal_core.paths import Paths

ORDER = (
    "data",
    "simulate",
    "recovery_own",
    "recovery_bayes",
    "experiments",
    "calibrate",
    "budget",
    "targeting",
    "clv",
    "attribution",
)


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
