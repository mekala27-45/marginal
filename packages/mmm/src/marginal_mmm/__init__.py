"""Two marketing mix model backends on one interface: own and bayes."""

from marginal_mmm.interface import (
    ChannelReturn,
    LiftResult,
    MMMSpec,
    Model,
    calibrate,
    contributions,
    design_columns,
    fit,
    intervals,
    marginal_return,
    response_curve,
)
from marginal_mmm.transforms import geometric_adstock, half_life, hill, hill_slope

__all__ = [
    "ChannelReturn",
    "LiftResult",
    "MMMSpec",
    "Model",
    "calibrate",
    "contributions",
    "design_columns",
    "fit",
    "geometric_adstock",
    "half_life",
    "hill",
    "hill_slope",
    "intervals",
    "marginal_return",
    "response_curve",
]
