# Definitions, and the measurement policy behind them

Rendered from `results/manifest.json` by the claim gate. Every constant quoted here is
read from `marginal_core.config.POLICY`; a change to the policy is a change to this
document, and a DECISIONS entry goes with it.

This document is a policy, not a glossary. It says what counts as incremental, what
margin is used, what the lifetime value horizon is, what a plan may not do, and why.
Where a definition has SQL, the query runs over the marts under `results/marts`
(DuckDB views over the committed parquet), and the code reference is the function that
produced the published figure.

## Sales

**Baseline sales** are the sales the market would have produced with every paid channel
at zero: organic demand with its seasonality, trend, holidays, price and promotion effects.
**Incremental sales** are everything above that. On the demonstration brand both are known
from the simulator's truth table (`packages/sim`, `truth_contributions.parquet`); on the
mix model they are estimated, and the estimate is shown beside the truth wherever the truth
is known.

```sql
select week, sum(baseline) as baseline, sum(incremental) as incremental
from truth_contributions group by week order by week;
```

**Contribution** of a channel in a week is the incremental sales the model assigns to it
(`marginal_mmm.interface.contributions`). Contributions and baseline sum to modeled sales;
the residual, the part of actual sales the decomposition does not explain, is published as a
share of sales rather than folded into the baseline.

## Returns

**Return on ad spend** is incremental revenue per dollar of spend over the fit window.
**Return on investment** is incremental profit per dollar at the contribution margin of
42%, so a channel with a return on ad spend below
2.38 loses money at the margin used here.

**Marginal return** is the slope of a channel's response curve at its current spend: the
incremental revenue the next dollar earns (`marginal_mmm.interface.marginal_return`). The
budget optimizer moves money until marginal returns are equal across every channel that is
not at a bound; the average return per dollar plays no part in the plan, because a channel
can have a high average and a low margin at the same time, and it is the margin the next
dollar sees.

## Carryover and saturation

**Carryover** is geometric adstock: a dollar spent this week keeps a share theta of its
effect next week, theta squared the week after, and so on. The **half life** is the number
of weeks until that share is one half, log(0.5) / log(theta). **Saturation** is a Hill
curve, x^s / (k^s + x^s), where k is the **half saturation point**, the adstocked spend at
which the channel delivers half of its ceiling, and s is the slope. The `own` backend
searches theta, k and s per channel; the `bayes` backend places priors on them.

## Experiments

**Lift** is the difference in an outcome between treated and control units in a randomized
or quasi randomized test. **Incrementality** is lift expressed as the share of the treated
outcome the treatment caused. A lift test's estimate carries a stated interval and, on the
simulator, is shown beside the true lift from the truth table.

Every experiment is **pre-registered**: its design (units, assignment rule, channel, spend
change, window, primary outcome, analysis plan) is hashed with the design hash ported from
readout (`marginal_core.hashing.design_hash`) and registered through `POST /v1/experiments`
before its data is analyzed. A result cannot be posted to an experiment without a plan hash,
and changing the design after registration changes the hash and is rejected.

The **SRM gate** (sample ratio mismatch) is a chi square test of the observed assignment
counts against the planned ratio; no result is shown while it fails at p below 0.001, and the
gate refuses to pass on an empty assignment.

## Uplift and targeting

**Uplift** is the conditional average treatment effect: the change in the outcome the
treatment causes for a customer with given features. The **four quadrants** are the
persuadables (convert only if treated), the sure things (convert either way), the lost
causes (convert neither way) and the sleeping dogs (convert only if left alone); a
targeting policy earns money on persuadables, wastes it on sure things and lost causes, and
loses it on sleeping dogs.

**Qini** is the cumulative incremental outcome as a share of the population is contacted in
descending order of predicted uplift, against the random diagonal; the Qini coefficient is
the area between the two. **Policy value per thousand contacts** is expected incremental
profit per thousand customers contacted at a stated cost per contact. On Hillstrom the cost
per email is $0.12 and the margin on the spend the email
causes is 30%; the share contacted is chosen on the
validation split and reported on the test split, and the choice must be strictly interior,
with the curve lower on both sides, or the page says the operating point is degenerate.

## Lifetime value

**Lifetime value** is the expected discounted revenue from a customer over the next
12 months at an annual discount rate of
10%, from a BG/NBD purchase frequency model and a
Gamma-Gamma monetary value model fit on the calibration window and checked on the holdout
by frequency decile before either is used. The **acquisition cost allowance** is lifetime
value times the contribution margin times a payback share of 70%:
the most a channel may spend to acquire a customer of that segment. The retail transactions
are a UK online gift retailer's, largely wholesale customers, from 2009 to 2011, and the
demonstration brand's market is simulated, so the allowance demonstrates the mechanism and
is not a number for the brand.

## Plans

A **plan** is an allocation of a stated total budget across the seven channels with the
model version, the spec hash, the inputs' hash, the expected incremental profit and its
interval stored beside it, so a review months later can ask what the model said and why.
A plan may not move any channel by more than 30% of
last year's spend, may not take a channel below 25% or above
200% of last year's spend, and may not imply an acquisition
cost above the allowance. The optimizer is SLSQP from 8
starting points with the solver status recorded, and a plan is published only when marginal
returns are equal within tolerance across every channel that is not at a bound.

## Attribution

Attribution rules (last touch, first touch, linear, position based, time decay, Shapley)
allocate credit for a conversion across the touches on its path. They are reporting
conventions, not measurements of cause: a rule cannot see what would have happened without
a touch. On the simulated paths every rule is shown beside the true incremental credit, and
the channel that touches people who were about to convert anyway (display and retargeting,
by construction here and in most real markets) is the one every rule over credits.

## The numbers behind the words

- Interval level everywhere: 90%.
- Block bootstrap: 200 replicates of 8 week blocks.
- Rolling origin validation: 4 origins.
- Placebo permutations for synthetic control: 200.
- Recovery study seeds: 20 per condition for `own`, 3 for `bayes`.
- Lift test: Display and retargeting, spend change -100.0% in the treated geos,
  8 weeks after a 52 week pre period.
- Channels, in the fixed order the palette follows: Paid search, Paid social, Online video, Display and retargeting, Email, Affiliate and promo codes, Direct mail.

> Alderquist is a fictional direct to consumer home goods brand and its market is simulated with known truth. The email experiment is Kevin Hillstrom's public 2008 dataset, the purchase history is the UCI Online Retail II dataset, and the large uplift set is Criteo's public research release. No real company's spend and no real customer's identity appears here.
