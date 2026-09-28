"""The Gamma-Gamma model of spend per purchase (Fader, Hardie and Lee 2005, "RFM and CLV").

Each purchase a customer makes is worth z ~ Gamma(p, nu), where nu is the customer's own scale,
and across customers nu ~ Gamma(q, v). A customer with x repeat purchases averaging m has, with
nu integrated out, the density

    f(m | x) = Gamma(p x + q) / (Gamma(p x) Gamma(q)) * v^q * x^(p x) * m^(p x - 1) / (v + x m)^(p x + q)

and the expected value of that customer's next purchase is the weighted average

    E(Z | m, x) = (q - 1) / (p x + q - 1) * p v / (q - 1)  +  p x / (p x + q - 1) * m

of the population mean p v / (q - 1) and the customer's own mean: the more purchases behind the
customer's mean, the more weight it carries. A customer without a repeat purchase gets the
population mean, which exists only when q > 1.

Only repeat purchases enter, for the reason marginal_clv.frame gives, and only customers with at
least one. The fit is the same as BG/NBD's: BFGS on the log parameters with the analytic
gradient, and the same convergence test.

The model assumes a customer's spend per purchase does not depend on how often they buy.
`spend_frequency_correlation` reports the Pearson correlation between frequency and mean repeat
spend among repeat customers, the check the Gamma-Gamma literature asks for before the model is
used; a correlation near zero does not prove independence, but a strong one rules the model out.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from marginal_core.model import StrictModel
from scipy.optimize import minimize
from scipy.special import digamma, gammaln

from marginal_clv.bgnbd import GRADIENT_ACCEPT, GTOL, MAX_ITERATIONS, FitRecord, Vector, beyond_limit

PARAMETERS = ("p", "q", "v")

PARAMETER_FLOOR = 1e-12
PARAMETER_CEILING = 1e12

WEAK_CORRELATION = 0.3
"""Below this in absolute value, frequency and spend count as weakly correlated. A convention
for a check, not a test statistic: the point is to catch a strong dependence, not to certify
independence."""


class IndependenceCheck(StrictModel):
    correlation: float
    customers: int
    threshold: float
    weak: bool


def _pair(frequency: Vector, monetary: Vector) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(frequency, dtype=np.float64)
    m = np.asarray(monetary, dtype=np.float64)
    if x.ndim != 1 or m.shape != x.shape:
        raise ValueError("frequency and monetary need one value each per customer")
    if not np.all(np.isfinite(x)) or np.any(x < 0):
        raise ValueError("frequency holds missing, infinite or negative values")
    return x, m


def repeat_customers(frequency: Vector, monetary: Vector) -> tuple[np.ndarray, np.ndarray]:
    """Frequency and mean repeat spend of the customers with at least one repeat purchase."""
    x, m = _pair(frequency, monetary)
    keep = x > 0
    x, m = x[keep], m[keep]
    if not np.all(np.isfinite(m)) or np.any(m <= 0):
        raise ValueError("a repeat customer has a missing or non positive mean spend")
    return x, m


def _clip(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError(f"a Gamma-Gamma parameter is not finite: {value}")
    return min(max(value, PARAMETER_FLOOR), PARAMETER_CEILING)


def _from_log(log_params: np.ndarray) -> tuple[float, float, float]:
    bounded = np.clip(log_params, math.log(PARAMETER_FLOOR), math.log(PARAMETER_CEILING))
    p, q, v = (_clip(float(value)) for value in np.exp(bounded))
    return p, q, v


def _log_likelihood(p: float, q: float, v: float, x: np.ndarray, m: np.ndarray) -> np.ndarray:
    px = p * x
    ll: np.ndarray = (
        gammaln(px + q)
        - gammaln(px)
        - gammaln(q)
        + q * math.log(v)
        + (px - 1.0) * np.log(m)
        + px * np.log(x)
        - (px + q) * np.log(x * m + v)
    )
    return ll


def _objective(log_params: np.ndarray, x: np.ndarray, m: np.ndarray) -> tuple[float, np.ndarray]:
    """Mean negative log likelihood and its gradient with respect to the log parameters."""
    p, q, v = _from_log(log_params)
    px = p * x
    log_total = np.log(x * m + v)
    d_p = x * (digamma(px + q) - digamma(px) + np.log(m) + np.log(x) - log_total)
    d_q = digamma(px + q) - digamma(q) + math.log(v) - log_total
    d_v = q / v - (px + q) / (x * m + v)
    gradient = np.array([p * d_p.mean(), q * d_q.mean(), v * d_v.mean()], dtype=np.float64)
    return float(-_log_likelihood(p, q, v, x, m).mean()), -gradient


@dataclass
class GammaGamma:
    """Gamma-Gamma with parameters p, q and v; ``fit`` sets them by maximum likelihood."""

    p: float = 1.0
    q: float = 2.0
    v: float = 1.0
    record: FitRecord | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        for name in PARAMETERS:
            value = getattr(self, name)
            if not (math.isfinite(value) and value > 0):
                raise ValueError(f"Gamma-Gamma parameter {name} must be positive and finite, got {value}")

    @property
    def params(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in PARAMETERS}

    def fit(self, frequency: Vector, monetary: Vector) -> GammaGamma:
        """Fit on the customers with frequency above zero; the others carry no repeat spend."""
        x, m = repeat_customers(frequency, monetary)
        if x.size < len(PARAMETERS):
            raise ValueError(f"Gamma-Gamma needs at least {len(PARAMETERS)} repeat customers, got {x.size}")
        # With q at two, the population mean spend p v / (q - 1) starts at the sample mean.
        start = np.log(np.array([1.0, 2.0, float(m.mean())]))
        result = minimize(
            _objective,
            start,
            args=(x, m),
            jac=True,
            method="BFGS",
            options={"gtol": GTOL, "maxiter": MAX_ITERATIONS},
        )
        solution = np.asarray(result.x, dtype=np.float64)
        mean_nll, gradient = _objective(solution, x, m)
        # v is in money, so it is judged against the mean repeat spend (see bgnbd.LOG_LIMIT).
        beyond = beyond_limit(PARAMETERS, solution, {"v": float(m.mean())})
        gradient_max = float(np.max(np.abs(gradient)))
        self.p, self.q, self.v = _from_log(solution)
        self.record = FitRecord(
            method="BFGS on log parameters, analytic gradient",
            success=bool(result.success),
            converged=gradient_max <= GRADIENT_ACCEPT and not beyond,
            status=int(result.status),
            message=str(result.message),
            evaluations=int(result.nfev),
            iterations=int(result.nit),
            neg_log_likelihood=mean_nll * x.size,
            gradient_max=gradient_max,
            beyond_limit=beyond,
            customers=int(x.size),
        )
        return self

    def log_likelihood_by_customer(self, frequency: Vector, monetary: Vector) -> np.ndarray:
        """Log likelihood of each repeat customer, in the order they appear."""
        x, m = repeat_customers(frequency, monetary)
        return _log_likelihood(_clip(self.p), _clip(self.q), _clip(self.v), x, m)

    def log_likelihood(self, frequency: Vector, monetary: Vector) -> float:
        return float(np.sum(self.log_likelihood_by_customer(frequency, monetary)))

    @property
    def population_mean_spend(self) -> float:
        """Mean spend per purchase across customers, p v / (q - 1)."""
        if self.q <= 1.0:
            raise ValueError(f"q = {self.q:.4g} is not above one, so the fitted spend has no finite mean")
        return self.p * self.v / (self.q - 1.0)

    def conditional_expected_average_profit(self, frequency: Vector, monetary: Vector) -> np.ndarray:
        """Expected spend per purchase for each customer, given their repeat purchases.

        The name follows the literature; the value is revenue per purchase, and the contribution
        margin is applied where the allowance is computed. A customer without a repeat purchase
        may carry a null mean spend and gets the population mean.
        """
        population = self.population_mean_spend
        x, m = _pair(frequency, monetary)
        repeat = x > 0
        if not np.all(np.isfinite(m[repeat])) or np.any(m[repeat] <= 0):
            raise ValueError("a repeat customer has a missing or non positive mean spend")
        own = np.where(repeat, m, 0.0)
        weight = self.p * x / (self.p * x + self.q - 1.0)
        expected: np.ndarray = (1.0 - weight) * population + weight * own
        return expected


def spend_frequency_correlation(frequency: Vector, monetary: Vector) -> IndependenceCheck:
    """Pearson correlation of frequency and mean repeat spend among repeat customers."""
    x, m = repeat_customers(frequency, monetary)
    if x.size < 3 or np.std(x) == 0 or np.std(m) == 0:
        raise ValueError("the correlation needs at least three repeat customers with varying values")
    correlation = float(np.corrcoef(x, m)[0, 1])
    return IndependenceCheck(
        correlation=correlation,
        customers=int(x.size),
        threshold=WEAK_CORRELATION,
        weak=abs(correlation) < WEAK_CORRELATION,
    )
