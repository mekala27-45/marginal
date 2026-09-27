"""The sample ratio mismatch gate, ported from readout.

No result is shown while the observed assignment counts are unlikely under the planned
ratio. The gate refuses to pass on an empty assignment, because a test that ran on nobody
has nothing to say.
"""

from __future__ import annotations

from collections.abc import Mapping

from marginal_core.config import POLICY
from marginal_core.model import StrictModel
from scipy.stats import chi2


class SRMResult(StrictModel):
    observed: dict[str, int]
    expected: dict[str, float]
    statistic: float
    p_value: float
    alpha: float
    passed: bool


def srm_gate(
    observed: Mapping[str, int], planned_shares: Mapping[str, float], alpha: float = POLICY.srm_alpha
) -> SRMResult:
    total = sum(observed.values())
    if total <= 0:
        raise ValueError("the SRM gate refuses to pass on an empty assignment")
    if set(observed) != set(planned_shares):
        raise ValueError("observed arms and planned arms differ")
    share_total = sum(planned_shares.values())
    if abs(share_total - 1.0) > 1e-9:
        raise ValueError("planned shares must sum to one")
    expected = {arm: total * share for arm, share in planned_shares.items()}
    statistic = sum((observed[arm] - expected[arm]) ** 2 / expected[arm] for arm in observed)
    p_value = float(chi2.sf(statistic, df=len(observed) - 1))
    return SRMResult(
        observed=dict(observed),
        expected=expected,
        statistic=float(statistic),
        p_value=p_value,
        alpha=alpha,
        passed=p_value >= alpha,
    )
