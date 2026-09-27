"""Qini, uplift and policy value curves on a randomized holdout, the choice of how many to
contact, and the known truth measures only the simulator allows.

Every curve contacts customers in descending score order. Customers who share a score are
contacted together or not at all in expectation: inside a tied group the cumulative sums are
interpolated linearly, which is the expected curve under random tie breaking. A constant score
therefore traces the random diagonal exactly, instead of whatever order the rows arrived in.

Units. The Qini value is the standard one, treated outcomes among the contacted minus control
outcomes scaled by the ratio of treated to control counts, rescaled from incremental outcomes
among the treated to incremental outcomes per thousand customers on the list. The rescaling
divides by the treated count of the whole evaluated set, a constant for one curve, so the shape
and the ranking of policies are untouched, and splits and datasets of different sizes share a
unit. The Qini coefficient is the area between that curve and the random diagonal.

Policy value is also stated per thousand customers on the list: the incremental profit of
contacting the top share and leaving the rest alone. A value per thousand contacted is reported
beside it, but it is an average over the contacted, and an average falls as the list deepens
whenever the ranking works, so maximizing it would always pick the smallest share on offer.
The share is chosen where total profit peaks, which is where the marginal contact stops paying
for itself.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import polars as pl
from marginal_core.config import POLICY
from marginal_core.model import StrictModel
from marginal_core.seeds import rng
from marginal_evaluation.stats import Interval
from marginal_sim.customers import QUADRANTS

from marginal_targeting.learners import binary

DEFAULT_POINTS = 100
PER_THOUSAND = 1000.0
TOP_DECILE = 0.10
SELECTION_SPLIT = "validation"
REPORTING_SPLIT = "test"
ArrayLike = Sequence[float] | Sequence[int] | np.ndarray


class QiniDifference(StrictModel):
    """One policy's Qini coefficient minus another's, resampled on the same customers."""

    first: str
    second: str
    interval: Interval


@dataclass(frozen=True)
class QiniBootstrap:
    """Paired bootstrap output: an interval per policy, per pair, and a band per curve point."""

    coefficients: dict[str, Interval]
    differences: tuple[QiniDifference, ...]
    curves: pl.DataFrame


# Input checks


def _scores(values: ArrayLike, name: str = "scores") -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or array.size == 0:
        raise ValueError(f"{name} must be a non empty vector")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} hold missing or infinite values")
    return array


def _vectors(scores: ArrayLike, treated: ArrayLike, outcome: ArrayLike) -> tuple[np.ndarray, ...]:
    s = _scores(scores)
    t = binary(np.asarray(treated), "treated").astype(np.int64)
    y = _scores(outcome, "outcomes")
    if not (s.size == t.size == y.size):
        raise ValueError(f"{s.size} scores, {t.size} treatment flags and {y.size} outcomes")
    if t.all() or not t.any():
        raise ValueError("a curve on a randomized holdout needs both treated and control customers")
    return s, t, y


def _grid(points: int) -> np.ndarray:
    if points < 2:
        raise ValueError("a curve needs at least two points")
    return np.linspace(0.0, 1.0, points + 1)


def _share_grid(share_grid: Sequence[float]) -> np.ndarray:
    grid = np.asarray(share_grid, dtype=np.float64)
    if grid.ndim != 1 or grid.size < 3:
        raise ValueError("the share grid needs at least three shares, or no share could be interior")
    if np.any(grid <= 0.0) or np.any(grid > 1.0) or np.any(np.diff(grid) <= 0.0):
        raise ValueError("the share grid must rise strictly within (0, 1]")
    return grid


# The ranked, tie aware cumulative sums every curve is read from


@dataclass(frozen=True)
class _Members:
    """Where a 0/1 column is one, or zero when that is rarer, in ranked and in input order."""

    ranked: np.ndarray
    customers: np.ndarray
    complement: bool


@dataclass(frozen=True)
class _Ranked:
    """Columns laid out in descending score order, with the end of each tied group.

    When every column is 0/1, the positions of its ones (or of its zeros, whichever are fewer)
    are kept too, so a bootstrap replicate can read the column's weighted prefix sums from a
    cumulative sum over those positions alone instead of over every customer.
    """

    order: np.ndarray
    ends: np.ndarray
    columns: tuple[np.ndarray, ...]
    members: tuple[_Members, ...] | None

    @classmethod
    def build(
        cls, scores: np.ndarray, columns: Sequence[np.ndarray], *, binary: bool | None = None
    ) -> _Ranked:
        order = np.argsort(-scores, kind="stable")
        ranked = scores[order]
        breaks = np.flatnonzero(ranked[1:] != ranked[:-1]) + 1
        ends = np.append(breaks, scores.size)
        laid_out = tuple(c[order] for c in columns)
        members: tuple[_Members, ...] | None = None
        if binary if binary is not None else all(_is_binary(c) for c in columns):
            parts = []
            for c in laid_out:
                complement = bool(c.sum() * 2 > c.size)
                positions = np.flatnonzero(c == (0 if complement else 1))
                parts.append(_Members(ranked=positions, customers=order[positions], complement=complement))
            members = tuple(parts)
        return cls(order=order, ends=ends, columns=laid_out, members=members)

    def at(self, shares: np.ndarray, weights: np.ndarray | None = None) -> np.ndarray:
        """Cumulative count and column sums after contacting each share, one row per quantity.

        Row 0 is the (weighted) number contacted; row j is the sum of column j among them.
        Weights are bootstrap counts per customer, in the order the columns were given.
        """
        if weights is not None and self.members is not None:
            return self._at_members(shares, weights)
        last = self.ends - 1
        table = np.zeros((len(self.columns) + 1, last.size + 1))
        if weights is None:
            table[0, 1:] = self.ends
            for j, column in enumerate(self.columns, start=1):
                table[j, 1:] = np.cumsum(column)[last]
        else:
            w = weights[self.order]
            table[0, 1:] = np.cumsum(w)[last]
            for j, column in enumerate(self.columns, start=1):
                table[j, 1:] = np.cumsum(column * w)[last]
        lower, upper, fraction = _bracket(table[0], shares)
        return np.asarray(table[:, lower] + fraction * (table[:, upper] - table[:, lower]))

    def _at_members(self, shares: np.ndarray, weights: np.ndarray) -> np.ndarray:
        """The weighted path for 0/1 columns: only the count needs a pass over every customer."""
        counts = np.zeros(self.ends.size + 1)
        if self.ends.size == 1:
            counts[1] = weights.sum()
        else:
            cumulative = np.cumsum(weights[self.order])
            counts[1:] = cumulative if self.ends.size == cumulative.size else cumulative[self.ends - 1]
        lower, upper, fraction = _bracket(counts, shares)
        # Group boundary g ends at ranked position ends[g - 1]; boundary 0 is the empty prefix.
        boundaries = np.concatenate([lower, upper])
        positions = np.where(boundaries == 0, 0, self.ends[np.maximum(boundaries - 1, 0)])
        prefix_count = counts[boundaries]
        out = np.empty((len(self.columns) + 1, shares.size))
        out[0] = counts[lower] + fraction * (counts[upper] - counts[lower])
        for j, m in enumerate(self.members or (), start=1):
            running = np.concatenate([[0], np.cumsum(weights[m.customers])])
            prefix = running[np.searchsorted(m.ranked, positions, side="left")].astype(np.float64)
            if m.complement:
                prefix = prefix_count - prefix
            low, high = prefix[: shares.size], prefix[shares.size :]
            out[j] = low + fraction * (high - low)
        return out


def _bracket(counts: np.ndarray, shares: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The group boundaries either side of each share of the (weighted) list, and how far between.

    Interpolating between the two boundaries is the expected prefix sum when the tied group
    being entered is contacted in random order.
    """
    target = shares * counts[-1]
    upper = np.clip(np.searchsorted(counts, target, side="left"), 1, counts.size - 1)
    lower = upper - 1
    width = counts[upper] - counts[lower]
    fraction = np.divide(target - counts[lower], width, out=np.zeros_like(target), where=width > 0)
    return lower, upper, fraction


def _mean(total: np.ndarray, count: np.ndarray) -> np.ndarray:
    """A mean per point that is missing, not zero, where no one was counted."""
    mean = np.divide(total, count, out=np.zeros_like(total), where=count > 0)
    return np.asarray(np.where(count > 0, mean, np.nan))


def _rate_difference(n_t: np.ndarray, n_c: np.ndarray, s_t: np.ndarray, s_c: np.ndarray) -> np.ndarray:
    """Treated mean minus control mean among the contacted; undefined while an arm is empty."""
    return np.asarray(_mean(s_t, n_t) - _mean(s_c, n_c))


def _qini_values(sums: np.ndarray) -> np.ndarray:
    """Qini value per thousand customers on the list from rows (n, treated, y treated, y control).

    The last column must be the whole list, whose treated count sets the scale.
    """
    n, n_t, y_t, y_c = sums[0], sums[1], sums[2], sums[3]
    n_c = n - n_t
    treated_total, control_total = n_t[-1], n_c[-1]
    if treated_total <= 0 or control_total <= 0:
        return np.full(n.size, np.nan)
    # Before the first control customer is contacted there is no control rate to scale; the
    # control term is taken as zero there, which only touches the first sliver of the curve.
    control_term = np.divide(y_c * n_t, n_c, out=np.zeros_like(n), where=n_c > 0)
    return np.asarray(PER_THOUSAND * (y_t - control_term) / treated_total)


def _is_binary(values: np.ndarray) -> bool:
    return bool(np.all((values == 0) | (values == 1)))


def _qini_ranked(s: np.ndarray, t: np.ndarray, y: np.ndarray, *, binary: bool | None = None) -> _Ranked:
    # t is 0/1 by the time it gets here, so the columns are 0/1 exactly when the outcome is.
    return _Ranked.build(s, (t, y * t, y * (1 - t)), binary=_is_binary(y) if binary is None else binary)


def _area(shares: np.ndarray, qini: np.ndarray) -> float:
    return float(np.trapezoid(qini - shares * qini[-1], shares))


# Qini and uplift


def qini_curve(
    uplift_scores: ArrayLike, treated: ArrayLike, outcome: ArrayLike, points: int = DEFAULT_POINTS
) -> pl.DataFrame:
    """The Qini curve by share contacted, with the random diagonal beside it.

    Columns: share (0 to 1), qini (incremental outcomes per thousand customers on the list when
    the top share is contacted), random (the diagonal from the origin to the curve's end).
    """
    s, t, y = _vectors(uplift_scores, treated, outcome)
    shares = _grid(points)
    qini = _qini_values(_qini_ranked(s, t, y).at(shares))
    return pl.DataFrame({"share": shares, "qini": qini, "random": shares * qini[-1]})


def qini_coefficient(
    uplift_scores: ArrayLike, treated: ArrayLike, outcome: ArrayLike, points: int = DEFAULT_POINTS
) -> float:
    """Area between the Qini curve and the random diagonal; zero for a score with no ranking."""
    curve = qini_curve(uplift_scores, treated, outcome, points)
    return _area(curve["share"].to_numpy(), curve["qini"].to_numpy())


def uplift_curve(
    uplift_scores: ArrayLike, treated: ArrayLike, outcome: ArrayLike, points: int = DEFAULT_POINTS
) -> pl.DataFrame:
    """The observed uplift among the contacted by share contacted.

    Columns: share, treated_rate and control_rate (outcome means among the contacted in each arm)
    and uplift (their difference). The curve starts at the first positive share, because a share
    of zero contacts no one and has no rate; it ends at the average effect on the whole list.
    """
    s, t, y = _vectors(uplift_scores, treated, outcome)
    shares = _grid(points)[1:]
    sums = _qini_ranked(s, t, y).at(shares)
    n_t, n_c = sums[1], sums[0] - sums[1]
    treated_rate, control_rate = _mean(sums[2], n_t), _mean(sums[3], n_c)
    return pl.DataFrame(
        {
            "share": shares,
            "treated_rate": treated_rate,
            "control_rate": control_rate,
            "uplift": treated_rate - control_rate,
        }
    )


def uplift_top_decile(uplift_scores: ArrayLike, treated: ArrayLike, outcome: ArrayLike) -> float:
    """Treated rate minus control rate among the ten percent with the highest scores."""
    s, t, y = _vectors(uplift_scores, treated, outcome)
    sums = _qini_ranked(s, t, y).at(np.array([TOP_DECILE]))
    return float(_rate_difference(sums[1], sums[0] - sums[1], sums[2], sums[3])[0])


# Policy value and the choice of how many to contact


def policy_value_curve(
    scores: ArrayLike,
    treated: ArrayLike,
    outcome: ArrayLike,
    spend: ArrayLike | None,
    share_grid: Sequence[float],
    margin_on_spend: float,
    cost_per_contact: float,
    *,
    split: str,
) -> pl.DataFrame:
    """Expected incremental profit of contacting the top share by score, for each share on the grid.

    Among the contacted, the incremental spend per contact is the treated mean spend minus the
    control mean spend, which randomization makes an unbiased estimate of what contacting them
    all would add. Profit per contact is that times the margin, less the cost of the contact.
    With no spend column the outcome itself is the value (margin one and no cost give the
    incremental outcome, for a dataset that publishes no price).

    Columns: split, share, incremental_spend_per_contact, incremental_conversion_per_contact,
    profit_per_thousand_contacted (the average over the contacted) and profit_per_thousand (per
    thousand customers on the list, the quantity the share is chosen on).
    """
    s, t, y = _vectors(scores, treated, outcome)
    grid = _share_grid(share_grid)
    columns: list[np.ndarray] = [t, y * t, y * (1 - t)]
    if spend is not None:
        v = _scores(spend, "spend")
        if v.size != s.size:
            raise ValueError(f"{v.size} spend values for {s.size} customers")
        columns += [v * t, v * (1 - t)]
    sums = _Ranked.build(s, columns).at(grid)
    n_t, n_c = sums[1], sums[0] - sums[1]
    conversion = _rate_difference(n_t, n_c, sums[2], sums[3])
    incremental_spend = _rate_difference(n_t, n_c, sums[4], sums[5]) if spend is not None else None
    value = incremental_spend if incremental_spend is not None else conversion
    per_contact = value * margin_on_spend - cost_per_contact
    return pl.DataFrame(
        {
            "split": [split] * grid.size,
            "share": grid,
            "incremental_spend_per_contact": incremental_spend
            if incremental_spend is not None
            else [None] * grid.size,
            "incremental_conversion_per_contact": conversion,
            "profit_per_thousand_contacted": PER_THOUSAND * per_contact,
            "profit_per_thousand": PER_THOUSAND * grid * per_contact,
        },
        schema_overrides={"incremental_spend_per_contact": pl.Float64},
    ).with_columns(pl.col(pl.Float64).fill_nan(None))


def chosen_on(split_name: str) -> str:
    """The split an operating point may be chosen on, and a guard against choosing it on test.

    A share chosen on the test split and then reported on the test split is a number the test
    helped pick: it is optimistic by construction, which is the bias a three way split exists to
    remove. The training split is refused too, since the models were fit on it.
    """
    if split_name == REPORTING_SPLIT:
        raise ValueError(
            "the share is chosen on the validation split and reported on the test split; "
            "choosing it on the test split would report a number the test helped pick"
        )
    if split_name != SELECTION_SPLIT:
        raise ValueError(f"the share is chosen on the validation split, not on {split_name!r}")
    return split_name


def _curve_split(curve: pl.DataFrame) -> str:
    if "split" not in curve.columns:
        raise ValueError("a policy value curve must say which split it was measured on")
    labels = curve["split"].unique().to_list()
    if len(labels) != 1:
        raise ValueError(f"a policy value curve comes from one split, got {labels}")
    return str(labels[0])


def choose_share(curve: pl.DataFrame) -> float:
    """The share with the highest profit per thousand customers on the validation curve.

    When two shares tie, the smaller is taken: at equal profit, contact fewer customers.
    """
    chosen_on(_curve_split(curve))
    values = curve["profit_per_thousand"].cast(pl.Float64).fill_null(float("nan")).to_numpy()
    if np.all(np.isnan(values)):
        raise ValueError("the policy value curve has no defined point")
    return float(curve["share"][int(np.nanargmax(values))])


def interior_test(curve: pl.DataFrame, share: float) -> tuple[bool, str]:
    """True only when the chosen share is strictly inside the grid and both neighbours earn less.

    A share on the edge of the grid is an answer the grid gave, not the data: the curve may keep
    rising past the largest share or below the smallest. A flat top means the data cannot tell
    the neighbours apart. Either way the operating point is reported as degenerate.
    """
    shares = curve["share"].to_numpy()
    values = curve["profit_per_thousand"].cast(pl.Float64).fill_null(float("nan")).to_numpy()
    hits = np.flatnonzero(np.isclose(shares, share))
    if hits.size != 1:
        raise ValueError(f"the share {share} is not on the curve's grid")
    i = int(hits[0])
    if i == 0:
        return False, (
            f"the chosen share, {shares[0]:.0%}, is the smallest on the grid, "
            "so the curve may still rise below it"
        )
    if i == shares.size - 1:
        return False, (
            f"the chosen share, {shares[-1]:.0%}, is the largest on the grid: the curve is still "
            "rising where the list runs out"
        )
    left, here, right = values[i - 1], values[i], values[i + 1]
    if not (left < here and right < here):
        return False, (
            f"the curve is flat at the chosen share, {shares[i]:.0%}: a neighbour earns as much, "
            "so the data do not pick one share"
        )
    return True, (
        f"the curve peaks at {shares[i]:.0%} and is lower at {shares[i - 1]:.0%} and at {shares[i + 1]:.0%}"
    )


# The paired bootstrap


def paired_bootstrap_qini(
    scores: Mapping[str, ArrayLike],
    treated: ArrayLike,
    outcome: ArrayLike,
    keys: ArrayLike,
    *,
    seed: int,
    replicates: int = POLICY.bootstrap_replicates,
    level: float = POLICY.interval_level,
    points: int = DEFAULT_POINTS,
) -> QiniBootstrap:
    """Intervals on each policy's Qini coefficient and curve by resampling customers.

    Customers are sorted by key before the draw, so the replicates do not depend on the order
    rows arrived in. Every policy is scored on the same resampled customers in each replicate,
    which is what makes the difference between two policies' coefficients a paired comparison:
    the luck of the draw is shared, and the difference interval is narrower than the two
    marginal intervals suggest.
    """
    if not scores:
        raise ValueError("the bootstrap needs at least one policy's scores")
    if replicates < 2:
        raise ValueError("the bootstrap needs at least two replicates")
    names = list(scores)
    k = np.asarray(keys)
    order = np.argsort(k, kind="stable")
    if k.size > 1 and np.any(k[order][1:] == k[order][:-1]):
        raise ValueError("the bootstrap resamples customers, so each key must appear once")
    t = binary(np.asarray(treated), "treated").astype(np.int64)
    y = _scores(outcome, "outcomes")
    if not (t.size == y.size == k.size):
        raise ValueError(f"{k.size} keys, {t.size} treatment flags and {y.size} outcomes")
    t, y = t[order], y[order]
    outcome_binary = _is_binary(y)
    ranked = {}
    for name in names:
        s, _, _ = _vectors(scores[name], t, y)
        ranked[name] = _qini_ranked(s[order], t, y, binary=outcome_binary)

    shares = _grid(points)
    point = {name: _qini_values(ranked[name].at(shares)) for name in names}
    estimate = {name: _area(shares, point[name]) for name in names}

    draw = rng(seed, "qini_bootstrap")
    coefficients = np.empty((replicates, len(names)))
    bands = np.empty((replicates, len(names), shares.size))
    for b in range(replicates):
        # Resampling with replacement is a count per customer; the counts weight the sums, so
        # every policy sees the same resampled customers without copying the data per draw.
        weights = np.bincount(draw.integers(0, k.size, k.size), minlength=k.size)
        for j, name in enumerate(names):
            curve = _qini_values(ranked[name].at(shares, weights))
            bands[b, j] = curve
            coefficients[b, j] = _area(shares, curve)

    alpha = (1.0 - level) / 2.0

    def interval(estimate_: float, draws: np.ndarray) -> Interval:
        # A replicate that drew no treated or no control customer has no curve; it is dropped
        # rather than allowed to turn the percentile into a missing value.
        return Interval(
            estimate=estimate_,
            lower=float(np.nanquantile(draws, alpha)),
            upper=float(np.nanquantile(draws, 1.0 - alpha)),
            level=level,
            replicates=replicates,
        )

    intervals = {name: interval(estimate[name], coefficients[:, j]) for j, name in enumerate(names)}
    differences = tuple(
        QiniDifference(
            first=first,
            second=names[j],
            interval=interval(estimate[first] - estimate[names[j]], coefficients[:, i] - coefficients[:, j]),
        )
        for i, first in enumerate(names)
        for j in range(i + 1, len(names))
    )
    curves = pl.concat(
        [
            pl.DataFrame(
                {
                    "policy": [name] * shares.size,
                    "share": shares,
                    "qini": point[name],
                    "qini_lower": np.nanquantile(bands[:, j, :], alpha, axis=0),
                    "qini_upper": np.nanquantile(bands[:, j, :], 1.0 - alpha, axis=0),
                    "random": shares * point[name][-1],
                }
            )
            for j, name in enumerate(names)
        ]
    )
    return QiniBootstrap(coefficients=intervals, differences=differences, curves=curves)


# Known truth measures, for the simulator only


def pehe(uplift_pred: ArrayLike, tau_true: ArrayLike) -> float:
    """Precision in estimating heterogeneous effects: the root mean squared error of the
    predicted uplift against the true effect. Only a simulator can report it."""
    predicted = _scores(uplift_pred, "predicted uplift")
    truth = _scores(tau_true, "true effects")
    if predicted.size != truth.size:
        raise ValueError(f"{predicted.size} predictions for {truth.size} true effects")
    return float(np.sqrt(np.mean((predicted - truth) ** 2)))


def contact_mask(scores: ArrayLike, share: float) -> np.ndarray:
    """The customers a policy contacts at a share: the top share by score, rounded to a count.

    Ties at the cut are broken by position, so pass the scores in key order for a stable mask.
    """
    s = _scores(scores)
    if not 0.0 <= share <= 1.0:
        raise ValueError("a share is between zero and one")
    count = int(round(share * s.size))
    mask = np.zeros(s.size, dtype=bool)
    mask[np.argsort(-s, kind="stable")[:count]] = True
    return mask


def quadrant_shares_contacted(
    policy_contacted_mask: ArrayLike, quadrant: Sequence[str] | np.ndarray | pl.Series
) -> dict[str, float]:
    """The share of each true quadrant that a policy contacts; not defined for an empty quadrant."""
    mask = np.asarray(policy_contacted_mask, dtype=bool)
    labels = quadrant.to_numpy() if isinstance(quadrant, pl.Series) else np.asarray(quadrant)
    if mask.size != labels.size:
        raise ValueError(f"{mask.size} contact flags for {labels.size} customers")
    unknown = set(np.unique(labels).tolist()) - set(QUADRANTS)
    if unknown:
        raise ValueError(f"unknown quadrant labels {sorted(unknown)}")
    shares: dict[str, float] = {}
    for q in QUADRANTS:
        members = labels == q
        shares[q] = float(mask[members].mean()) if members.any() else float("nan")
    return shares


def oracle_regret(contacted_mask: ArrayLike, y0: ArrayLike, y1: ArrayLike) -> int:
    """Incremental conversions a policy leaves on the table against the oracle.

    The oracle contacts every persuadable (y0 = 0, y1 = 1) and no sleeping dog (y0 = 1, y1 = 0),
    and contacting a sure thing or a lost cause changes nothing, so the oracle earns one
    conversion per persuadable and its regret is zero by construction. A policy's regret is the
    persuadables it missed plus the sleeping dogs it woke.
    """
    mask = np.asarray(contacted_mask, dtype=bool)
    untreated = binary(np.asarray(y0), "y0").astype(np.int64)
    treated = binary(np.asarray(y1), "y1").astype(np.int64)
    if not (mask.size == untreated.size == treated.size):
        raise ValueError("one contact flag and both potential outcomes per customer")
    oracle = int(np.sum((untreated == 0) & (treated == 1)))
    earned = int(np.sum((treated - untreated)[mask]))
    return oracle - earned
