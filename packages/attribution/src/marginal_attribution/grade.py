"""Every rule's share of credit per channel beside the true incremental share and the mix
model's share, and how far each rule is from the truth.

The truth is the summed incremental credit of every touch (the conversion probability with the
touch minus the probability without it), as a share by channel. The mix model's answer is its
incremental revenue at current spend by channel, as a share; it measures a different brand
panel from the same simulator, so it is a third answer, not a second truth. The grade per rule
is the mean absolute share error in points, the rank agreement with the truth, and the channel
each rule over credits most.
"""

from __future__ import annotations

import numpy as np
import polars as pl
from marginal_core.config import CHANNELS
from marginal_core.model import StrictModel
from marginal_evaluation import spearman
from marginal_mmm import ModelExport
from marginal_sim.paths import true_incremental_share

from marginal_attribution.rules import RULES, converting_touches, credit_by_channel
from marginal_attribution.shapley import shapley


class RuleGrade(StrictModel):
    rule: str
    mean_abs_error_points: float
    max_abs_error_points: float
    rank_agreement: float
    over_credits_most: str
    over_credit_points: float
    over_credit_ratio: float


def model_share(model: ModelExport) -> pl.DataFrame:
    """The mix model's share of incremental revenue at current spend, by channel."""
    revenue = {c.channel: float(c.response(c.weekly_spend_current)[()]) for c in model.channels}
    total = sum(revenue.values())
    return pl.DataFrame(
        {
            "channel": list(CHANNELS),
            "share_model": [revenue.get(c, 0.0) / total if total > 0 else 0.0 for c in CHANNELS],
        }
    )


def credit_table(touches: pl.DataFrame, users: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """One row per channel with the credit and the share under every rule, and the Shapley
    coalition table beside it."""
    frame = converting_touches(touches, users)
    conversions = float(users["converted"].sum())
    out = pl.DataFrame({"channel": list(CHANNELS)})
    for rule in RULES:
        if rule == "shapley":
            credit, coalitions = shapley(touches, users)
        else:
            credit = credit_by_channel(frame, rule)
        out = out.join(credit.rename({"credit": f"credit_{rule}"}), on="channel", how="left")
        out = out.with_columns((pl.col(f"credit_{rule}") / conversions).alias(f"share_{rule}"))
    truth = true_incremental_share(touches).select(
        "channel", pl.col("share_true"), pl.col("credit_true").alias("credit_true_expected")
    )
    out = out.join(truth, on="channel", how="left")
    return out, coalitions


def comparison(
    touches: pl.DataFrame, users: pl.DataFrame, model: ModelExport
) -> tuple[pl.DataFrame, pl.DataFrame]:
    table, coalitions = credit_table(touches, users)
    return table.join(model_share(model), on="channel", how="left"), coalitions


def grade(table: pl.DataFrame) -> list[RuleGrade]:
    truth = table["share_true"].to_numpy()
    grades = []
    for rule in RULES:
        share = table[f"share_{rule}"].to_numpy()
        gap = share - truth
        worst = int(np.argmax(gap))
        grades.append(
            RuleGrade(
                rule=rule,
                mean_abs_error_points=float(np.mean(np.abs(gap))) * 100.0,
                max_abs_error_points=float(np.max(np.abs(gap))) * 100.0,
                rank_agreement=spearman(share, truth),
                over_credits_most=str(table["channel"][worst]),
                over_credit_points=float(gap[worst]) * 100.0,
                over_credit_ratio=float(share[worst] / truth[worst]) if truth[worst] > 0 else float("nan"),
            )
        )
    return grades


def over_credit(table: pl.DataFrame, rule: str, channel: str) -> tuple[float, float, float]:
    """A rule's share for a channel, the true share, and the gap in points."""
    row = table.filter(pl.col("channel") == channel).row(0, named=True)
    share = float(row[f"share_{rule}"])
    truth = float(row["share_true"])
    return share, truth, (share - truth) * 100.0
