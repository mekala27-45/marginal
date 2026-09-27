"""Customers with a known heterogeneous treatment effect for an email.

Each customer has both potential outcomes written down: whether they would convert if
left alone (y0) and whether they would convert if emailed (y1). That is what makes the
four quadrants exact labels rather than guesses. The randomized set assigns the email by
a coin; the policy set assigns it by the "sure things" rule most retailers run, contacting
the customers most likely to convert anyway.
"""

from __future__ import annotations

import numpy as np
import polars as pl
from marginal_core.seeds import rng

from marginal_sim.spec import CustomerSpec

FEATURES = (
    "recency_days",
    "frequency",
    "monetary",
    "tenure_days",
    "category_affinity",
    "engagement",
    "region",
    "mobile_share",
)

QUADRANTS = ("persuadable", "sure_thing", "lost_cause", "sleeping_dog")


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return np.asarray(1.0 / (1.0 + np.exp(-x)))


def simulate_customers(spec: CustomerSpec) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Returns the randomized set, the policy assigned set, and the truth table."""
    n = spec.customers
    r = rng(spec.seed, "customer_features")
    recency = r.gamma(2.0, 45.0, n)
    frequency = r.poisson(2.2, n) + 1
    monetary = r.lognormal(4.2, 0.7, n)
    tenure = r.gamma(2.5, 260.0, n)
    affinity = r.beta(2.0, 3.0, n)
    engagement = r.beta(2.5, 2.5, n)
    region = r.integers(0, 4, n)
    mobile = r.beta(3.0, 2.0, n)

    # Baseline conversion: recent, frequent, engaged customers convert on their own.
    base_logit = (
        -3.1
        - 0.010 * (recency - 90.0)
        + 0.22 * np.log(frequency)
        + 0.25 * (np.log(monetary) - 4.2)
        + 1.4 * (engagement - 0.5)
        + 0.15 * (region == 2)
    )
    p0 = _sigmoid(base_logit)

    # The email's effect: strongest on lapsed, affinity matched customers with middling engagement;
    # negative on the most engaged, most recent customers, who are fatigued by another email.
    tau_logit = (
        0.55
        + 0.006 * (recency - 90.0)
        + 1.2 * (affinity - 0.4)
        - 2.4 * np.clip(engagement - 0.72, 0.0, None)
        - 0.35 * np.clip(30.0 - recency, 0.0, None) / 30.0
        - 0.10 * (region == 3)
    )
    tau = 0.12 * np.tanh(tau_logit)
    p1 = np.clip(p0 + tau, 0.001, 0.999)

    o = rng(spec.seed, "potential_outcomes")
    u0 = o.random(n)
    u1 = o.random(n)
    y0 = (u0 < p0).astype(np.int8)
    # A positive effect turns a share tau / (1 - p0) of the non converters into converters;
    # a negative one turns a share |tau| / p0 of the converters away. Either way P(y1) = p1, and
    # everyone else keeps the outcome they had, so the quadrants are exact.
    gain = (y0 == 0) & (tau > 0) & (u1 < tau / np.maximum(1.0 - p0, 1e-9))
    loss = (y0 == 1) & (tau < 0) & (u1 < -tau / np.maximum(p0, 1e-9))
    y1 = np.where(gain, 1, np.where(loss, 0, y0)).astype(np.int8)
    quadrant = np.select(
        [(y0 == 0) & (y1 == 1), (y0 == 1) & (y1 == 1), (y0 == 0) & (y1 == 0), (y0 == 1) & (y1 == 0)],
        [np.full(n, q, dtype=object) for q in QUADRANTS],
        default="",
    ).astype(str)

    a = rng(spec.seed, "random_assignment")
    treated_random = (a.random(n) < spec.treated_share_random).astype(np.int8)
    # The stated policy: contact the top share by baseline conversion probability, the "sure things".
    cutoff = np.quantile(p0, 1.0 - spec.policy_contact_share)
    treated_policy = (p0 >= cutoff).astype(np.int8)

    truth = pl.DataFrame(
        {
            "customer_id": np.arange(n, dtype=np.int32),
            "recency_days": recency.astype(np.float32),
            "frequency": frequency.astype(np.int16),
            "monetary": monetary.astype(np.float32),
            "tenure_days": tenure.astype(np.float32),
            "category_affinity": affinity.astype(np.float32),
            "engagement": engagement.astype(np.float32),
            "region": region.astype(np.int8),
            "mobile_share": mobile.astype(np.float32),
            "p0_true": p0.astype(np.float32),
            "p1_true": p1.astype(np.float32),
            "tau_true": (p1 - p0).astype(np.float32),
            "y0": y0,
            "y1": y1,
            "quadrant": quadrant,
            "treated_random": treated_random,
            "treated_policy": treated_policy,
        }
    )
    return randomized_view(truth), policy_view(truth), truth


def _observed(truth: pl.DataFrame, column: str) -> pl.DataFrame:
    return truth.select(
        "customer_id",
        *FEATURES,
        pl.col(column).alias("treated"),
        pl.when(pl.col(column) == 1).then(pl.col("y1")).otherwise(pl.col("y0")).alias("converted"),
    )


def randomized_view(truth: pl.DataFrame) -> pl.DataFrame:
    """What an analyst sees of the randomized set: features, the coin, the observed outcome."""
    return _observed(truth, "treated_random")


def policy_view(truth: pl.DataFrame) -> pl.DataFrame:
    """What an analyst sees of the policy assigned set."""
    return _observed(truth, "treated_policy")


def quadrant_shares(truth: pl.DataFrame) -> dict[str, float]:
    counts = truth.group_by("quadrant").len()
    total = truth.height
    out = {q: 0.0 for q in QUADRANTS}
    for row in counts.iter_rows(named=True):
        out[str(row["quadrant"])] = row["len"] / total
    return out
