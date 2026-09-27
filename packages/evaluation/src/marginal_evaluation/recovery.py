"""The recovery study: fit a backend on markets where the truth is known, many seeds, six
conditions, and report how wrong it was.

The runner never grades a model by asking the model. It simulates a market, hands the
backend only what an analyst would see (sales, spend, price, promotion, holiday), and
compares what came back with the truth table: bias of the return estimate, median
absolute error, interval coverage against the nominal level, and whether the estimated
ranking of channels by marginal return agrees with the true ranking, which is what the
optimizer needs.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
import polars as pl
from marginal_core.config import CHANNELS
from marginal_core.model import StrictModel
from marginal_sim import MarketSpec, condition_name, national_truth_table, simulate_market

from marginal_evaluation.stats import bootstrap_interval, spearman

OBSERVED_COLUMNS = ("week", "week_start", "sales", "price_index", "promo", "holiday")


class ChannelEstimate(StrictModel):
    channel: str
    roas: float
    roas_lower: float
    roas_upper: float
    marginal_return: float
    carryover: float | None = None


class FitResult(StrictModel):
    backend: str
    channels: list[ChannelEstimate]
    diagnostics: dict[str, float | int | str]


FitFn = Callable[[pl.DataFrame, int], FitResult]


def observed(national: pl.DataFrame) -> pl.DataFrame:
    """The columns an analyst sees. No truth column ever reaches a backend."""
    keep = [*OBSERVED_COLUMNS, *[f"spend_{c}" for c in CHANNELS]]
    return national.select(keep)


class RecoveryRow(StrictModel):
    backend: str
    condition: str
    rho: float
    feedback: bool
    seed: int
    channel: str
    roas_estimate: float
    roas_lower: float
    roas_upper: float
    roas_true: float
    marginal_estimate: float
    marginal_true: float
    relative_error: float
    covered: bool


def run_recovery(
    fit: FitFn,
    backend: str,
    conditions: Sequence[tuple[float, bool]],
    seeds: int,
    *,
    first_seed: int = 1000,
    progress: Callable[[str], None] | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame, list[dict[str, float | int | str]]]:
    """Returns per seed rows, per seed rank agreement, and every fit's diagnostics."""
    rows: list[dict[str, object]] = []
    ranks: list[dict[str, object]] = []
    diagnostics: list[dict[str, float | int | str]] = []
    for rho, feedback in conditions:
        name = condition_name(rho, feedback)
        for i in range(seeds):
            seed = first_seed + i
            spec = MarketSpec(seed=seed, spend_correlation=rho, demand_feedback=feedback)
            _, national, market = simulate_market(spec)
            truth = national_truth_table(national, market)
            result = fit(observed(national), seed)
            if progress:
                progress(f"{backend} {name} seed {seed}")
            diagnostics.append({"condition": name, "seed": seed, **result.diagnostics})
            by_channel = {c.channel: c for c in result.channels}
            est_marginal = []
            true_marginal = []
            for r in truth.iter_rows(named=True):
                ch = str(r["channel"])
                est = by_channel[ch]
                roas_true = float(r["roas_true"])
                rows.append(
                    RecoveryRow(
                        backend=backend,
                        condition=name,
                        rho=rho,
                        feedback=feedback,
                        seed=seed,
                        channel=ch,
                        roas_estimate=est.roas,
                        roas_lower=est.roas_lower,
                        roas_upper=est.roas_upper,
                        roas_true=roas_true,
                        marginal_estimate=est.marginal_return,
                        marginal_true=float(r["marginal_return_true"]),
                        relative_error=(est.roas - roas_true) / roas_true,
                        covered=est.roas_lower <= roas_true <= est.roas_upper,
                    ).model_dump()
                )
                est_marginal.append(est.marginal_return)
                true_marginal.append(float(r["marginal_return_true"]))
            ranks.append(
                {
                    "backend": backend,
                    "condition": name,
                    "rho": rho,
                    "feedback": feedback,
                    "seed": seed,
                    "rank_agreement": spearman(est_marginal, true_marginal),
                }
            )
    return pl.DataFrame(rows), pl.DataFrame(ranks), diagnostics


def summarise(rows: pl.DataFrame, ranks: pl.DataFrame, *, level: float = 0.90, seed: int = 0) -> pl.DataFrame:
    """Per condition and channel: bias, median absolute error and coverage, each with an interval
    over seeds; plus one row per condition for the rank agreement (channel 'all')."""
    out: list[dict[str, object]] = []
    for (condition,), group in rows.group_by(["condition"], maintain_order=True):
        rho = float(group["rho"][0])
        feedback = bool(group["feedback"][0])
        n_seeds = group["seed"].n_unique()
        for channel in CHANNELS:
            sub = group.filter(pl.col("channel") == channel).sort("seed")
            errors = sub["relative_error"].to_numpy()
            bias = bootstrap_interval(errors, level=level, seed=seed, stream=f"bias {condition} {channel}")
            mae = bootstrap_interval(
                np.abs(errors),
                lambda x: float(np.median(x)),
                level=level,
                seed=seed,
                stream=f"mae {condition} {channel}",
            )
            cov = bootstrap_interval(
                sub["covered"].cast(pl.Float64).to_numpy(),
                level=level,
                seed=seed,
                stream=f"cov {condition} {channel}",
            )
            out.append(
                {
                    "backend": str(group["backend"][0]),
                    "condition": str(condition),
                    "rho": rho,
                    "feedback": feedback,
                    "channel": channel,
                    "seeds": n_seeds,
                    "bias": bias.estimate,
                    "bias_lower": bias.lower,
                    "bias_upper": bias.upper,
                    "median_abs_error": mae.estimate,
                    "median_abs_error_lower": mae.lower,
                    "median_abs_error_upper": mae.upper,
                    "coverage": cov.estimate,
                    "coverage_lower": cov.lower,
                    "coverage_upper": cov.upper,
                    "nominal_coverage": level,
                }
            )
        r = ranks.filter(pl.col("condition") == condition).sort("seed")["rank_agreement"].to_numpy()
        agreement = bootstrap_interval(r, level=level, seed=seed, stream=f"rank {condition}")
        out.append(
            {
                "backend": str(group["backend"][0]),
                "condition": str(condition),
                "rho": rho,
                "feedback": feedback,
                "channel": "all",
                "seeds": n_seeds,
                "bias": None,
                "bias_lower": None,
                "bias_upper": None,
                "median_abs_error": float(np.median(np.abs(group["relative_error"].to_numpy()))),
                "median_abs_error_lower": None,
                "median_abs_error_upper": None,
                "coverage": float(group["covered"].cast(pl.Float64).mean()),  # type: ignore[arg-type]
                "coverage_lower": None,
                "coverage_upper": None,
                "nominal_coverage": level,
                "rank_agreement": agreement.estimate,
                "rank_agreement_lower": agreement.lower,
                "rank_agreement_upper": agreement.upper,
            }
        )
    return pl.DataFrame(out)


def floor_crossing(summary: pl.DataFrame, floor: float) -> list[str]:
    """The conditions under which the median absolute error over every channel crosses the floor."""
    crossed = summary.filter((pl.col("channel") == "all") & (pl.col("median_abs_error") > floor))
    return [str(c) for c in crossed["condition"].to_list()]
