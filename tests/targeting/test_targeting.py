"""Known truth tests for targeting: the curves, the operating point, the learners, and the rule
that the share is chosen on validation and reported on test.

The synthetic customers carry both potential outcomes. One uniform draw decides both, so a
customer whose effect is positive can only gain from the email and one whose effect is negative
can only lose, and the quadrants are exact rather than estimated.
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from marginal_targeting import (
    SHARE_GRID,
    LearnerParams,
    ProtocolResult,
    TLearner,
    XLearner,
    choose_share,
    chosen_on,
    interior_test,
    oracle_regret,
    paired_bootstrap_qini,
    pehe,
    policy_value_curve,
    qini_coefficient,
    qini_curve,
    quadrant_shares_contacted,
    run_protocol,
    split_customers,
    uplift_curve,
    uplift_top_decile,
)

FEATURES = ("x0", "x1", "x2", "x3", "x4")


def _customers(n: int = 10_000, seed: int = 3) -> pl.DataFrame:
    """Uplift rises with x0 and turns negative at its low end; baseline conversion rises with x1."""
    r = np.random.default_rng(seed)
    x = r.normal(size=(n, len(FEATURES)))
    p0 = 1.0 / (1.0 + np.exp(-(-0.8 + 0.7 * x[:, 1])))
    p1 = np.clip(p0 + 0.05 + 0.15 * np.tanh(1.5 * x[:, 0]), 0.01, 0.99)
    u = r.random(n)
    y0 = (u < p0).astype(np.int8)
    y1 = (u < p1).astype(np.int8)
    treated = (r.random(n) < 0.5).astype(np.int8)
    converted = np.where(treated == 1, y1, y0)
    return pl.DataFrame(
        {
            "customer_id": np.arange(n, dtype=np.int64),
            **{name: x[:, i] for i, name in enumerate(FEATURES)},
            "treated": treated,
            "converted": converted,
            "spend": converted * 40.0,
            "tau": p1 - p0,
            "y0": y0,
            "y1": y1,
        }
    )


def _quadrants(frame: pl.DataFrame) -> np.ndarray:
    y0, y1 = frame["y0"].to_numpy(), frame["y1"].to_numpy()
    return np.select(
        [(y0 == 0) & (y1 == 1), (y0 == 1) & (y1 == 1), (y0 == 0) & (y1 == 0)],
        ["persuadable", "sure_thing", "lost_cause"],
        default="sleeping_dog",
    )


@pytest.fixture(scope="module")
def customers() -> pl.DataFrame:
    return _customers()


@pytest.fixture(scope="module")
def protocol(customers: pl.DataFrame) -> ProtocolResult:
    return run_protocol(
        customers.select("customer_id", *FEATURES, "treated", "converted", "spend"),
        FEATURES,
        "treated",
        "converted",
        "spend",
        "customer_id",
        seed=7,
        learners=("t_learner", "x_learner"),
        cost_per_contact=0.12,
        margin_on_spend=0.30,
        params=LearnerParams(n_estimators=100),
    )


def _hand_curve(values: list[float], split: str = "validation") -> pl.DataFrame:
    shares = [round(0.1 * i, 1) for i in range(1, len(values) + 1)]
    return pl.DataFrame({"split": [split] * len(values), "share": shares, "profit_per_thousand": values})


# 1. Qini and uplift curves


def test_a_perfect_score_beats_a_random_one_and_random_is_near_zero(customers: pl.DataFrame) -> None:
    t = customers["treated"].to_numpy()
    y = customers["converted"].to_numpy()
    perfect = customers["tau"].to_numpy()
    random = np.random.default_rng(11).random(customers.height)

    q_perfect = qini_coefficient(perfect, t, y)
    q_random = qini_coefficient(random, t, y)
    assert q_perfect > 0
    assert abs(q_random) < 0.1 * q_perfect
    # A constant score has no ranking at all: tied customers are contacted together, so the curve
    # is the diagonal itself.
    assert qini_coefficient(np.zeros(customers.height), t, y) == pytest.approx(0.0, abs=1e-9)
    assert uplift_top_decile(perfect, t, y) > uplift_top_decile(random, t, y)

    best, blind = qini_curve(perfect, t, y), qini_curve(random, t, y)
    for curve in (best, blind):
        assert curve["share"][0] == 0.0 and curve["qini"][0] == 0.0 and curve["random"][0] == 0.0
        assert curve["share"][-1] == 1.0 and curve["qini"][-1] == pytest.approx(curve["random"][-1])
    # Contacting everyone is the same act whatever the order, so both curves end at one point.
    assert best["qini"][-1] == pytest.approx(blind["qini"][-1])
    lifts = uplift_curve(perfect, t, y), uplift_curve(random, t, y)
    assert lifts[0]["uplift"][-1] == pytest.approx(lifts[1]["uplift"][-1])
    assert lifts[0]["uplift"][-1] == pytest.approx(y[t == 1].mean() - y[t == 0].mean())


# 2. The operating point and the guard on the test split


def test_the_chosen_share_is_interior_on_a_hill_and_degenerate_on_a_monotone_curve() -> None:
    hill = _hand_curve([10, 30, 55, 70, 62, 40, 20])
    share = choose_share(hill)
    assert share == pytest.approx(0.4)
    assert interior_test(hill, share)[0]

    rising = _hand_curve([10, 20, 30, 40, 50])
    share = choose_share(rising)
    passed, reason = interior_test(rising, share)
    assert share == pytest.approx(0.5) and not passed and "largest" in reason

    falling = _hand_curve([50, 40, 30, 20, 10])
    share = choose_share(falling)
    passed, reason = interior_test(falling, share)
    assert share == pytest.approx(0.1) and not passed and "smallest" in reason

    flat_top = _hand_curve([10, 40, 40, 20])
    passed, reason = interior_test(flat_top, choose_share(flat_top))
    assert not passed and "flat" in reason


def test_the_share_is_never_chosen_on_the_test_split() -> None:
    assert chosen_on("validation") == "validation"
    with pytest.raises(ValueError, match="validation"):
        chosen_on("test")
    with pytest.raises(ValueError):
        chosen_on("train")
    with pytest.raises(ValueError, match="validation"):
        choose_share(_hand_curve([10, 30, 20], split="test"))


# 3. The value at the chosen share comes from the test split


@pytest.mark.lightgbm
def test_the_value_at_the_chosen_share_is_reported_from_the_test_split(protocol: ProtocolResult) -> None:
    curves = protocol.policy_value
    moved = 0
    for p in protocol.policies:
        assert p.chosen_on == "validation"
        assert p.value_validation.split == "validation"
        assert p.value_test.split == "test"
        assert p.value_test.share == p.chosen_share == p.value_validation.share

        def at(split: str, policy: str = p.policy, share: float = p.chosen_share) -> float:
            row = curves.filter(
                (pl.col("policy") == policy) & (pl.col("split") == split) & (pl.col("share") == share)
            )
            return float(row["profit_per_thousand"].item())

        assert p.value_test.profit_per_thousand == pytest.approx(at("test"))
        assert p.value_validation.profit_per_thousand == pytest.approx(at("validation"))
        moved += at("test") != at("validation")
        if p.policy != "everyone":
            # The share is the best one on validation, whatever the test split would have preferred.
            validation = curves.filter((pl.col("policy") == p.policy) & (pl.col("split") == "validation"))
            best = validation.sort("profit_per_thousand", descending=True, nulls_last=True)["share"][0]
            assert p.chosen_share == best
    # The two splits give different numbers, so reading the right one is a real check.
    assert moved > 0
    assert protocol.policy("everyone").chosen_share == 1.0
    assert not protocol.policy("everyone").interior.interior


# 4. Known truth measures


def test_pehe_regret_and_quadrant_shares_on_known_truth(customers: pl.DataFrame) -> None:
    tau = customers["tau"].to_numpy()
    assert pehe(tau, tau) == 0.0
    assert pehe(tau + 0.1, tau) == pytest.approx(0.1)
    assert pehe(np.zeros_like(tau), tau) > 0

    y0, y1 = customers["y0"].to_numpy(), customers["y1"].to_numpy()
    quadrant = _quadrants(customers)
    sleeping_dogs = int((quadrant == "sleeping_dog").sum())
    assert sleeping_dogs > 0
    oracle = (y0 == 0) & (y1 == 1)
    assert oracle_regret(oracle, y0, y1) == 0
    everyone = np.ones(customers.height, dtype=bool)
    assert oracle_regret(everyone, y0, y1) == sleeping_dogs
    assert oracle_regret(~everyone, y0, y1) == int(oracle.sum())

    mask = np.random.default_rng(5).random(customers.height) < 0.4
    contacted = quadrant_shares_contacted(mask, quadrant)
    left_alone = quadrant_shares_contacted(~mask, quadrant)
    for q, share in contacted.items():
        assert 0.0 <= share <= 1.0
        assert share + left_alone[q] == pytest.approx(1.0)
    assert quadrant_shares_contacted(oracle, quadrant)["persuadable"] == 1.0
    assert quadrant_shares_contacted(oracle, quadrant)["sleeping_dog"] == 0.0


# 5. The learners find the planted effect


@pytest.mark.lightgbm
def test_t_and_x_learners_recover_the_planted_uplift(customers: pl.DataFrame) -> None:
    split = split_customers(customers, "customer_id", seed=7)
    train = split.filter(pl.col("split") == "train")
    test = split.filter(pl.col("split") == "test")
    truth = test["tau"].to_numpy()
    for learner in (TLearner(FEATURES, seed=7), XLearner(FEATURES, seed=7)):
        learner.fit(train, train["treated"], train["converted"])
        predicted = learner.predict_uplift(test)
        assert np.corrcoef(predicted, truth)[0, 1] > 0.3, learner.name
    with pytest.raises(ValueError, match="both arms"):
        TLearner(FEATURES, seed=7).fit(train, np.ones(train.height), train["converted"])


# 6. The split


def test_the_split_sorts_before_it_draws(customers: pl.DataFrame) -> None:
    frame = customers.select("customer_id", "x0")
    first = split_customers(frame, "customer_id", seed=7)
    shuffled = split_customers(frame.sample(fraction=1.0, shuffle=True, seed=1), "customer_id", seed=7)
    assert first.select("customer_id", "split").equals(shuffled.select("customer_id", "split"))
    shares = first["split"].value_counts(normalize=True).sort("split")
    assert dict(zip(shares["split"], shares["proportion"], strict=True)) == pytest.approx(
        {"test": 0.2, "train": 0.6, "validation": 0.2}, abs=0.02
    )
    with pytest.raises(ValueError, match="unique"):
        split_customers(pl.concat([frame, frame.head(1)]), "customer_id", seed=7)


# 7. The paired bootstrap


def test_the_paired_bootstrap_interval_contains_the_point_estimate(customers: pl.DataFrame) -> None:
    t = customers["treated"].to_numpy()
    y = customers["converted"].to_numpy()
    keys = customers["customer_id"].to_numpy()
    r = np.random.default_rng(13)
    scores = {
        "perfect": customers["tau"].to_numpy(),
        "noisy": customers["tau"].to_numpy() + r.normal(0.0, 0.1, customers.height),
        "random": r.random(customers.height),
        "everyone": np.zeros(customers.height),
    }
    boot = paired_bootstrap_qini(scores, t, y, keys, seed=7)
    for name, interval in boot.coefficients.items():
        assert interval.replicates == 200 and interval.level == pytest.approx(0.90)
        assert interval.lower <= interval.estimate <= interval.upper, name
        assert interval.estimate == pytest.approx(qini_coefficient(scores[name], t, y))
    for difference in boot.differences:
        assert difference.interval.lower <= difference.interval.estimate <= difference.interval.upper
    perfect_vs_random = next(d for d in boot.differences if (d.first, d.second) == ("perfect", "random"))
    assert perfect_vs_random.interval.lower > 0
    assert boot.curves.height == 4 * 101

    # Sorting on the key before the draw: the same customers in another order, the same intervals.
    order = r.permutation(customers.height)
    again = paired_bootstrap_qini(
        {k: v[order] for k, v in scores.items()}, t[order], y[order], keys[order], seed=7
    )
    assert again.coefficients == boot.coefficients


def test_policy_value_curve_prices_the_contacted_and_sums_over_the_list(customers: pl.DataFrame) -> None:
    t = customers["treated"].to_numpy()
    y = customers["converted"].to_numpy()
    spend = customers["spend"].to_numpy()
    curve = policy_value_curve(np.zeros(customers.height), t, y, spend, SHARE_GRID, 0.30, 0.12, split="test")
    lift = spend[t == 1].mean() - spend[t == 0].mean()
    per_contact = 1000.0 * (lift * 0.30 - 0.12)
    # A constant score contacts a random slice at every share: the value per contact is flat and
    # the value per thousand on the list grows in proportion to the share contacted.
    assert curve["profit_per_thousand_contacted"].to_numpy() == pytest.approx(
        np.full(len(SHARE_GRID), per_contact)
    )
    assert curve["profit_per_thousand"].to_numpy() == pytest.approx(np.asarray(SHARE_GRID) * per_contact)
    assert set(curve["split"]) == {"test"}
