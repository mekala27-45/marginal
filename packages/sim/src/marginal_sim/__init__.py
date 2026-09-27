"""The seeded market with known truth: geo panel, customers with known effects, paths with known credit."""

from marginal_sim.customers import (
    QUADRANTS,
    policy_view,
    quadrant_shares,
    randomized_view,
    simulate_customers,
)
from marginal_sim.market import (
    Market,
    TruthParams,
    adstock,
    hill,
    hill_derivative,
    marginal_return,
    national_truth_table,
    response,
    simulate_market,
    truth_params,
)
from marginal_sim.paths import simulate_paths, true_incremental_share
from marginal_sim.spec import (
    CONDITIONS,
    DEFAULT_CHANNELS,
    ChannelTruth,
    CustomerSpec,
    Intervention,
    MarketSpec,
    PathSpec,
    condition_name,
    demonstration_spec,
)

__all__ = [
    "CONDITIONS",
    "DEFAULT_CHANNELS",
    "QUADRANTS",
    "ChannelTruth",
    "CustomerSpec",
    "Intervention",
    "Market",
    "MarketSpec",
    "PathSpec",
    "TruthParams",
    "adstock",
    "condition_name",
    "demonstration_spec",
    "hill",
    "hill_derivative",
    "marginal_return",
    "national_truth_table",
    "policy_view",
    "quadrant_shares",
    "randomized_view",
    "response",
    "simulate_customers",
    "simulate_market",
    "simulate_paths",
    "true_incremental_share",
    "truth_params",
]
