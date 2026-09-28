"""The BG/NBD purchase frequency model (Fader, Hardie and Lee 2005), fit by maximum likelihood.

The model's account of one customer: while active, purchases arrive as a Poisson process with
rate lambda, and after each repeat purchase the customer leaves for good with probability p.
Across customers lambda is Gamma(r, alpha) and p is Beta(a, b). A customer enters as frequency
x (repeat purchases), recency t_x (the last purchase, counted from the first) and age T (the
first purchase to the end of the window), all in days here, so alpha is in days too.

The likelihood of one customer (FHL 2005, equation 6) is

    L = B(a, b + x) / B(a, b) * Gamma(r + x) alpha^r / (Gamma(r) (alpha + T)^(r + x))
      + [x > 0] B(a + 1, b + x - 1) / B(a, b) * Gamma(r + x) alpha^r / (Gamma(r) (alpha + t_x)^(r + x))

It is evaluated in logs: the common factors are added as log gamma and log beta terms, the
ratio of the two beta functions becomes a / (b + x - 1), and the two branches are combined
with logaddexp, so no power of (alpha + T) is ever formed. With the parameters clipped to
[PARAMETER_FLOOR, PARAMETER_CEILING] and the inputs clipped to a valid customer (x and T not
negative, t_x between 0 and T) every term is finite, which is what lets the optimizer probe
far from the answer without a NaN ending the search.

The fit minimizes the mean negative log likelihood per customer with scipy.optimize.minimize
(BFGS) on the logs of r, alpha, a and b, which keeps each parameter positive, using the
analytic gradient. The tolerance is tight on purpose. On purchase histories like the retail
file the likelihood has a long, nearly flat ridge along which a and b grow together with a / b
almost fixed; a default stopping rule halts somewhere on that ridge (on the retail file, scipy's
L-BFGS-B at its default tolerances stopped at b = 180 from one start, and PyMC-Marketing's MAP at
its defaults at b = 304, against b = 309 at the optimum), and the published a and b then
describe the stopping rule rather than the data. BFGS is used rather than L-BFGS-B because on
that ridge L-BFGS-B's line search gives up before the gradient is small. Convergence
is judged by the first order condition itself (the largest gradient component at the answer),
not only by the optimizer's own flag, and a parameter that runs off to an extreme value is
reported, not published as an estimate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt
from marginal_core.model import StrictModel
from scipy.optimize import minimize
from scipy.special import betaln, digamma, expit, gammaln, hyp2f1

PARAMETERS = ("r", "alpha", "a", "b")

PARAMETER_FLOOR = 1e-12
PARAMETER_CEILING = 1e12
"""The likelihood clips each parameter into this range, wide enough never to bind in a fit."""

LOG_LIMIT = 12.0
"""A fitted parameter more than e^12 (about 1.6e5) times above or below its natural scale means
the maximum of the likelihood lies on the edge of the parameter space: the search ran along a
direction where the likelihood keeps rising ever more slowly (a toward zero when the data show
no one leaving, a and b together toward infinity when everyone leaves at the same rate), and
where it stopped is not an estimate. The natural scale is one for a shape parameter, and the
sample's mean age or mean spend for a parameter measured in days or money (alpha here, v in
Gamma-Gamma), so the check does not depend on units. Small samples of the retail file end
this way; the full calibration frame does not."""

GTOL = 1e-8
MAX_ITERATIONS = 2000

GRADIENT_ACCEPT = 1e-6
"""Converged means every component of the gradient of the mean log likelihood, taken with
respect to the log parameters, is below this at the answer and no parameter is beyond
LOG_LIMIT."""

NEAR_ONE = 1e-6
"""The conditional expectation has a removable singularity at a = 1 (a factor 1 / (a - 1)
against a bracket that vanishes). Within this distance of 1 it is averaged over a = 1 - NEAR_ONE
and a = 1 + NEAR_ONE, which cancels the first order error of stepping off the point."""

Vector = npt.ArrayLike


def beyond_limit(names: tuple[str, ...], log_values: np.ndarray, scales: dict[str, float]) -> list[str]:
    """The parameters whose fitted log lies more than LOG_LIMIT from the log of their scale."""
    return [
        name
        for name, value in zip(names, log_values, strict=True)
        if abs(float(value) - math.log(scales.get(name, 1.0))) > LOG_LIMIT
    ]


class FitRecord(StrictModel):
    """What the optimizer did, kept beside the estimates so a reader can judge them."""

    method: str
    success: bool
    converged: bool
    status: int
    message: str
    evaluations: int
    iterations: int
    neg_log_likelihood: float
    gradient_max: float
    beyond_limit: list[str]
    customers: int


def _vector(values: Vector, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1:
        raise ValueError(f"{name} must be a vector with one value per customer")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} holds missing or infinite values")
    return array


def customer_arrays(
    frequency: Vector, recency: Vector, T: Vector
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Frequency, recency and age as float arrays, clipped to a customer the model can describe.

    The frame builder already produces valid customers; the clip guards the likelihood against
    a recency a rounding error above the age, not against wrong data, which the finiteness
    check refuses.
    """
    x = _vector(frequency, "frequency")
    t_x = _vector(recency, "recency")
    age = _vector(T, "T")
    if not (x.size == t_x.size == age.size):
        raise ValueError("frequency, recency and T need one value each per customer")
    x = np.clip(x, 0.0, None)
    age = np.clip(age, 0.0, None)
    t_x = np.clip(t_x, 0.0, age)
    return x, t_x, age


def _clip(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError(f"a BG/NBD parameter is not finite: {value}")
    return min(max(value, PARAMETER_FLOOR), PARAMETER_CEILING)


def _from_log(log_params: np.ndarray) -> tuple[float, float, float, float]:
    """Parameters from their logs, clipped first so a long probe step cannot overflow."""
    bounded = np.clip(log_params, math.log(PARAMETER_FLOOR), math.log(PARAMETER_CEILING))
    r, alpha, a, b = (_clip(float(v)) for v in np.exp(bounded))
    return r, alpha, a, b


def _terms(
    r: float, alpha: float, a: float, b: float, x: np.ndarray, t_x: np.ndarray, age: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Per customer log likelihood, the log of each branch, and the log of their sum."""
    repeat = x > 0
    common = gammaln(r + x) - gammaln(r) + r * math.log(alpha) + betaln(a, b + x) - betaln(a, b)
    survived = -(r + x) * np.log(alpha + age)
    dropped = np.full(x.shape, -np.inf)
    xr = x[repeat]
    dropped[repeat] = math.log(a) - np.log(b + xr - 1.0) - (r + xr) * np.log(alpha + t_x[repeat])
    branches = np.logaddexp(survived, dropped)
    return common + branches, survived, dropped, branches


def _objective(
    log_params: np.ndarray, x: np.ndarray, t_x: np.ndarray, age: np.ndarray
) -> tuple[float, np.ndarray]:
    """Mean negative log likelihood and its gradient with respect to the log parameters."""
    r, alpha, a, b = _from_log(log_params)
    ll, survived, dropped, branches = _terms(r, alpha, a, b, x, t_x, age)
    # Each branch's share of the likelihood; the dropped branch is zero without a repeat purchase.
    w_survived = np.exp(survived - branches)
    w_dropped = np.exp(dropped - branches)
    repeat = x > 0
    b_x = np.where(repeat, b + x - 1.0, 1.0)
    d_r = (
        digamma(r + x)
        - digamma(r)
        + math.log(alpha)
        - w_survived * np.log(alpha + age)
        - w_dropped * np.log(alpha + t_x)
    )
    d_alpha = r / alpha - (r + x) * (w_survived / (alpha + age) + w_dropped / (alpha + t_x))
    d_a = digamma(a + b) - digamma(a + b + x) + w_dropped / a
    d_b = digamma(b + x) - digamma(a + b + x) - digamma(b) + digamma(a + b) - w_dropped / b_x
    gradient = np.array(
        [r * d_r.mean(), alpha * d_alpha.mean(), a * d_a.mean(), b * d_b.mean()], dtype=np.float64
    )
    return float(-ll.mean()), -gradient


def _alpha_start(x: np.ndarray, age: np.ndarray) -> float:
    """With r at one, the mean purchase rate r / alpha matches repeat purchases per day of age.

    The caller has checked that someone made a repeat purchase, so the mean frequency is positive.
    """
    return max(float(age.mean()), 1.0) / float(x.mean())


def _probability_alive(
    r: float, alpha: float, a: float, b: float, x: np.ndarray, t_x: np.ndarray, age: np.ndarray
) -> np.ndarray:
    repeat = x > 0
    log_odds_gone = np.full(x.shape, -np.inf)
    xr = x[repeat]
    log_odds_gone[repeat] = (
        math.log(a)
        - np.log(b + xr - 1.0)
        + (r + xr) * (np.log(alpha + age[repeat]) - np.log(alpha + t_x[repeat]))
    )
    alive: np.ndarray = expit(-log_odds_gone)
    return alive


def _conditional_expectation(
    r: float,
    alpha: float,
    a: float,
    b: float,
    horizon: np.ndarray,
    x: np.ndarray,
    t_x: np.ndarray,
    age: np.ndarray,
) -> np.ndarray:
    """FHL 2005 equation 10: expected purchases in (T, T + t] given x, t_x and T.

        E = P(alive) * (a + b + x - 1) / (a - 1)
              * [1 - ((alpha + T) / (alpha + T + t))^(r + x) 2F1(r + x, b + x; a + b + x - 1; z)]

    with z = t / (alpha + T + t). The bracket is formed as -expm1 of its log so it keeps its
    precision when it is small. For a customer with many repeat purchases the series 2F1 can
    overflow; there Euler's transformation gives the same bracket from
    (1 - z)^(a - 1) 2F1(a + b - 1 - r, a - 1; a + b + x - 1; z), whose first two arguments do
    not grow with x.
    """
    z = horizon / (alpha + age + horizon)
    c = a + b + x - 1.0
    log_keep = np.log(alpha + age) - np.log(alpha + age + horizon)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        log_term = (r + x) * log_keep + np.log(hyp2f1(r + x, b + x, c, z))
        euler = (a - 1.0) * log_keep + np.log(hyp2f1(a + b - 1.0 - r, a - 1.0, c, z))
    log_term = np.where(np.isfinite(log_term), log_term, euler)
    if not np.all(np.isfinite(log_term)):
        bad = int(np.sum(~np.isfinite(log_term)))
        raise ValueError(f"the BG/NBD conditional expectation is not finite for {bad} customers")
    bracket = -np.expm1(log_term)
    expected: np.ndarray = _probability_alive(r, alpha, a, b, x, t_x, age) * c / (a - 1.0) * bracket
    return np.clip(expected, 0.0, None)


@dataclass
class BGNBD:
    """BG/NBD with parameters r, alpha, a and b; ``fit`` sets them by maximum likelihood."""

    r: float = 1.0
    alpha: float = 1.0
    a: float = 1.0
    b: float = 1.0
    record: FitRecord | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        for name in PARAMETERS:
            value = getattr(self, name)
            if not (math.isfinite(value) and value > 0):
                raise ValueError(f"BG/NBD parameter {name} must be positive and finite, got {value}")

    @property
    def params(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in PARAMETERS}

    def _clipped(self) -> tuple[float, float, float, float]:
        return _clip(self.r), _clip(self.alpha), _clip(self.a), _clip(self.b)

    def fit(self, frequency: Vector, recency: Vector, T: Vector) -> BGNBD:
        x, t_x, age = customer_arrays(frequency, recency, T)
        if x.size == 0:
            raise ValueError("BG/NBD needs at least one customer")
        if not np.any(x > 0):
            raise ValueError("no customer made a repeat purchase, so the dropout process cannot be fit")
        start = np.log(np.array([1.0, _alpha_start(x, age), 1.0, 1.0]))
        result = minimize(
            _objective,
            start,
            args=(x, t_x, age),
            jac=True,
            method="BFGS",
            options={"gtol": GTOL, "maxiter": MAX_ITERATIONS},
        )
        solution = np.asarray(result.x, dtype=np.float64)
        mean_nll, gradient = _objective(solution, x, t_x, age)
        beyond = beyond_limit(PARAMETERS, solution, {"alpha": max(float(age.mean()), 1.0)})
        gradient_max = float(np.max(np.abs(gradient)))
        self.r, self.alpha, self.a, self.b = _from_log(solution)
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

    def log_likelihood_by_customer(self, frequency: Vector, recency: Vector, T: Vector) -> np.ndarray:
        x, t_x, age = customer_arrays(frequency, recency, T)
        ll, _, _, _ = _terms(*self._clipped(), x, t_x, age)
        return ll

    def log_likelihood(self, frequency: Vector, recency: Vector, T: Vector) -> float:
        return float(np.sum(self.log_likelihood_by_customer(frequency, recency, T)))

    def probability_alive(self, frequency: Vector, recency: Vector, T: Vector) -> np.ndarray:
        """Probability each customer is still active at the end of the window.

        One for a customer without a repeat purchase: in this model a customer can only leave
        right after a repeat purchase, a known property of BG/NBD rather than a claim that
        one time buyers are all still active.
        """
        x, t_x, age = customer_arrays(frequency, recency, T)
        return _probability_alive(*self._clipped(), x, t_x, age)

    def expected_purchases(
        self, t: float | npt.ArrayLike, frequency: Vector, recency: Vector, T: Vector
    ) -> np.ndarray:
        """Expected purchase days in the next t days for each customer (FHL 2005, equation 10)."""
        x, t_x, age = customer_arrays(frequency, recency, T)
        horizon = np.asarray(t, dtype=np.float64)
        if not np.all(np.isfinite(horizon)) or np.any(horizon < 0):
            raise ValueError("the horizon t must be finite and not negative")
        r, alpha, a, b = self._clipped()
        if abs(a - 1.0) < NEAR_ONE:
            below = _conditional_expectation(r, alpha, 1.0 - NEAR_ONE, b, horizon, x, t_x, age)
            above = _conditional_expectation(r, alpha, 1.0 + NEAR_ONE, b, horizon, x, t_x, age)
            averaged: np.ndarray = 0.5 * (below + above)
            return averaged
        return _conditional_expectation(r, alpha, a, b, horizon, x, t_x, age)
