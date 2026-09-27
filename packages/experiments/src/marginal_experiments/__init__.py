"""Geo lift design with power by simulation, pre-registration, the SRM gate, difference in
differences, synthetic control with placebo inference, and the email experiment."""

from marginal_experiments.email import EmailAnalysis, analyse, email_design
from marginal_experiments.geo_lift import (
    DiDResult,
    PowerCell,
    SyntheticControlResult,
    design_test,
    difference_in_differences,
    intervention_for,
    power_curve,
    stratified_assignment,
    synthetic_control,
    true_lift,
)
from marginal_experiments.registration import EmailDesign, GeoLiftDesign
from marginal_experiments.srm import SRMResult, srm_gate

__all__ = [
    "DiDResult",
    "EmailAnalysis",
    "EmailDesign",
    "GeoLiftDesign",
    "PowerCell",
    "SRMResult",
    "SyntheticControlResult",
    "analyse",
    "design_test",
    "difference_in_differences",
    "email_design",
    "intervention_for",
    "power_curve",
    "srm_gate",
    "stratified_assignment",
    "synthetic_control",
    "true_lift",
]
