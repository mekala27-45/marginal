"""The stated constants of the measurement policy.

Every margin, cost, horizon and threshold a figure depends on is written here
once, under a name, so docs/definitions.md can cite the field and a test can
assert that the documents quote the value the code used.
"""

from __future__ import annotations

from marginal_core.model import StrictModel

# The seven paid channels in their fixed order. The palette slots follow this order on every page.
CHANNELS: tuple[str, ...] = (
    "paid_search",
    "paid_social",
    "online_video",
    "display_retargeting",
    "email",
    "affiliate_promo",
    "direct_mail",
)

CHANNEL_LABELS: dict[str, str] = {
    "paid_search": "Paid search",
    "paid_social": "Paid social",
    "online_video": "Online video",
    "display_retargeting": "Display and retargeting",
    "email": "Email",
    "affiliate_promo": "Affiliate and promo codes",
    "direct_mail": "Direct mail",
}


class Policy(StrictModel):
    """The measurement policy. Quoted in docs/definitions.md; changed only with a DECISIONS entry."""

    contribution_margin: float = 0.42
    """Gross margin on incremental revenue, the rate that turns revenue into profit."""

    email_cost_per_contact: float = 0.12
    """Cost of one marketing email, in dollars, for the policy value curve."""

    email_margin_on_spend: float = 0.30
    """Margin on the spend a Hillstrom customer makes in the two week window."""

    clv_horizon_months: int = 12
    clv_discount_rate_annual: float = 0.10
    clv_payback_share: float = 0.70
    """Share of twelve month lifetime value at margin a channel may spend to acquire a customer."""

    lift_test_length_weeks: int = 8
    lift_test_pre_period_weeks: int = 52
    lift_test_channel: str = "display_retargeting"
    lift_test_spend_change: float = -1.0
    """A holdout: the tested channel's spend goes to zero in the treated geos."""

    srm_alpha: float = 0.001
    """No result is shown while the assignment counts fail the sample ratio test at this level."""

    placebo_permutations: int = 200
    bootstrap_replicates: int = 200
    bootstrap_block_weeks: int = 8
    rolling_origins: int = 8
    interval_level: float = 0.90

    recovery_seeds_own: int = 20
    recovery_seeds_bayes: int = 3

    budget_max_change_share: float = 0.30
    """No channel moves more than this share of last year's spend in one plan."""

    budget_floor_share: float = 0.25
    budget_ceiling_share: float = 2.00
    optimizer_starts: int = 8


POLICY = Policy()
