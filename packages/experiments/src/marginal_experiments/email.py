"""The email experiment on Hillstrom: the one real randomized result in the build.

Three arms, randomized in thirds. The SRM gate runs on the arm counts first. Then each
email's average treatment effect against no email on visit, conversion and spend, with
normal intervals from the difference of means, the incremental revenue per email at the
stated cost, and the same effects by purchase history segment with Benjamini-Hochberg
across the segments.
"""

from __future__ import annotations

import math

import numpy as np
import polars as pl
from marginal_core.config import POLICY
from marginal_core.model import StrictModel
from marginal_evaluation import benjamini_hochberg
from scipy.stats import norm

from marginal_experiments.registration import EmailDesign
from marginal_experiments.srm import SRMResult, srm_gate

OUTCOMES = ("visit", "conversion", "spend")


class ArmEffect(StrictModel):
    arm: str
    outcome: str
    treated_mean: float
    control_mean: float
    effect: float
    standard_error: float
    lower: float
    upper: float
    p_value: float
    treated_n: int
    control_n: int


class SegmentEffect(StrictModel):
    arm: str
    outcome: str
    segment: str
    effect: float
    lower: float
    upper: float
    p_value: float
    p_adjusted: float
    significant: bool
    n: int


class EmailAnalysis(StrictModel):
    design: EmailDesign
    srm: SRMResult
    effects: list[ArmEffect]
    segments: list[SegmentEffect]
    incremental_revenue_per_email: dict[str, float]
    incremental_profit_per_email: dict[str, float]
    cost_per_email: float
    margin_on_spend: float


def email_design(level: float = POLICY.interval_level) -> EmailDesign:
    return EmailDesign(
        name="Hillstrom 2008 email experiment",
        arms=("control", "mens", "womens"),
        planned_shares=(1 / 3, 1 / 3, 1 / 3),
        primary_arm="mens",
        control_arm="control",
        outcomes=OUTCOMES,
        outcome_window_days=14,
        segments_by="history_segment",
        interval_level=level,
    )


def _effect(treated: np.ndarray, control: np.ndarray, level: float, arm: str, outcome: str) -> ArmEffect:
    if treated.size == 0 or control.size == 0:
        raise ValueError("an arm with no customers has no effect")
    diff = float(treated.mean() - control.mean())
    se = math.sqrt(treated.var(ddof=1) / treated.size + control.var(ddof=1) / control.size)
    z = float(norm.ppf(1.0 - (1.0 - level) / 2.0))
    p = 2.0 * float(norm.sf(abs(diff) / se)) if se > 0 else 1.0
    return ArmEffect(
        arm=arm,
        outcome=outcome,
        treated_mean=float(treated.mean()),
        control_mean=float(control.mean()),
        effect=diff,
        standard_error=se,
        lower=diff - z * se,
        upper=diff + z * se,
        p_value=p,
        treated_n=int(treated.size),
        control_n=int(control.size),
    )


def analyse(frame: pl.DataFrame, design: EmailDesign | None = None) -> EmailAnalysis:
    design = design or email_design()
    counts = {arm: int(frame.filter(pl.col("arm") == arm).height) for arm in design.arms}
    srm = srm_gate(counts, dict(zip(design.arms, design.planned_shares, strict=True)))
    if not srm.passed:
        raise ValueError(f"the SRM gate failed (p = {srm.p_value:.2g}); no result is shown")
    control = frame.filter(pl.col("arm") == design.control_arm)
    effects: list[ArmEffect] = []
    segments: list[SegmentEffect] = []
    revenue_per_email: dict[str, float] = {}
    profit_per_email: dict[str, float] = {}
    for arm in design.arms:
        if arm == design.control_arm:
            continue
        treated = frame.filter(pl.col("arm") == arm)
        for outcome in design.outcomes:
            effects.append(
                _effect(
                    treated[outcome].to_numpy().astype(float),
                    control[outcome].to_numpy().astype(float),
                    design.interval_level,
                    arm,
                    outcome,
                )
            )
        spend_effect = next(e for e in effects if e.arm == arm and e.outcome == "spend")
        revenue_per_email[arm] = spend_effect.effect
        profit_per_email[arm] = (
            spend_effect.effect * POLICY.email_margin_on_spend - POLICY.email_cost_per_contact
        )
        # Segments: one family per arm and outcome, corrected across the segments.
        for outcome in design.outcomes:
            family: list[SegmentEffect] = []
            for segment in sorted(frame[design.segments_by].unique().to_list()):
                t_seg = (
                    treated.filter(pl.col(design.segments_by) == segment)[outcome].to_numpy().astype(float)
                )
                c_seg = (
                    control.filter(pl.col(design.segments_by) == segment)[outcome].to_numpy().astype(float)
                )
                e = _effect(t_seg, c_seg, design.interval_level, arm, outcome)
                family.append(
                    SegmentEffect(
                        arm=arm,
                        outcome=outcome,
                        segment=str(segment),
                        effect=e.effect,
                        lower=e.lower,
                        upper=e.upper,
                        p_value=e.p_value,
                        p_adjusted=e.p_value,
                        significant=False,
                        n=e.treated_n + e.control_n,
                    )
                )
            adjusted, rejected = benjamini_hochberg([f.p_value for f in family], q=0.05)
            for item, p_adj, sig in zip(family, adjusted, rejected, strict=True):
                segments.append(item.model_copy(update={"p_adjusted": p_adj, "significant": sig}))
    return EmailAnalysis(
        design=design,
        srm=srm,
        effects=effects,
        segments=segments,
        incremental_revenue_per_email=revenue_per_email,
        incremental_profit_per_email=profit_per_email,
        cost_per_email=POLICY.email_cost_per_contact,
        margin_on_spend=POLICY.email_margin_on_spend,
    )
