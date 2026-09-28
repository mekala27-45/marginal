# The budget optimizer

Rendered from `results/manifest.json` by the claim gate; do not edit by hand.

The optimizer answers one question: given a weekly budget, how should it be split across the
7 channels so that the next dollar earns the same everywhere it is free to
go. It reads fitted response curves, never raw data, and it runs in the pipeline (`make budget`)
and live behind the API (`/v1/optimize`, `/v1/plans`) on the same code (`marginal_budget`).

## The objective

Maximize expected incremental profit: the contribution margin of 42%
times the incremental revenue the curves predict at each channel's spend, less the spend, summed over
channels, at a stated total. Average return plays no part. A channel can have a high average return
and a low marginal one at the same time, and it is the margin the next dollar sees.

## The constraints

- **Floors and ceilings.** No channel below 25% or above
  200% of last year's spend.
- **The change limit.** No channel moves by more than 30% of last
  year's spend in one plan. With these values the change limit is always the
  tighter bound: every channel's spend stays within 30% of last
  year's, and the floor and ceiling never bind.
- **The acquisition cost allowance.** A channel's spend per acquired customer may not exceed its
  allowance from the lifetime value model, where customers are the channel's incremental revenue
  divided by the revenue one acquisition brings ($443.24). A channel
  whose curve cannot meet its allowance anywhere in its admissible range is held at the lowest spend
  it is allowed and labelled "allowance (infeasible)", rather than failing the plan.
- **The total.** The allocation spends exactly the stated budget, and a budget the bounds cannot
  meet is refused with the bounds named.

## The solver

SLSQP from 8 starting points, keeping the best feasible answer and
recording the solver's status. On the demonstration brand 8 of
8 starts converged, with the status "Optimization terminated successfully".

**The equalization check.** At an optimum the marginal profit is equal across every channel that is
not at a bound. The plan is published only when it is equal within tolerance; here it is
(yes), with a spread of 0.000 across the
2 interior channels.

**The interior test.** Budget is moved between every pair of interior channels, in both directions,
and each move must lower expected profit; otherwise the optimizer stopped on a bound or a flat spot
and the page says the plan is degenerate. This plan reads interior:
every reallocation between interior channels lowers expected profit.

## The plan on the demonstration brand

The calibrated own curves at last year's budget of $500,233 a week
($26,012,128 a year):

| Channel | Last year (weekly) | Plan (weekly) | Change | Expected revenue | Marginal return | Marginal profit | Bound |
|---|---:|---:|---:|---:|---:|---:|---|
| Paid search | $129,669 | $162,629 | +25.4% | $566,447 | 2.03 | -14.6% | interior |
| Paid social | $110,747 | $139,753 | +26.2% | $374,698 | 2.03 | -14.6% | interior |
| Online video | $63,969 | $44,778 | -30.0% | $22,804 | 0.84 | -64.6% | allowance (infeasible) |
| Display and retargeting | $82,854 | $57,998 | -30.0% | $95,908 | 1.03 | -56.9% | change limit |
| Email | $15,454 | $20,090 | +30.0% | $129,901 | 2.79 | +17.3% | change limit |
| Affiliate and promo codes | $40,330 | $34,939 | -13.4% | $36,800 | 1.68 | -29.3% | allowance |
| Direct mail | $57,210 | $40,047 | -30.0% | $33,475 | 0.85 | -64.2% | change limit |

Source: simulated, model optimizer, demonstration brand, calibrated own curves, condition rho 0.6, feedback on, seed 12, as of 2026-09-27.

Online video is held by its allowance of $517.73, which its
curve cannot meet at any admissible spend, so it sits at -30.0% from
last year.

Every plan evaluated on the simulator's true curves:

| Plan | True weekly profit | Gain over last year (weekly) | Gain over last year (annual) |
|---|---:|---:|---:|
| Calibrated model's plan | $36,354 | $18,334 | $953,345 |
| Uncalibrated model's plan | $30,862 | $12,842 | $667,778 |
| Truth optimal plan | $38,872 | $20,852 | $1,084,278 |
| Last year's mix | $18,020 | $0 | $0 |
| Equal split | -$56,079 | -$74,100 | -$3,853,187 |

Source: simulated, model optimizer, demonstration brand, calibrated own curves, condition rho 0.6, feedback on, seed 12, as of 2026-09-27.

## The two headline numbers

**The gain from reallocating the same budget:** $953,345 a
year over last year's mix, $18,334 a week, judged on the
true curves. **The share of the truth optimal gain captured:** 88%
for the calibrated plan and 62% for the uncalibrated
one, against the truth optimal plan's $1,084,278 a year. Both come
from one simulated market. The regret study below is the number to quote.

## The regret study

For each of 10 seeds of the demonstration condition the market is
simulated, the geo test is run on it, own is fit before and after calibration, each fit's plan is
optimized under the same constraints, and every plan is judged on that market's true curves. The
calibrated plan captured 67% of the truth optimal gain
(53% to 80%,
a bootstrap interval over seeds) and the uncalibrated plan 68%
(53% to 81%).
The two are within a point of each other: across markets, calibration did not buy a better budget
on average.
Against last year's mix, an equal split's weekly gain averages
-$76,541 across the same markets, which is why no plan here
starts from one.

| Model | Seeds | Share of optimal gain captured | Lower | Upper | Gain over last year (weekly) | Lower | Upper | Beats last year |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| uncalibrated | 10 | 68% | 53% | 81% | $12,250 | $9,646 | $14,730 | 90% |
| calibrated | 10 | 67% | 53% | 80% | $12,149 | $9,555 | $14,640 | 90% |

Source: simulated, model optimizer, markets with known truth, demonstration condition, condition rho 0.6, feedback on, 10 seeds, as of 2026-09-27.

## The surface behind the slider

The site's budget slider asks the live API for a plan at the chosen total. So that it still works
while the API is asleep, the pipeline solves a surface in advance: a grid over the total budget from
$300,140 to $675,315 a week
(31 points), at the stated constraints and again with the change limit
tightened and loosened (`results/budget/surface.parquet`). The page labels answers from it
"precomputed".

## How a plan is stored

A plan is saved with what a review would need months later to ask what the model said and why:
the model version, the backend, the spec hash of the fit, an inputs hash over the model version, the
spec hash and every constraint, the total budget, the allocation, the expected profit with its
interval and level, the constraints themselves, whether the plan is degenerate, and a note. Through
the API it goes to the `plans` table with an audit row written before the response. The
demonstration plan's record:

| Field | Value |
|---|---|
| Model version | `own-0c071596-calibrated` |
| Spec hash | `0c07159692e406de` |
| Inputs hash | `aeacfc8e6e7cbdd1` |
| Expected weekly profit | $28,981 ($18,568 to $53,742, at 90%) |
| True weekly profit of the same plan | $36,354 |

Source: simulated, model optimizer, demonstration brand, calibrated own curves, condition rho 0.6, feedback on, seed 12, as of 2026-09-27.

The interval on expected profit holds the plan's true profit, though the point estimate sits
below it.

> Alderquist is a fictional direct to consumer home goods brand and its market is simulated with known truth. The email experiment is Kevin Hillstrom's public 2008 dataset, the purchase history is the UCI Online Retail II dataset, and the large uplift set is Criteo's public research release. No real company's spend and no real customer's identity appears here.
