"""Two marketing mix model backends on one interface: own and bayes."""

from marginal_mmm.interface import (
    ChannelReturn,
    CurveParams,
    LiftResult,
    MMMSpec,
    Model,
    ModelExport,
    calibrate,
    contributions,
    design_columns,
    export_model,
    fit,
    intervals,
    marginal_return,
    response_curve,
)
from marginal_mmm.transforms import geometric_adstock, half_life, hill, hill_slope

__all__ = [
    "ChannelReturn",
    "CurveParams",
    "ModelExport",
    "export_model",
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
