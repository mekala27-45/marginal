"""Attribution: the six rules hand out exactly the conversions, Shapley is exact and efficient,
a one channel path set gives that channel all the credit, and the grade against the truth
names the channel every rule over credits."""

from __future__ import annotations

import math

import numpy as np
import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from marginal_attribution import (
    COALITIONS,
    RULES,
    coalition_table,
    comparison,
    converting_touches,
    credit_by_channel,
    credit_table,
    grade,
    model_share,
    over_credit,
    path_channel_sets,
    shapley,
    shapley_credit,
    touch_weights,
)
from marginal_core.config import CHANNELS, POLICY
from marginal_mmm import CurveParams, ModelExport
from marginal_sim import PathSpec
from marginal_sim.paths import simulate_paths


def _paths(rows: list[tuple[int, list[str], int]]) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Build a touch table and a users table from (user, channels in order, converted)."""
    touches = []
    users = []
    for user, channels, converted in rows:
        n = len(channels)
        for position, channel in enumerate(channels):
            touches.append(
                {
                    "user_id": user,
                    "position": position,
                    "channel": channel,
                    "days_before_end": float(n - 1 - position) * 3.0,
                    "touch_effect_true": 0.05,
                    "credit_true": 0.05,
                }
            )
        users.append(
            {
                "user_id": user,
                "intent_true": 0.0,
                "p_base_true": 0.04,
                "p_convert_true": 0.1,
                "converted": converted,
                "touches": n,
            }
        )
    return pl.DataFrame(touches), pl.DataFrame(users)


def _model() -> ModelExport:
    channels = [
        CurveParams(
            channel=c,
            ceiling=100_000.0 * (i + 1),
            half_saturation=50_000.0,
            slope=1.2,
            carryover=0.3,
            weekly_spend_current=50_000.0,
            spend_last_year=50_000.0,
            ceiling_draws=[],
        )
        for i, c in enumerate(CHANNELS)
    ]
    return ModelExport(
        backend="own",
        spec_hash="test",
        data_source="simulated",
        calibrated=True,
        version="test",
        channels=channels,
    )


@pytest.fixture(scope="module")
def simulated() -> tuple[pl.DataFrame, pl.DataFrame]:
    return simulate_paths(PathSpec(seed=3, users=4_000))


def test_every_rule_hands_out_exactly_the_conversions(simulated: tuple[pl.DataFrame, pl.DataFrame]) -> None:
    touches, users = simulated
    conversions = float(users["converted"].sum())
    table, _ = credit_table(touches, users)
    for rule in RULES:
        assert float(table[f"credit_{rule}"].sum()) == pytest.approx(conversions)
        assert float(table[f"share_{rule}"].sum()) == pytest.approx(1.0)
    assert table["channel"].to_list() == list(CHANNELS)


def test_weights_sum_to_one_per_path_under_every_rule(simulated: tuple[pl.DataFrame, pl.DataFrame]) -> None:
    touches, users = simulated
    frame = converting_touches(touches, users)
    for rule in RULES:
        if rule == "shapley":
            continue
        weighted = frame.with_columns(touch_weights(frame, rule))
        per_path = weighted.group_by("user_id").agg(pl.col("weight").sum())["weight"].to_numpy()
        assert np.allclose(per_path, 1.0)


def test_the_rules_credit_the_positions_they_are_named_for() -> None:
    touches, users = _paths([(0, ["email", "paid_social", "online_video", "paid_search"], 1)])
    frame = converting_touches(touches, users)
    last = credit_by_channel(frame, "last_touch")
    first = credit_by_channel(frame, "first_touch")
    linear = credit_by_channel(frame, "linear")
    position = credit_by_channel(frame, "position_based")
    decay = credit_by_channel(frame, "time_decay")

    def credit(table: pl.DataFrame, channel: str) -> float:
        return float(table.filter(pl.col("channel") == channel)["credit"][0])

    assert credit(last, "paid_search") == 1.0 and credit(last, "email") == 0.0
    assert credit(first, "email") == 1.0 and credit(first, "paid_search") == 0.0
    assert credit(linear, "email") == pytest.approx(0.25)
    assert credit(position, "email") == pytest.approx(POLICY.attribution_position_first)
    assert credit(position, "paid_search") == pytest.approx(POLICY.attribution_position_last)
    assert credit(position, "paid_social") == pytest.approx(
        (1.0 - POLICY.attribution_position_first - POLICY.attribution_position_last) / 2
    )
    # Time decay: the last touch (zero days before the end) weighs most; nine days before, at a
    # seven day half life, the first touch weighs 2 ** (-9 / 7) of it.
    ratio = credit(decay, "email") / credit(decay, "paid_search")
    assert ratio == pytest.approx(2.0 ** (-9.0 / POLICY.attribution_half_life_days))
    assert (
        credit(decay, "paid_search")
        > credit(decay, "online_video")
        > credit(decay, "paid_social")
        > credit(decay, "email")
    )


def test_position_based_on_short_paths() -> None:
    touches, users = _paths([(0, ["email"], 1), (1, ["email", "direct_mail"], 1)])
    frame = converting_touches(touches, users)
    weights = touch_weights(frame, "position_based").to_list()
    assert weights == pytest.approx([1.0, 0.5, 0.5])


def test_a_non_converting_path_earns_nothing() -> None:
    touches, users = _paths([(0, ["email"], 0), (1, ["direct_mail"], 1)])
    table, _ = credit_table(touches, users)
    row = {r["channel"]: r for r in table.iter_rows(named=True)}
    for rule in RULES:
        assert row["email"][f"credit_{rule}"] == pytest.approx(0.0)
        assert row["direct_mail"][f"credit_{rule}"] == pytest.approx(1.0)


def test_shapley_on_a_single_channel_path_set_gives_that_channel_all_the_credit() -> None:
    touches, users = _paths([(i, ["email"] * (1 + i % 3), 1 if i % 4 else 0) for i in range(40)])
    credit, coalitions = shapley(touches, users)
    conversions = float(users["converted"].sum())
    by_channel = dict(zip(credit["channel"].to_list(), credit["credit"].to_list(), strict=True))
    assert by_channel["email"] == pytest.approx(conversions)
    for channel in CHANNELS:
        if channel != "email":
            assert by_channel[channel] == pytest.approx(0.0)
    assert coalitions.height == COALITIONS == 128
    assert int((coalitions["paths_exact"] > 0).sum()) == 1


def test_shapley_is_exact_and_symmetric_on_a_two_channel_game() -> None:
    # Two channels that only ever convert together: equal split by symmetry. A channel that
    # converts alone as often as the pair does earns the extra alone.
    touches, users = _paths(
        [
            (0, ["email", "direct_mail"], 1),
            (1, ["direct_mail", "email"], 1),
            (2, ["email"], 1),
            (3, ["direct_mail"], 0),
        ]
    )
    credit, _ = shapley(touches, users)
    by_channel = dict(zip(credit["channel"].to_list(), credit["credit"].to_list(), strict=True))
    # Worths: {email} = 1, {direct_mail} = 0, {email, direct_mail} = 3.
    # email: 1/2 * (1 - 0) + 1/2 * (3 - 0) = 2; direct_mail: 1/2 * 0 + 1/2 * (3 - 1) = 1.
    assert by_channel["email"] == pytest.approx(2.0)
    assert by_channel["direct_mail"] == pytest.approx(1.0)
    assert sum(by_channel.values()) == pytest.approx(3.0)


@settings(max_examples=25, deadline=None)
@given(
    st.lists(
        st.tuples(st.lists(st.sampled_from(CHANNELS), min_size=1, max_size=5), st.integers(0, 1)),
        min_size=1,
        max_size=40,
    )
)
def test_shapley_credit_sums_to_the_conversion_count(rows: list[tuple[list[str], int]]) -> None:
    touches, users = _paths([(i, channels, converted) for i, (channels, converted) in enumerate(rows)])
    credit, coalitions = shapley(touches, users)
    assert float(credit["credit"].sum()) == pytest.approx(float(users["converted"].sum()))
    assert float(credit["credit"].min()) >= -1e-9
    assert int(coalitions.sort("mask")["worth"][-1]) == int(users["converted"].sum())


def test_coalition_worth_is_monotone_in_the_coalition(simulated: tuple[pl.DataFrame, pl.DataFrame]) -> None:
    touches, users = simulated
    coalitions = coalition_table(path_channel_sets(touches, users)).sort("mask")
    worth = coalitions["worth"].to_numpy()
    for mask in range(COALITIONS):
        for i in range(len(CHANNELS)):
            if not mask >> i & 1:
                assert worth[mask | 1 << i] >= worth[mask]
    assert worth[0] == 0
    assert worth[-1] == int(users["converted"].sum())
    assert float(shapley_credit(coalitions)["credit"].sum()) == pytest.approx(float(worth[-1]))


def test_model_share_sums_to_one_and_follows_the_ceilings() -> None:
    share = model_share(_model())
    assert float(share["share_model"].sum()) == pytest.approx(1.0)
    values = share["share_model"].to_list()
    assert values == sorted(values)


def test_the_grade_names_the_over_credited_channel(simulated: tuple[pl.DataFrame, pl.DataFrame]) -> None:
    touches, users = simulated
    table, _ = comparison(touches, users, _model())
    grades = grade(table)
    assert [g.rule for g in grades] == list(RULES)
    for g in grades:
        assert g.mean_abs_error_points >= 0.0
        assert g.max_abs_error_points >= g.mean_abs_error_points
        assert -1.0 <= g.rank_agreement <= 1.0
        assert g.over_credits_most == "display_retargeting"
        assert g.over_credit_points > 5.0
        assert g.over_credit_ratio > 1.5
    share, truth, points = over_credit(table, "last_touch", "display_retargeting")
    assert points == pytest.approx((share - truth) * 100.0)
    assert share > truth


def test_the_grade_is_zero_when_a_rule_matches_the_truth() -> None:
    table = pl.DataFrame(
        {
            "channel": list(CHANNELS),
            **{f"share_{rule}": [1.0 / len(CHANNELS)] * len(CHANNELS) for rule in RULES},
            "share_true": [1.0 / len(CHANNELS)] * len(CHANNELS),
        }
    )
    for g in grade(table):
        assert g.mean_abs_error_points == pytest.approx(0.0)
        assert math.isclose(g.over_credit_points, 0.0, abs_tol=1e-9)
