"""Pre-registration: a design is hashed before its data exists, and a result can only be
posted against that hash. Changing anything in the design changes the hash."""

from __future__ import annotations

from marginal_core.hashing import design_hash
from marginal_core.model import StrictModel


class GeoLiftDesign(StrictModel):
    name: str
    channel: str
    spend_change: float
    """-1.0 is a holdout (spend to zero in the treated geos); 0.5 is a fifty percent increase."""
    assignment: str
    """'stratified' on pre period sales, or 'synthetic' by synthetic control weights."""
    treated_geos: tuple[int, ...]
    control_geos: tuple[int, ...]
    pre_period_weeks: int
    start_week: int
    end_week: int
    primary_outcome: str = "sales"
    analysis: str = "difference in differences with geo and week fixed effects on log sales; synthetic control with placebo inference"
    placebo_permutations: int
    interval_level: float
    power_at_true_effect: float | None = None
    """Filled by the power study before registration; part of the hash."""

    @property
    def window_weeks(self) -> int:
        return self.end_week - self.start_week + 1

    @property
    def plan_hash(self) -> str:
        return design_hash(self.model_dump(mode="json"))


class EmailDesign(StrictModel):
    name: str
    arms: tuple[str, ...]
    planned_shares: tuple[float, ...]
    primary_arm: str
    control_arm: str
    outcomes: tuple[str, ...]
    outcome_window_days: int
    segments_by: str
    correction: str = "Benjamini-Hochberg across segments"
    interval_level: float

    @property
    def plan_hash(self) -> str:
        return design_hash(self.model_dump(mode="json"))


class ExperimentRecord(StrictModel):
    """What the registry stores when a design is registered: the plan and its hash, and when."""

    experiment_id: str
    name: str
    kind: str
    """geo_lift or email."""
    plan_hash: str
    design: dict[str, object]
    registered_at: str
    registered_via: str
    """'api' when the live registry answered, 'local' when it was written to the results folder."""


class ResultRecord(StrictModel):
    experiment_id: str
    plan_hash: str
    method: str
    channel: str
    incremental_revenue: float
    standard_error: float
    lower: float
    upper: float
    level: float
    geos: tuple[int, ...]
    start_week: int
    end_week: int
    posted_at: str
    truth: float | None = None
