"""The evaluation protocol for targeting policies on a randomized holdout.

The protocol is the order a careful analyst works in, written as code so that no step can be
skipped or reordered: split by customer (sorted on the key, then one seeded draw each), fit
every model on the training split alone, choose how many to contact on the validation split,
and report every published number from the test split, which took no part in fitting or in
choosing. The test split is scored once.

Four policies are compared on the same customers: the uplift scores of the T learner and the
X learner, the sure things score (the probability of converting, treatment ignored, the rule
most retailers run), and everyone (contact the whole list, the baseline a targeting policy has
to beat before it is worth running).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl
from marginal_core.config import POLICY
from marginal_core.model import StrictModel
from marginal_core.seeds import rng
from marginal_evaluation.stats import Interval

from marginal_targeting.learners import (
    LearnerParams,
    SureThingsPolicy,
    TLearner,
    XLearner,
    binary,
    feature_matrix,
    split_customers,
)
from marginal_targeting.metrics import (
    DEFAULT_POINTS,
    QiniDifference,
    choose_share,
    chosen_on,
    interior_test,
    paired_bootstrap_qini,
    policy_value_curve,
    uplift_curve,
    uplift_top_decile,
)

LEARNERS = ("t_learner", "x_learner")
BASELINES = ("sure_things", "everyone")
SHARE_GRID = tuple(round(0.05 * i, 2) for i in range(1, 21))
"""Shares of the list the policy value curve is read at: 5% to 100% in steps of 5%."""

EVERYONE_REASON = (
    "the everyone policy contacts the whole list by definition; it is the baseline the "
    "targeting policies are judged against, not a choice"
)


class SplitRows(StrictModel):
    train: int
    train_used: int
    validation: int
    test: int


class PolicyValuePoint(StrictModel):
    """The policy value curve read at one share, labelled with the split it was measured on."""

    split: str
    share: float
    incremental_spend_per_contact: float | None
    incremental_conversion_per_contact: float | None
    profit_per_thousand_contacted: float | None
    profit_per_thousand: float | None


class InteriorCheck(StrictModel):
    interior: bool
    reason: str


class PolicyResult(StrictModel):
    """One policy's published figures. Everything but the chosen share comes from the test split."""

    policy: str
    qini: Interval
    top_decile_uplift: float | None
    chosen_share: float
    chosen_on: str
    interior: InteriorCheck
    value_validation: PolicyValuePoint
    value_test: PolicyValuePoint


class ProtocolSettings(StrictModel):
    features: tuple[str, ...]
    treated_col: str
    outcome_col: str
    spend_col: str | None
    key: str
    seed: int
    learners: tuple[str, ...]
    cost_per_contact: float
    margin_on_spend: float
    share_grid: tuple[float, ...]
    points: int
    replicates: int
    level: float
    train_rows: int | None
    params: LearnerParams


@dataclass(frozen=True)
class ProtocolResult:
    """Records for the figures, polars frames for the curves and the scored test split.

    qini: policy, share, qini, qini_lower, qini_upper, random, uplift (test split).
    policy_value: policy, split, share and the policy value columns (validation and test).
    test_scores: key, treatment, outcome (and spend) with one score column per policy.
    """

    settings: ProtocolSettings
    rows: SplitRows
    policies: tuple[PolicyResult, ...]
    differences: tuple[QiniDifference, ...]
    qini: pl.DataFrame
    policy_value: pl.DataFrame
    test_scores: pl.DataFrame

    def policy(self, name: str) -> PolicyResult:
        for result in self.policies:
            if result.policy == name:
                return result
        raise KeyError(f"no policy named {name!r}")

    def summary(self) -> dict[str, Any]:
        """Everything but the frames, ready for a JSON file."""
        return {
            "settings": self.settings.model_dump(mode="json"),
            "rows": self.rows.model_dump(mode="json"),
            "policies": [p.model_dump(mode="json") for p in self.policies],
            "qini_differences": [d.model_dump(mode="json") for d in self.differences],
        }


def _chosen_learners(learners: Sequence[str]) -> tuple[str, ...]:
    chosen = tuple(dict.fromkeys(learners))
    unknown = [name for name in chosen if name not in LEARNERS]
    if unknown or not chosen:
        raise ValueError(f"learners are one or both of {LEARNERS}, got {list(learners)}")
    return chosen


def _collect(lazy: pl.LazyFrame, key: str, keys: pl.Series, columns: Sequence[str]) -> pl.DataFrame:
    """One split's rows, read with only the columns needed.

    The streaming engine keeps a large source from being materialized whole before the semi
    join narrows it; the rows are then sorted by key so a model sees the same order on every run.
    """
    wanted = pl.DataFrame({key: keys}).lazy()
    return lazy.join(wanted, on=key, how="semi").select(list(columns)).collect(engine="streaming").sort(key)


def _point(curve: pl.DataFrame, share: float) -> PolicyValuePoint:
    row = curve.filter((pl.col("share") - share).abs() < 1e-9)
    if row.height != 1:
        raise ValueError(f"the share {share} is not on the curve's grid")
    values = row.row(0, named=True)
    return PolicyValuePoint(
        split=str(values["split"]),
        share=float(values["share"]),
        incremental_spend_per_contact=values["incremental_spend_per_contact"],
        incremental_conversion_per_contact=values["incremental_conversion_per_contact"],
        profit_per_thousand_contacted=values["profit_per_thousand_contacted"],
        profit_per_thousand=values["profit_per_thousand"],
    )


def run_protocol(
    frame: pl.DataFrame | pl.LazyFrame,
    features: Sequence[str],
    treated_col: str,
    outcome_col: str,
    spend_col: str | None,
    key: str,
    seed: int,
    learners: Sequence[str] = LEARNERS,
    cost_per_contact: float = POLICY.email_cost_per_contact,
    margin_on_spend: float = POLICY.email_margin_on_spend,
    *,
    train_rows: int | None = None,
    params: LearnerParams | None = None,
    share_grid: Sequence[float] = SHARE_GRID,
    replicates: int = POLICY.bootstrap_replicates,
    level: float = POLICY.interval_level,
    points: int = DEFAULT_POINTS,
    progress: Callable[[str], None] | None = None,
) -> ProtocolResult:
    """Split, fit on train, choose on validation, report on test.

    frame may be lazy: only the key column is read whole, and each split is read on its own
    with only the columns the models need. train_rows, when set, fits the models on a seeded
    subsample of that many training customers, drawn after sorting on the key; validation and
    test are always used whole.
    """

    def note(message: str) -> None:
        if progress is not None:
            progress(message)

    chosen = _chosen_learners(learners)
    params = params or LearnerParams()
    grid = tuple(float(s) for s in share_grid)
    if not grid or abs(grid[-1] - 1.0) > 1e-12:
        raise ValueError("the share grid must end at the whole list, where the everyone policy sits")
    leaked = {treated_col, outcome_col, key, spend_col} & set(features)
    if leaked:
        raise ValueError(f"the feature set holds {sorted(c for c in leaked if c)}, which a model may not see")
    lazy = frame.lazy()
    schema = lazy.collect_schema()
    columns = [key, *features, treated_col, outcome_col, *([spend_col] if spend_col else [])]
    missing = [c for c in columns if c not in schema]
    if missing:
        raise KeyError(f"the frame lacks {missing}")

    note("split by customer")
    splits = split_customers(lazy.select(key).collect(), key, seed)
    keys = {name: splits.filter(pl.col("split") == name)[key] for name in ("train", "validation", "test")}
    del splits
    train_keys = keys["train"]
    if train_rows is not None and train_rows < train_keys.len():
        # The keys are already sorted, so the draw does not depend on the order rows arrived in.
        picked = np.sort(
            rng(seed, "train_subsample", key).choice(train_keys.len(), train_rows, replace=False)
        )
        train_keys = train_keys.gather(picked)
    rows = SplitRows(
        train=keys["train"].len(),
        train_used=train_keys.len(),
        validation=keys["validation"].len(),
        test=keys["test"].len(),
    )

    note(f"fit on {rows.train_used} training customers")
    train = _collect(lazy, key, train_keys, columns)
    x = feature_matrix(train, features)
    t = binary(train[treated_col], treated_col)
    y = binary(train[outcome_col], outcome_col)
    del train
    models: dict[str, TLearner | XLearner] = {}
    for name in chosen:
        learner = (
            TLearner(features, seed, params) if name == "t_learner" else XLearner(features, seed, params)
        )
        models[name] = learner.fit(x, t, y)
        note(f"fit {name}")
    sure_things = SureThingsPolicy(features, seed, params).fit(x, y)
    note("fit sure_things")
    del x, t, y

    policies = [*chosen, *BASELINES]
    scored: dict[str, pl.DataFrame] = {}
    for split_name in ("validation", "test"):
        part = _collect(lazy, key, keys[split_name], columns)
        x = feature_matrix(part, features)
        scores = {name: models[name].predict_uplift(x) for name in chosen}
        scores["sure_things"] = sure_things.score(x)
        scores["everyone"] = np.zeros(part.height)
        del x
        kept = [key, treated_col, outcome_col, *([spend_col] if spend_col else [])]
        scored[split_name] = part.select(kept).with_columns(
            [pl.Series(name, values) for name, values in scores.items()]
        )
        del part
        note(f"scored the {split_name} split")

    def curve(split_frame: pl.DataFrame, policy: str, split: str) -> pl.DataFrame:
        return policy_value_curve(
            split_frame[policy].to_numpy(),
            split_frame[treated_col].to_numpy(),
            split_frame[outcome_col].to_numpy(),
            split_frame[spend_col].to_numpy() if spend_col else None,
            grid,
            margin_on_spend,
            cost_per_contact,
            split=split,
        ).with_columns(pl.lit(policy).alias("policy"))

    # Choose on validation. chosen_on is the guard: it names the only split a share may be
    # chosen on, and choose_share refuses a curve labelled with any other split.
    selection = chosen_on("validation")
    validation, test = scored["validation"], scored["test"]
    on_validation = {policy: curve(validation, policy, selection) for policy in policies}
    choices: dict[str, tuple[float, InteriorCheck]] = {}
    for policy in policies:
        if policy == "everyone":
            choices[policy] = (1.0, InteriorCheck(interior=False, reason=EVERYONE_REASON))
            continue
        share = choose_share(on_validation[policy])
        passed, reason = interior_test(on_validation[policy], share)
        choices[policy] = (share, InteriorCheck(interior=passed, reason=reason))
    note("chose the shares on validation")

    # Report on test: the shares are fixed now, and the test split is read for the first time.
    treated_test = test[treated_col].to_numpy()
    outcome_test = test[outcome_col].to_numpy()
    boot = paired_bootstrap_qini(
        {policy: test[policy].to_numpy() for policy in policies},
        treated_test,
        outcome_test,
        test[key].to_numpy(),
        seed=seed,
        replicates=replicates,
        level=level,
        points=points,
    )
    note("bootstrapped the Qini on test")
    on_test = {policy: curve(test, policy, "test") for policy in policies}

    results: list[PolicyResult] = []
    qini_frames: list[pl.DataFrame] = []
    for policy in policies:
        share, interior = choices[policy]
        scores_test = test[policy].to_numpy()
        top = uplift_top_decile(scores_test, treated_test, outcome_test)
        results.append(
            PolicyResult(
                policy=policy,
                qini=boot.coefficients[policy],
                top_decile_uplift=None if np.isnan(top) else top,
                chosen_share=share,
                chosen_on=selection,
                interior=interior,
                value_validation=_point(on_validation[policy], share),
                value_test=_point(on_test[policy], share),
            )
        )
        uplift = uplift_curve(scores_test, treated_test, outcome_test, points)["uplift"].to_numpy()
        # The uplift curve has no value at a share of zero, where the Qini curve starts.
        qini_frames.append(
            boot.curves.filter(pl.col("policy") == policy).with_columns(
                pl.Series("uplift", np.concatenate([[np.nan], uplift])).fill_nan(None)
            )
        )

    settings = ProtocolSettings(
        features=tuple(features),
        treated_col=treated_col,
        outcome_col=outcome_col,
        spend_col=spend_col,
        key=key,
        seed=seed,
        learners=chosen,
        cost_per_contact=cost_per_contact,
        margin_on_spend=margin_on_spend,
        share_grid=grid,
        points=points,
        replicates=replicates,
        level=level,
        train_rows=train_rows,
        params=params,
    )
    order = ["policy", "split", "share"]
    policy_value = pl.concat([*on_validation.values(), *on_test.values()]).select(
        *order, pl.all().exclude(order)
    )
    return ProtocolResult(
        settings=settings,
        rows=rows,
        policies=tuple(results),
        differences=boot.differences,
        qini=pl.concat(qini_frames),
        policy_value=policy_value,
        test_scores=test,
    )
