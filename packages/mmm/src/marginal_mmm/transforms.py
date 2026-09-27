"""Carryover and saturation, the two transforms both backends apply to spend."""

from __future__ import annotations

import math

import numpy as np


def geometric_adstock(x: np.ndarray, theta: float, max_lag: int) -> np.ndarray:
    """Normalized geometric adstock of a weekly series: weights theta^lag over max_lag lags,
    scaled to sum to one, so a constant spend adstocks to itself."""
    if not 0.0 <= theta < 1.0:
        raise ValueError(f"retention rate must be in [0, 1), got {theta}")
    weights = np.array([theta**lag for lag in range(max_lag + 1)])
    weights /= weights.sum()
    out = np.zeros(len(x))
    for lag, w in enumerate(weights):
        if lag == 0:
            out += w * x
        else:
            out[lag:] += w * x[:-lag]
    return out


def hill(x: np.ndarray, k: float, s: float) -> np.ndarray:
    xs = np.power(np.clip(np.asarray(x, dtype=float), 0.0, None), s)
    return np.asarray(xs / (k**s + xs))


def hill_slope(x: float, k: float, s: float) -> float:
    if x <= 0:
        return 0.0
    return float(s * (k**s) * x ** (s - 1) / (k**s + x**s) ** 2)


def half_life(theta: float) -> float:
    if theta <= 0.0:
        return 0.0
    return math.log(0.5) / math.log(theta)
