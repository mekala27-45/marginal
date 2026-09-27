"""The budget optimizer: move money until the next dollar earns the same in every channel.

Maximize expected incremental profit from the fitted response curves at the contribution
margin, over a stated weekly budget, subject to per channel floors and ceilings, a maximum
change from last year's mix, and the acquisition cost allowance. SLSQP from several
starting points with the solver status recorded and the best feasible solution kept. The
optimality condition is checked and published: marginal profit is equal, within tolerance,
across every channel that is not at a bound.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import numpy as np
from marginal_core.config import CHANNELS, POLICY
from marginal_core.hashing import design_hash
from marginal_core.model import StrictModel
from marginal_core.seeds import rng
from marginal_mmm import CurveParams, ModelExport
from scipy.optimize import minimize


class Constraints(StrictModel):
    total_budget: float
    """Weekly dollars across the seven channels."""
    floor_share: float = POLICY.budget_floor_share
    ceiling_share: float = POLICY.budget_ceiling_share
    max_change_share: float = POLICY.budget_max_change_share
    margin: float = POLICY.contribution_margin
    allowance: dict[str, float] | None = None
    """Acquisition cost allowance per channel, dollars per acquired customer."""
    revenue_per_acquisition: float | None = None
    """Revenue one acquired customer brings in the window, which turns revenue into customers."""
    floors: dict[str, float] | None = None
    ceilings: dict[str, float] | None = None
    """Explicit weekly floors and ceilings override the shares of last year's spend."""

    @property
    def hash(self) -> str:
        return design_hash(self.model_dump(mode="json"))


class ChannelAllocation(StrictModel):
    channel: str
    spend: float
    last_year: float
    change: float
    expected_revenue: float
    marginal_return: float
    marginal_profit: float
    at_bound: str
    """'floor', 'ceiling', 'change limit', 'allowance' or 'interior'."""
    implied_acquisition_cost: float | None


class Plan(StrictModel):
    model_version: str
    backend: str
    spec_hash: str
    inputs_hash: str
    constraints: Constraints
    allocation: list[ChannelAllocation]
    expected_revenue: float
    expected_profit: float
    profit_lower: float
    profit_upper: float
    level: float
    solver_status: str
    starts: int
    starts_converged: int
    marginal_equalized: bool
    marginal_spread: float
    interior_channels: int
    degenerate: bool
    degenerate_reason: str | None

    @property
    def spend(self) -> dict[str, float]:
        return {a.channel: a.spend for a in self.allocation}


def _bounds(model: ModelExport, constraints: Constraints) -> list[tuple[float, float]]:
    bounds = []
    for c in model.channels:
        last = c.weekly_spend_current
        low = (
            constraints.floors[c.channel]
            if constraints.floors and c.channel in constraints.floors
            else constraints.floor_share * last
        )
        high = (
            constraints.ceilings[c.channel]
            if constraints.ceilings and c.channel in constraints.ceilings
            else constraints.ceiling_share * last
        )
        low = max(low, last * (1.0 - constraints.max_change_share), 0.0)
        high = min(high, last * (1.0 + constraints.max_change_share))
        if high < low:
            high = low
        bounds.append((low, high))
    return bounds


def _feasible_budget(bounds: list[tuple[float, float]], total: float) -> None:
    low = sum(b[0] for b in bounds)
    high = sum(b[1] for b in bounds)
    if not low - 1e-6 <= total <= high + 1e-6:
        raise ValueError(
            f"a budget of {total:,.0f} cannot satisfy floors {low:,.0f} and ceilings {high:,.0f}"
        )


def optimize(
    model: ModelExport, constraints: Constraints, *, seed: int = 0, starts: int = POLICY.optimizer_starts
) -> Plan:
    channels = [c.channel for c in model.channels]
    if tuple(channels) != CHANNELS:
        raise ValueError("the model's channels are not in the fixed order")
    bounds = _bounds(model, constraints)
    _feasible_budget(bounds, constraints.total_budget)
    margin = constraints.margin
    curves = model.channels

    def revenue(x: np.ndarray) -> float:
        return float(sum(c.response(x[j])[()] for j, c in enumerate(curves)))

    def profit(x: np.ndarray) -> float:
        return margin * revenue(x) - float(x.sum())

    def gradient(x: np.ndarray) -> np.ndarray:
        return np.array([margin * c.marginal(float(x[j])) - 1.0 for j, c in enumerate(curves)])

    ineq: list[Callable[[np.ndarray], float]] = []
    if constraints.allowance and constraints.revenue_per_acquisition:
        rpa = constraints.revenue_per_acquisition
        for j, c in enumerate(curves):
            limit = constraints.allowance.get(c.channel)
            if limit is None:
                continue
            # spend / customers <= allowance, customers = revenue / revenue per acquisition.
            ineq.append(_allowance_constraint(j, c, limit, rpa))
    cons: list[dict[str, Any]] = [
        {
            "type": "eq",
            "fun": lambda x: float(x.sum() - constraints.total_budget),
            "jac": lambda x: np.ones(len(x)),
        }
    ]
    cons.extend({"type": "ineq", "fun": fun} for fun in ineq)

    r = rng(seed, "optimizer_starts", constraints.hash)
    lows = np.array([b[0] for b in bounds])
    highs = np.array([b[1] for b in bounds])
    last = np.array([c.weekly_spend_current for c in curves])
    results = []
    for i in range(starts):
        if i == 0:
            x0 = np.clip(last * constraints.total_budget / last.sum(), lows, highs)
        else:
            weights = r.dirichlet(np.ones(len(curves)) * 4.0)
            x0 = np.clip(weights * constraints.total_budget, lows, highs)
        x0 = _project(x0, lows, highs, constraints.total_budget)
        res = minimize(
            lambda x: -profit(x),
            x0,
            jac=lambda x: -gradient(x),
            method="SLSQP",
            bounds=bounds,
            constraints=cons,
            options={"maxiter": 500, "ftol": 1e-10},
        )
        feasible = abs(res.x.sum() - constraints.total_budget) < 1e-3 * constraints.total_budget and all(
            fun(res.x) >= -1e-6 for fun in ineq
        )
        results.append((res, feasible))
    feasible_results = [(res, ok) for res, ok in results if ok]
    if not feasible_results:
        raise RuntimeError("no start produced a feasible plan")
    best, _ = min(feasible_results, key=lambda pair: pair[0].fun)
    x = np.asarray(best.x, dtype=float)

    allocation, interior, marginal_profits, degenerate_reason = _describe(
        x, curves, bounds, last, constraints
    )
    spread = float(max(marginal_profits) - min(marginal_profits)) if len(marginal_profits) > 1 else 0.0
    equalized = spread <= 0.05 or len(marginal_profits) <= 1
    degenerate = interior == 0 or degenerate_reason is not None
    if interior == 0:
        degenerate_reason = "every channel sits at a bound; the constraints, not the curves, chose the plan"

    # The expected outcome interval from the ceiling draws, transforms held fixed.
    draws = np.array([c.ceiling_draws for c in curves])  # C x R
    if draws.size and draws.shape[1] > 0:
        r_count = min(d.shape[0] for d in draws)
        sat = np.array(
            [float(c.response(x[j])[()] / c.ceiling) if c.ceiling > 0 else 0.0 for j, c in enumerate(curves)]
        )
        rev_draws = (draws[:, :r_count] * sat[:, None]).sum(axis=0)
        profit_draws = margin * rev_draws - x.sum()
        alpha = (1.0 - POLICY.interval_level) / 2.0
        lower, upper = float(np.quantile(profit_draws, alpha)), float(np.quantile(profit_draws, 1.0 - alpha))
    else:
        lower = upper = profit(x)

    return Plan(
        model_version=model.version,
        backend=model.backend,
        spec_hash=model.spec_hash,
        inputs_hash=design_hash(
            {
                "model": model.version,
                "spec": model.spec_hash,
                "constraints": constraints.model_dump(mode="json"),
            }
        ),
        constraints=constraints,
        allocation=allocation,
        expected_revenue=revenue(x),
        expected_profit=profit(x),
        profit_lower=lower,
        profit_upper=upper,
        level=POLICY.interval_level,
        solver_status=str(best.message),
        starts=starts,
        starts_converged=sum(1 for res, _ in results if res.success),
        marginal_equalized=equalized,
        marginal_spread=spread,
        interior_channels=interior,
        degenerate=degenerate,
        degenerate_reason=degenerate_reason,
    )


def _allowance_constraint(
    j: int, curve: CurveParams, limit: float, rpa: float
) -> Callable[[np.ndarray], float]:
    def inner(x: np.ndarray) -> float:
        return float(limit * curve.response(x[j])[()] / rpa - x[j])

    return inner


def _project(x: np.ndarray, lows: np.ndarray, highs: np.ndarray, total: float) -> np.ndarray:
    """Scale a start onto the budget while staying inside the box."""
    x = np.clip(x, lows, highs)
    for _ in range(50):
        gap = total - x.sum()
        if abs(gap) < 1e-6:
            break
        room = (highs - x) if gap > 0 else (x - lows)
        if room.sum() <= 0:
            break
        x = np.clip(x + gap * room / room.sum(), lows, highs)
    return x


def _describe(
    x: np.ndarray,
    curves: list[CurveParams],
    bounds: list[tuple[float, float]],
    last: np.ndarray,
    constraints: Constraints,
) -> tuple[list[ChannelAllocation], int, list[float], str | None]:
    allocation = []
    interior = 0
    marginal_profits = []
    tol = 1e-3
    for j, c in enumerate(curves):
        low, high = bounds[j]
        spend = float(x[j])
        marginal_return = c.marginal(spend)
        marginal_profit = constraints.margin * marginal_return - 1.0
        at = "interior"
        if spend <= low + tol * max(low, 1.0):
            at = (
                "floor"
                if math.isclose(low, constraints.floor_share * last[j], rel_tol=1e-6)
                else "change limit"
            )
        elif spend >= high - tol * max(high, 1.0):
            at = (
                "ceiling"
                if math.isclose(high, constraints.ceiling_share * last[j], rel_tol=1e-6)
                else "change limit"
            )
        cac = None
        if constraints.allowance and constraints.revenue_per_acquisition:
            rev = float(c.response(spend)[()])
            customers = rev / constraints.revenue_per_acquisition
            cac = spend / customers if customers > 0 else None
            limit = constraints.allowance.get(c.channel)
            if limit is not None and cac is not None and cac >= limit * (1.0 - 1e-4):
                at = "allowance"
        if at == "interior":
            interior += 1
            marginal_profits.append(marginal_profit)
        allocation.append(
            ChannelAllocation(
                channel=c.channel,
                spend=spend,
                last_year=float(last[j]),
                change=spend / last[j] - 1.0 if last[j] > 0 else 0.0,
                expected_revenue=float(c.response(spend)[()]),
                marginal_return=marginal_return,
                marginal_profit=marginal_profit,
                at_bound=at,
                implied_acquisition_cost=cac,
            )
        )
    return allocation, interior, marginal_profits, None


def evaluate(
    model: ModelExport, spend: dict[str, float], margin: float = POLICY.contribution_margin
) -> tuple[float, float]:
    """Revenue and profit of an allocation under a model's curves (the truth's curves included)."""
    revenue = float(sum(c.response(spend[c.channel])[()] for c in model.channels))
    total = float(sum(spend.values()))
    return revenue, margin * revenue - total


def interior_test(
    model: ModelExport, constraints: Constraints, plan: Plan, *, step_share: float = 0.05
) -> tuple[bool, str]:
    """The allocation is an operating point only if moving budget between any two interior
    channels in either direction lowers expected profit; otherwise the optimizer stopped on a
    bound or a flat spot, and the page must say so."""
    interior = [a for a in plan.allocation if a.at_bound == "interior"]
    if len(interior) < 2:
        return False, "fewer than two channels are interior; the constraints chose the plan"
    base = plan.expected_profit
    spend = dict(plan.spend)
    for a in interior:
        for b in interior:
            if a.channel == b.channel:
                continue
            moved = dict(spend)
            delta = step_share * min(a.spend, b.spend)
            moved[a.channel] = a.spend - delta
            moved[b.channel] = b.spend + delta
            _, profit = evaluate(model, moved, constraints.margin)
            if profit > base + 1e-6:
                return (
                    False,
                    f"moving {step_share:.0%} from {a.channel} to {b.channel} raises expected profit",
                )
    return True, "every reallocation between interior channels lowers expected profit"
