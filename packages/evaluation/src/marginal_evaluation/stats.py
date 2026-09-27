"""Intervals and multiple comparison corrections used by every module.

Nothing here knows about marketing. A bootstrap draws in sorted input order from a named
seed stream, so a shuffled input gives the same interval; Benjamini-Hochberg is the one
correction used for any family of comparisons, as on every day of this series.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
from marginal_core.model import StrictModel
from marginal_core.seeds import rng


class Interval(StrictModel):
    estimate: float
    lower: float
    upper: float
    level: float
    replicates: int

    @property
    def width(self) -> float:
        return self.upper - self.lower

    def covers(self, truth: float) -> bool:
        return self.lower <= truth <= self.upper


def bootstrap_interval(
    values: Sequence[float] | np.ndarray,
    statistic: Callable[[np.ndarray], float] = lambda x: float(np.mean(x)),
    *,
    replicates: int = 1000,
    level: float = 0.90,
    seed: int = 0,
    stream: str = "bootstrap",
) -> Interval:
    """Percentile bootstrap of a statistic over independent units."""
    x = np.sort(np.asarray(values, dtype=float))
    if x.size == 0:
        raise ValueError("bootstrap of an empty sample")
    if x.size == 1:
        point = statistic(x)
        return Interval(estimate=point, lower=point, upper=point, level=level, replicates=0)
    r = rng(seed, stream)
    draws = np.empty(replicates)
    for i in range(replicates):
        draws[i] = statistic(x[r.integers(0, x.size, x.size)])
    alpha = (1.0 - level) / 2.0
    return Interval(
        estimate=statistic(x),
        lower=float(np.quantile(draws, alpha)),
        upper=float(np.quantile(draws, 1.0 - alpha)),
        level=level,
        replicates=replicates,
    )


def paired_bootstrap(
    a: Sequence[float] | np.ndarray,
    b: Sequence[float] | np.ndarray,
    statistic: Callable[[np.ndarray], float] = lambda x: float(np.mean(x)),
    *,
    replicates: int = 1000,
    level: float = 0.90,
    seed: int = 0,
    stream: str = "paired",
) -> Interval:
    """Interval on statistic(a) minus statistic(b), resampling the same units for both."""
    x = np.asarray(a, dtype=float)
    y = np.asarray(b, dtype=float)
    if x.shape != y.shape:
        raise ValueError("paired bootstrap needs one value of each per unit")
    if x.size == 0:
        raise ValueError("paired bootstrap of an empty sample")
    order = np.lexsort((y, x))
    x, y = x[order], y[order]
    r = rng(seed, stream)
    draws = np.empty(replicates)
    for i in range(replicates):
        idx = r.integers(0, x.size, x.size)
        draws[i] = statistic(x[idx]) - statistic(y[idx])
    alpha = (1.0 - level) / 2.0
    return Interval(
        estimate=statistic(x) - statistic(y),
        lower=float(np.quantile(draws, alpha)),
        upper=float(np.quantile(draws, 1.0 - alpha)),
        level=level,
        replicates=replicates,
    )


def benjamini_hochberg(p_values: Sequence[float], q: float = 0.05) -> tuple[list[float], list[bool]]:
    """Adjusted p values and the rejection decisions at false discovery rate q."""
    p = np.asarray(p_values, dtype=float)
    if p.size == 0:
        return [], []
    m = p.size
    order = np.argsort(p)
    ranked = p[order] * m / np.arange(1, m + 1)
    adjusted_sorted = np.minimum.accumulate(ranked[::-1])[::-1]
    adjusted = np.empty(m)
    adjusted[order] = np.clip(adjusted_sorted, 0.0, 1.0)
    return [float(v) for v in adjusted], [bool(v <= q) for v in adjusted]


def normal_interval(estimate: float, standard_error: float, level: float = 0.90) -> Interval:
    from scipy.stats import norm

    z = float(norm.ppf(1.0 - (1.0 - level) / 2.0))
    return Interval(
        estimate=estimate,
        lower=estimate - z * standard_error,
        upper=estimate + z * standard_error,
        level=level,
        replicates=0,
    )


def spearman(a: Sequence[float] | np.ndarray, b: Sequence[float] | np.ndarray) -> float:
    """Rank correlation between two orderings; one when they agree completely."""
    x = np.asarray(a, dtype=float)
    y = np.asarray(b, dtype=float)
    if x.size < 2:
        raise ValueError("rank agreement needs at least two items")
    from scipy.stats import rankdata

    rx = rankdata(x)
    ry = rankdata(y)
    if np.std(rx) == 0 or np.std(ry) == 0:
        return 0.0
    return float(np.corrcoef(rx, ry)[0, 1])


def coverage(intervals: Sequence[Interval], truths: Sequence[float]) -> float:
    if len(intervals) != len(truths) or not intervals:
        raise ValueError("coverage needs one truth per interval")
    return float(np.mean([i.covers(t) for i, t in zip(intervals, truths, strict=True)]))
