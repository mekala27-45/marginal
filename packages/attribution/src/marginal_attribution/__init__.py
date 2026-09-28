"""Six credit rules and exact Shapley graded against known incremental credit."""

from marginal_attribution.grade import RuleGrade, comparison, credit_table, grade, model_share, over_credit
from marginal_attribution.rules import (
    RULE_LABELS,
    RULES,
    converting_touches,
    credit_by_channel,
    touch_weights,
)
from marginal_attribution.shapley import (
    COALITIONS,
    coalition_table,
    path_channel_sets,
    shapley,
    shapley_credit,
)

__all__ = [
    "COALITIONS",
    "RULES",
    "RULE_LABELS",
    "RuleGrade",
    "coalition_table",
    "comparison",
    "converting_touches",
    "credit_by_channel",
    "credit_table",
    "grade",
    "model_share",
    "over_credit",
    "path_channel_sets",
    "shapley",
    "shapley_credit",
    "touch_weights",
]
