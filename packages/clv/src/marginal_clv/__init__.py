"""BG/NBD and Gamma-Gamma written in the repository with a holdout validation and the acquisition cost allowance."""

from marginal_clv.bgnbd import BGNBD, FitRecord, customer_arrays
from marginal_clv.crosscheck import CrossCheck, ParameterComparison, cross_check
from marginal_clv.frame import holdout_frame, rfm_frame
from marginal_clv.gamma_gamma import GammaGamma, IndependenceCheck, spend_frequency_correlation
from marginal_clv.validation import calibration_plot, holdout_by_decile
from marginal_clv.value import (
    CHANNEL_SEGMENT_MIX,
    DAYS_PER_MONTH,
    SEGMENTS,
    Allowance,
    ChannelAllowance,
    Segment,
    SegmentAllowance,
    acquisition_allowance,
    check_mixes,
    customer_lifetime_value,
    monthly_discount_rate,
    revenue_per_acquisition,
    segments,
)

__all__ = [
    "BGNBD",
    "CHANNEL_SEGMENT_MIX",
    "DAYS_PER_MONTH",
    "SEGMENTS",
    "Allowance",
    "ChannelAllowance",
    "CrossCheck",
    "FitRecord",
    "GammaGamma",
    "IndependenceCheck",
    "ParameterComparison",
    "Segment",
    "SegmentAllowance",
    "acquisition_allowance",
    "calibration_plot",
    "check_mixes",
    "cross_check",
    "customer_arrays",
    "customer_lifetime_value",
    "holdout_by_decile",
    "holdout_frame",
    "monthly_discount_rate",
    "revenue_per_acquisition",
    "rfm_frame",
    "segments",
    "spend_frequency_correlation",
]
