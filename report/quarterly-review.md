# Alderquist quarterly marketing review

As of 2026-09-27. For the chief marketing officer, from marketing science. The simulated
weekly panel behind the mix model runs from 2023-10-02 to 2026-09-21.

Every figure below is a value or a table in `results/manifest.json`, rendered by the claim gate;
none is typed by hand. Alderquist's market is simulated with known truth, so each mix model figure
sits beside the answer it was trying to find, and each public dataset is named where it is used.

## The budget numbers

**Reallocating the same budget.** Moving last year's $500,233 a week between
the channels, without adding a dollar, gains $953,345 a
year over last year's mix on the demonstration brand, or $18,334
a week, judged on the simulator's true response curves. Across 10
simulated markets the same procedure gained $12,149 a week
($9,555 to $14,640, a
90% bootstrap interval over seeds) and beat last year's mix in
90% of them.

**The share of the available gain captured.** On the demonstration brand the calibrated plan
captures 88% of the gain the truth optimal plan makes, which is
$1,084,278 a year; the plan built on the uncalibrated model
captures 62%. Across the 10
markets the calibrated plan captured 67%
(53% to 80%)
and the uncalibrated plan 68%
(53% to 81%).

The demonstration figures come from one seed and the study is the honest number: across seeds the
calibrated and uncalibrated plans are within a point of each other, so calibration bought a better
estimate of the channel it tested, not a better budget on average.

The plan at last year's budget, week by week:

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

Paid search and paid social are the interior channels, and their marginal returns
are equal at the optimum (a spread of 0.000), which is the condition the
optimizer is built to meet. Every other channel sits at a bound: the change limit of
30% of last year's spend, or the acquisition cost allowance
from the lifetime value model (below).

At this total the marginal profit column is negative in the interior channels: the next dollar
there returns less than the breakeven return of 2.38 at a
42% margin. The plan says where last year's budget does the most;
it does not say that budget is the right size, and the budget page's slider is where a smaller
total can be tried against the same curves.

Every plan judged on the true curves, and the study across markets:

| Plan | True weekly profit | Gain over last year (weekly) | Gain over last year (annual) |
|---|---:|---:|---:|
| Calibrated model's plan | $36,354 | $18,334 | $953,345 |
| Uncalibrated model's plan | $30,862 | $12,842 | $667,778 |
| Truth optimal plan | $38,872 | $20,852 | $1,084,278 |
| Last year's mix | $18,020 | $0 | $0 |
| Equal split | -$56,079 | -$74,100 | -$3,853,187 |

Source: simulated, model optimizer, demonstration brand, calibrated own curves, condition rho 0.6, feedback on, seed 12, as of 2026-09-27.

| Model | Seeds | Share of optimal gain captured | Lower | Upper | Gain over last year (weekly) | Lower | Upper | Beats last year |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| uncalibrated | 10 | 68% | 53% | 81% | $12,250 | $9,646 | $14,730 | 90% |
| calibrated | 10 | 67% | 53% | 80% | $12,149 | $9,555 | $14,640 | 90% |

Source: simulated, model optimizer, markets with known truth, demonstration condition, condition rho 0.6, feedback on, 10 seeds, as of 2026-09-27.

## What the lift test said, and how it moved the model

**The design.** The test switched display and retargeting off in 10 of the
40 simulated geos for 8 weeks, weeks 148
to 155 of the panel (a spend change of -100.0%), with the other
30 geos as controls and the 52 weeks before it as the
pre period. Geos were assigned by a stratified draw across the size distribution. Power was
estimated by simulation, 60 runs for each candidate design; at the true
effect this design's power is 100%, and the smaller designs that were
considered are in `docs/experiments.md`. The design was hashed and registered before any of the
test's weeks were read: plan hash `53733a76fe1af6ec`, registered at 2026-09-27T21:45:07+00:00.
It was registered locally in this build, in `results/experiments/registry.json`, because the build
sandbox could not reach the live API; the same design and result were replayed to the live registry
from a separate client afterwards (replayed, experiment
`076102e0-ebd0-5218-8433-fab40b6cff08`, same plan hash: yes), which
`docs/serving.md` records as a replay, not a pre-registration. The sample ratio gate passed (p = 1.000).

**The result against the truth.** Difference in differences puts the revenue the channel caused in
the treated geos over the window at $169,063 ($151,588 to
$186,538). Synthetic control, fit on the pre period, puts it at $167,952
($131,871 to $206,046), and none of its
200 placebo assignments produced a gap as large (placebo p value
0.000). The truth, known only because the market is
simulated, is $150,478. The difference in differences interval
misses it and the synthetic control's
covers it.
Both estimates sit above the truth, by +12.4% and +11.6%.

| Method | Estimate | Lower | Upper | Truth (simulated) | Covers | Error |
|---|---:|---:|---:|---:|---|---:|
| Difference in differences | $169,063 | $151,588 | $186,538 | $150,478 | no | +12.4% |
| Synthetic control | $167,952 | $131,871 | $206,046 | $150,478 | yes | +11.6% |

Source: simulated, model did, 10 treated geos of 40, 8 weeks, condition rho 0.6, feedback on, seed 12, as of 2026-09-27.

**How it moved the model.** The difference in differences result was posted against its plan hash
($169,063, standard error $10,624) and taken into
both mix models: in own as a pseudo observation weighted by the experiment's precision, in bayes as
a lift test measurement. On the tested channel, own's return on ad spend went from
1.62 (1.18 to
1.92) to 1.31
(1.27 to 1.32), and bayes's from
2.26 (1.12 to
4.56) to 1.42
(1.25 to 1.59). The true
return is 1.22.
Both estimates moved toward the truth, and both intervals narrowed until neither covers it: before
calibration each interval held the true return, and after it each sits wholly above it. The
experiment's own estimate sits above the truth, and the calibrated models follow the experiment.
That is what calibration should do with a test it is told to trust; it is also why one test is not
enough.

|  | Before | After | Truth (simulated) |
|---|---:|---:|---:|
| Return on ad spend | 1.62 | 1.31 | 1.22 |
| Interval lower | 1.18 | 1.27 | not applicable |
| Interval upper | 1.92 | 1.32 | not applicable |
| Marginal return | 0.76 | 0.55 | 0.69 |

Source: simulated, model own, demonstration brand, condition rho 0.6, feedback on, seed 12, as of 2026-09-27.

|  | Before | After | Truth (simulated) |
|---|---:|---:|---:|
| Return on ad spend | 2.26 | 1.42 | 1.22 |
| Interval lower | 1.12 | 1.25 | not applicable |
| Interval upper | 4.56 | 1.59 | not applicable |
| Marginal return | 1.41 | 1.15 | 0.69 |

Source: simulated, model bayes, demonstration brand, condition rho 0.6, feedback on, seed 12, as of 2026-09-27.

The lift each model implies for the test's geos and weeks tells the same story: own implied
$212,748 before and $173,669 after, bayes
$319,342 and $170,634, against the
experiment's $169,063 and a true $150,478.

**Across markets.** One market is one draw.
Across 20 seeds of the demonstration condition, each with its own
geo test, calibration cut own's median absolute error on the tested channel from
36.1% to 15.2%
and across all channels from 36.4% to
27.9%, while interval coverage
stayed at 37%.
Bayes, on its 3 seeds, went from
57.8% to 14.7%
on the tested channel; with so few seeds that is a direction, not a measurement.

|  | Before | After |
|---|---:|---:|
| Median absolute error, all channels | 36.4% | 27.9% |
| Median absolute error, tested channel | 36.1% | 15.2% |
| Interval coverage, all channels | 37.1% | 37.1% |

Source: simulated, model own, markets with known truth, demonstration condition, condition rho 0.6, feedback on, 20 seeds, as of 2026-09-27.

|  | Before | After |
|---|---:|---:|
| Median absolute error, all channels | 17.7% | 14.7% |
| Median absolute error, tested channel | 57.8% | 14.7% |
| Interval coverage, all channels | 100.0% | 100.0% |

Source: simulated, model bayes, markets with known truth, demonstration condition, condition rho 0.6, feedback on, 3 seeds, as of 2026-09-27.

**The weight passed its interior test.** Refit with the experiment's weight halved, as stated and
doubled, the gap between the lift own implies and the lift the experiment found is
$9,299, $4,606 and
$1,553: the residual against the experiment shrinks as the weight grows and is not zero at the stated weight. At the stated weight
the data still has a say; the experiment does not simply overwrite the fit.

## The targeting result

**The email experiment.** Hillstrom's file is the one real randomized test in this build:
64,000 recent buyers of a catalog retailer in 2008, assigned in equal thirds
to no email (21,306), a men's merchandise email (21,307) or a
women's (21,387). The sample ratio gate passed (p = 0.904).
Over the 14 days after the send, the men's email raised the conversion rate
from 0.57% to 1.25%, a difference of
0.68% of customers (0.53% to
0.83%), and spend per customer from $0.65
to $1.42, a difference of $0.77
($0.53 to $1.01), with intervals at
90%. At a 30% margin on that spend and
$0.12 per email, each men's email sent earned $0.11
of incremental profit; the women's email earned $0.01.

| Arm | Outcome | No email | Email | Effect | Lower | Upper |
|---|---|---:|---:|---:|---:|---:|
| mens | visit | 0.1062 | 0.1828 | 0.0766 | 0.0710 | 0.0822 |
| mens | conversion | 0.0057 | 0.0125 | 0.0068 | 0.0053 | 0.0083 |
| mens | spend | 0.6528 | 1.4226 | 0.7698 | 0.5309 | 1.0087 |
| womens | visit | 0.1062 | 0.1514 | 0.0452 | 0.0399 | 0.0506 |
| womens | conversion | 0.0057 | 0.0088 | 0.0031 | 0.0018 | 0.0045 |
| womens | spend | 0.6528 | 1.0772 | 0.4244 | 0.2100 | 0.6388 |

Source: real:hillstrom, 64,000 recent buyers, three arms, as of 2026-09-27. Visit and conversion are rates as fractions of customers; spend is
dollars per customer.

Split by purchase history, the men's email effect on conversion stays significant in
6 of 7
segments once the p values are corrected by Benjamini-Hochberg across segments, and the effect on
spend in 5 of the same segments. The conversion family,
with each p value before and after the correction:

| History segment | Effect | Lower | Upper | p | p adjusted | Significant |
|---|---:|---:|---:|---:|---:|---|
| 1) $0 - $100 | 0.50% | 0.28% | 0.72% | 0.000 | 0.001 | yes |
| 2) $100 - $200 | 0.48% | 0.21% | 0.75% | 0.004 | 0.006 | yes |
| 3) $200 - $350 | 0.85% | 0.47% | 1.23% | 0.000 | 0.001 | yes |
| 4) $350 - $500 | 0.87% | 0.24% | 1.50% | 0.022 | 0.026 | yes |
| 5) $500 - $750 | 0.83% | 0.27% | 1.40% | 0.015 | 0.021 | yes |
| 6) $750 - $1,000 | 2.00% | 0.89% | 3.11% | 0.003 | 0.006 | yes |
| 7) $1,000 + | 0.93% | -0.58% | 2.44% | 0.312 | 0.312 | no |

Source: real:hillstrom, 64,000 recent buyers, three arms, as of 2026-09-27.

**Who to email.** Four policies were compared on the same customers: the T learner and the X
learner, uplift models that rank customers by how much the email changes their chance of buying;
the sure things rule, which emails the customers most likely to buy and is the rule most retailers
run; and everyone. The models were fit on 60% of customers; each policy
chose how many to contact on a 20% validation split and is reported
on the 20% test split, which took no part in either. On test, per thousand
customers on the list, the T learner earned $188
contacting 95.0%, the X learner
$180 at 85.0%,
the sure things rule $207 at
85.0%, and emailing everyone
$202.
The learners did not beat the sure things rule, or emailing everyone, on this test, and every Qini
interval includes zero: -0.109 (-1.197 to
0.941) for the T learner, -0.110
(-1.245 to 1.039) for the X learner and
0.191 (-0.716 to 1.214)
for the rule. On this data the build cannot tell the policies apart. Emailing everyone involves no
ranking at all, yet its value moves from $83 on
validation to $202 on test: that is the noise a split of
8,560 customers carries.

| Policy | Qini coefficient | Lower | Upper | Chosen share | Value on validation | Value on test |
|---|---:|---:|---:|---:|---:|---:|
| T learner | -0.109 | -1.197 | 0.941 | 95.0% | $87 | $188 |
| X learner | -0.110 | -1.245 | 1.039 | 85.0% | $106 | $180 |
| Sure things | 0.191 | -0.716 | 1.214 | 85.0% | $84 | $207 |
| Everyone | 0.000 | 0.000 | 0.000 | 100.0% | $83 | $202 |

Source: real:hillstrom, Hillstrom men's email against no email, test split of 8,560 customers (models fit on 25,470, shares chosen on 8,583); T and X learners, the sure things rule and everyone, as of 2026-09-27.

**Where the answer is known.** On 200,000 simulated customers under a randomized
email, where each customer's response with and without the email is known, the learners win
clearly. Their Qini coefficients are 8.924 (7.627
to 10.030) and 10.147 (8.848
to 11.252), against -1.290
(-2.368 to -0.076) for the sure things
rule, which ranks worse than random here because the customers most likely to buy would mostly buy
anyway. On test they earn $893 and
$923 per thousand customers on the list, against
$879 for emailing everyone. The error in predicted uplift (PEHE)
is 0.024 for the T learner and 0.016
for the X learner, against an average true effect of 4.48%. An oracle that
emails exactly the persuadables collects 1,843 incremental
conversions on the test split; the T learner leaves 81 of them on
the table and the X learner 30, while the sure things rule and
everyone, which both end up emailing the whole list, give up 167
and 167: the sleeping dogs they wake.

| Policy | Share contacted | Persuadables | Sure things | Lost causes | Sleeping dogs | Regret (conversions) |
|---|---:|---:|---:|---:|---:|---:|
| T learner | 80.0% | 96.6% | 71.5% | 80.1% | 11.4% | 81 |
| X learner | 85.0% | 99.1% | 79.6% | 85.0% | 8.4% | 30 |
| Sure things | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 167 |
| Everyone | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 167 |
| Oracle (known truth) | 4.6% | 100.0% | 0.0% | 0.0% | 0.0% | 0 |

Source: simulated, simulated customers, randomized email, test split of 40,235 (models fit on 119,603, shares chosen on 40,162); the oracle contacts exactly the persuadables, seed 12, as of 2026-09-27.

**At scale.** Criteo's full v2.1 release, all 13,979,592 rows, is ranked on
visit (conversion is too rare to rank on). Both learners beat everyone by Qini,
3.428 (3.209 to 3.619)
and 3.706 (3.515 to 3.929),
but the release carries no cost per contact and no value per visit, so the policy value keeps
rising to the end of the list and both learners chose 100.0% of it:
a degenerate operating point, the same list as emailing everyone. The paired differences show that
the X learner and the sure things rule cannot be told apart and that the T learner ranks below the
rule.

| Policy | Qini coefficient | Lower | Upper | Chosen share | Value on validation | Value on test |
|---|---:|---:|---:|---:|---:|---:|
| T learner | 3.428 | 3.209 | 3.619 | 100.0% | 10.6 | 10.4 |
| X learner | 3.706 | 3.515 | 3.929 | 100.0% | 10.6 | 10.4 |
| Sure things | 3.629 | 3.438 | 3.861 | 95.0% | 10.6 | 10.4 |
| Everyone | 0.000 | 0.000 | 0.000 | 100.0% | 10.6 | 10.4 |

Source: real:criteo, Criteo v2.1, every row: test split of 2,793,890 users (models fit on a seeded 2,000,000 of 8,388,844 training rows, shares chosen on 2,796,858); T and X learners, the sure things rule and everyone, as of 2026-09-27. Values are incremental visits per thousand users on the list; Criteo publishes no value per visit and no cost per impression, so no cost is assumed.

| Comparison | Difference | Lower | Upper |
|---|---:|---:|---:|
| T learner minus X learner | -0.279 | -0.483 | -0.094 |
| T learner minus Sure things | -0.201 | -0.443 | -0.010 |
| X learner minus Sure things | 0.077 | -0.132 | 0.255 |

Source: real:criteo, Criteo v2.1, every row: test split of 2,793,890 users (models fit on a seeded 2,000,000 of 8,388,844 training rows, shares chosen on 2,796,858); T and X learners, the sure things rule and everyone, as of 2026-09-27.

## Lifetime value and the allowance

BG/NBD (how often a customer buys, and whether they are still a customer) and Gamma-Gamma (how
much they spend when they buy) were fit on the 4,266 Online Retail II customers
who bought by 2010-11-30, of 5,878 in the file, and
judged on what those customers did from 2010-12-01 to 2011-12-09.

**The model over predicts.** It expected 19,057 purchases in
the holdout and the customers made 12,835, a difference of
+48.5%; revenue is over by
+29.7%. The cause is in the parameters: the fitted chance
that a customer stops buying after a purchase is 0.11%, close to
zero, so the model treats nearly every customer who went quiet as still active and keeps predicting
purchases for them. Among the customers who bought most often in the calibration window, the tenth
decile, the gap is much smaller: +11.6%.

| Decile | Customers | Predicted purchases | Actual purchases | Predicted revenue | Actual revenue |
|---|---:|---:|---:|---:|---:|
| 1 | 427 | 890 | 379 | $379,157.78 | $141,437.86 |
| 2 | 427 | 833 | 377 | $355,114.07 | $124,717.32 |
| 3 | 426 | 902 | 333 | $384,536.25 | $106,853.80 |
| 4 | 427 | 1,119 | 562 | $467,779.35 | $272,297.72 |
| 5 | 426 | 1,312 | 639 | $517,517.02 | $283,728.18 |
| 6 | 427 | 1,411 | 810 | $569,778.79 | $310,921.93 |
| 7 | 427 | 1,789 | 1,036 | $724,786.44 | $410,357.61 |
| 8 | 426 | 2,100 | 1,383 | $887,311.65 | $781,357.76 |
| 9 | 427 | 2,853 | 2,075 | $1,197,973.31 | $1,069,345.52 |
| 10 | 426 | 5,848 | 5,241 | $3,775,160.08 | $3,638,901.18 |
| All customers | 4,266 | 19,057 | 12,835 | $9,259,114.73 | $7,139,918.88 |

Source: real:retail, model bgnbd, 4,266 customers who bought by 2010-11-30 (of 5,878 in the file), calibration to 2010-11-30, as of 2026-09-27. Deciles are of purchase frequency in the calibration window.

PyMC-Marketing fit the same two models to the same frame, by maximum a posteriori under flat
priors; the largest relative difference across the seven parameters is
0.001%. The two fits agree, which points the over prediction
at the model on this data rather than at the repository's code.

| Parameter | Repository | PyMC-Marketing |
|---|---:|---:|
| BG/NBD r | 0.896 | 0.896 |
| BG/NBD alpha | 73.948 | 73.948 |
| BG/NBD a | 0.340 | 0.340 |
| BG/NBD b | 308.682 | 308.683 |
| Gamma-Gamma p | 2.162 | 2.162 |
| Gamma-Gamma q | 3.621 | 3.621 |
| Gamma-Gamma v | 516.597 | 516.597 |

Source: real:retail, model bgnbd_pymc, 4,266 customers who bought by 2010-11-30 (of 5,878 in the file), calibration to 2010-11-30; PyMC-Marketing fit by MAP under flat priors beside the repository's fit, as of 2026-09-27.

Over a 12 month horizon at 10% a
year, lifetime value per customer has a mean of $2,014.33, a median of
$1,149.20 and a ninetieth percentile of $3,301.15. The allowance is that
value times the 42% contribution margin times a payback share of
70%: $592.21 per acquired customer overall, from
$239.89 for one time buyers to $1,957.63 for frequent
ones. A channel's allowance weights the segment allowances by the mix of customers the channel is
assumed to bring; the mixes are stated in `marginal_clv.value`, not measured, because the retail
file records no channel.

| Segment | Customers | Mean lifetime value | Allowance |
|---|---:|---:|---:|
| One time (no repeat purchase) | 1,508 | $815.94 | $239.89 |
| Occasional (1 to 2 repeat purchases) | 1,371 | $1,246.01 | $366.33 |
| Regular (3 to 5 repeat purchases) | 778 | $2,055.69 | $604.37 |
| Frequent (6 or more repeat purchases) | 609 | $6,658.60 | $1,957.63 |
| All customers | 4,266 | $2,014.33 | $592.21 |

Source: real:retail, model bgnbd, 4,266 customers who bought by 2010-11-30 (of 5,878 in the file), calibration to 2010-11-30, as of 2026-09-27.

| Channel | Allowance |
|---|---:|
| Paid search | $626.60 |
| Paid social | $477.20 |
| Online video | $517.73 |
| Display and retargeting | $450.20 |
| Email | $730.71 |
| Affiliate and promo codes | $420.83 |
| Direct mail | $671.89 |

Source: real:retail, model bgnbd, 4,266 customers who bought by 2010-11-30 (of 5,878 in the file), calibration to 2010-11-30, as of 2026-09-27.

**Where it binds.** In the plan the allowance binds on affiliate and promo codes,
and online video cannot meet its allowance of
$517.73 at any spend the constraints allow: every dollar it
could be given acquires a customer for more than that. The optimizer holds it at the lowest spend
the constraints allow, -30.0% from last year, and labels it
"allowance (infeasible)" instead of failing the plan.

Read the allowance as a demonstration of the mechanism, not a number for Alderquist. The
transactions are a UK online gift retailer's, largely wholesale customers, from
2009-12-01 to 2011-12-09, and Alderquist's market is
simulated. The retailer's amounts are pounds sterling, printed here in the repository's dollar
format and applied to Alderquist's dollars one for one. And because the purchase model over
predicts, the allowance leans optimistic: it lets a channel pay more per customer than the holdout
supports.

## Attribution beside the truth

On 60,000 simulated user paths with 10,861 conversions,
60% of them incremental, six credit rules (last
touch, first touch, linear, position based, time decay and Shapley) are set beside each channel's
true incremental share and the calibrated own model's share.

| Channel | Last touch | First touch | Linear | Position based | Time decay | Shapley | Truth (simulated) | Calibrated model |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Paid search | 28.9% | 29.5% | 28.9% | 29.1% | 28.8% | 27.4% | 32.8% | 42.2% |
| Paid social | 17.4% | 16.7% | 16.9% | 17.0% | 17.0% | 16.4% | 21.8% | 26.7% |
| Online video | 8.0% | 7.4% | 7.7% | 7.7% | 7.7% | 8.3% | 6.1% | 3.5% |
| Display and retargeting | 23.0% | 23.3% | 23.4% | 23.2% | 23.4% | 23.2% | 6.5% | 9.9% |
| Email | 11.3% | 12.2% | 11.7% | 11.8% | 11.7% | 12.2% | 20.4% | 9.8% |
| Affiliate and promo codes | 6.7% | 6.4% | 6.7% | 6.6% | 6.7% | 7.3% | 7.9% | 4.0% |
| Direct mail | 4.7% | 4.6% | 4.7% | 4.7% | 4.7% | 5.2% | 4.3% | 4.0% |

Source: simulated, model both, 60,000 user paths, demonstration seed, seed 12, as of 2026-09-27.

| Rule | Mean share error (points) | Largest share error (points) | Rank agreement with truth | Over credits most | By (points) | Ratio to truth |
|---|---:|---:|---:|---|---:|---:|
| Last touch | 5.4 | 16.5 | 0.71 | Display and retargeting | 16.5 | 3.5 |
| First touch | 5.2 | 16.8 | 0.71 | Display and retargeting | 16.8 | 3.6 |
| Linear | 5.4 | 16.8 | 0.71 | Display and retargeting | 16.8 | 3.6 |
| Position based | 5.3 | 16.7 | 0.71 | Display and retargeting | 16.7 | 3.6 |
| Time decay | 5.4 | 16.8 | 0.71 | Display and retargeting | 16.8 | 3.6 |
| Shapley | 5.7 | 16.7 | 0.71 | Display and retargeting | 16.7 | 3.6 |

Source: simulated, model rules, 60,000 user paths, demonstration seed, seed 12, as of 2026-09-27.

**Every rule over credits display and retargeting.** Last touch gives it
23.0% of conversions against a true incremental share of
6.5%: 16.5 points too much, 3.5 times the
truth. The worst rule, time decay, over credits it by 16.8
points. The channel reaches people who were about to buy anyway, and a rule that shares out the
touches on converting paths cannot see that. The calibrated model gives it 9.9%,
much closer. The model is a third answer rather than a second truth, since it measures the weekly
panel and not the paths, and it has errors of its own: paid search at
42.2% against a true 32.8%,
email at 9.8% against 20.4%.

The rules agree with one another far more than with the truth. Last touch ranks the channels with
a rank correlation of 0.71 against the truth and misses
each channel's share by 5.4 points on average;
the grades table shows the other five.

## The mix model itself

Two backends estimate the same model family, geometric carryover and Hill saturation on a weekly
panel: own, written in the repository and fit by a stated search with block bootstrap intervals,
and bayes, fit by PyMC-Marketing with posterior intervals. On the demonstration brand, each
channel's return on ad spend with its 90% interval, beside the truth:

| Channel | own | own interval | bayes | bayes interval | Truth (simulated) |
|---|---:|---:|---:|---:|---:|
| Paid search | 2.38 | 2.24 to 2.61 | 2.98 | 1.85 to 5.03 | 3.15 |
| Paid social | 3.02 | 2.58 to 3.38 | 3.84 | 2.09 to 6.74 | 2.37 |
| Online video | 0.85 | 0.36 to 1.19 | 0.99 | 0.23 to 2.70 | 1.59 |
| Display and retargeting | 1.62 | 1.18 to 1.92 | 2.26 | 1.12 to 4.56 | 1.22 |
| Email | 4.79 | 3.21 to 6.79 | 8.44 | 3.99 to 17.60 | 7.70 |
| Affiliate and promo codes | 1.60 | 1.27 to 2.00 | 1.65 | 0.66 to 3.81 | 2.74 |
| Direct mail | 1.93 | 0.38 to 4.05 | 1.80 | 0.37 to 5.14 | 1.88 |

Source: simulated, model own, demonstration brand, 156 weeks, condition rho 0.6, feedback on, seed 12, as of 2026-09-27. Source: simulated, model bayes, demonstration brand, 156 weeks, condition rho 0.6, feedback on, seed 12, as of 2026-09-27.

By the rule the site uses, the backends disagree on a channel when their intervals do not overlap,
and on that rule they disagree nowhere.
The overlap hides a real difference in the intervals themselves: own's miss the truth in
paid search, paid social, online video, email, and affiliate and promo codes, while bayes's cover it in every channel.
Own covers the truth in 2 of 7 channels here
and bayes in 7. The point estimates differ most on
email: 4.79 for own and 8.44
for bayes, against a true 7.70. Own puts
66.1% of sales in the baseline and bayes 53.7%,
against a true 62.0%; each leaves 0.6% and
0.7% of sales unexplained.

**The recovery study.** Each backend was refit on fresh simulated markets under
6 conditions (three levels of correlation between the channels'
spend, each with and without retargeting spend that follows demand) and every fit was graded
against the truth. Own ran 20 seeds per condition, bayes
3. Own's median absolute error in return across channels
runs from 30.3% (rho 0.6, feedback off) to
46.2% (rho 0.9, feedback on),
over the 25% floor in every condition, and its intervals hold
the truth 42% of the time against a stated
90%. Bayes runs from 17.7%
(rho 0.6, feedback on) to 34.4%
(rho 0.2, feedback on), and it is over the floor under these conditions:
rho 0.2, feedback off; rho 0.2, feedback on; rho 0.9, feedback off; rho 0.9, feedback on. Its intervals hold the truth
98% of the time. Bayes is the more accurate backend on this study
and the only one whose intervals reach the stated level; its figures rest on
3 seeds per condition, so its intervals over seeds are wide.
Both tables, every condition and channel, are in `docs/evaluation.md`.

**Bayes diagnostics.** The demonstration fit ran 2 chains of
400 draws after 400 tuning steps, in
258.9 seconds, with 0 divergences and a largest
R hat of 1.010, just under the level PyMC warns at. That is a clean fit on fewer
chains than PyMC recommends for R hat. The recovery fits were less clean: most reported a few
divergences and an R hat above that level, though every one stayed under the ceilings the backend
enforces and is marked ok in `results/recovery/bayes_diagnostics.json`.

## Limitations

**The market is simulated.** Every mix model, budget and attribution figure describes the
simulator, which was written with the effects it asks the models to find: geometric carryover,
Hill saturation and retargeting spend that follows demand. A real market can break those
assumptions in ways the recovery study cannot show. None of these returns applies to a real brand
until the pipeline has run on that brand's weekly panel.

**Bayes rests on 3 seeds per condition.** Each bayes fit
samples for minutes (258.9 seconds on the demonstration brand), so its
recovery study ran that many seeds against own's 20, and its
calibration study 3. Those figures are indicative: the
intervals over seeds are wide, and the order of the conditions could change with more.

**One experiment.** A single geo test on a single channel calibrates both models. It measured
display and retargeting at $169,063 against a true $150,478, off by
+12.4%, and the calibrated models inherited that error. A second test on another
channel, or a repeat of this one, is what would show whether calibration pays on average; for the
budget, the regret study says it did not.

**Hillstrom is catalog retail in 2008.** The email experiment is a real randomized test of
64,000 recent buyers of a catalog retailer over 14 days
in 2008. It shows the analysis and the targeting protocol working on data the build did not write;
it says nothing about Alderquist's customers or about email as it is sent today.

**The purchase history is a UK gift wholesaler's.** Lifetime value is fit on a UK online gift
retailer whose customers are largely wholesale buyers, from 2009-12-01 to
2011-12-09, in pounds sterling. Their purchase rhythm and basket sizes are not
those of a direct to consumer home goods brand, and the model over predicts their holdout purchases
by +48.5%.

**Criteo has no cost.** Criteo publishes no cost per impression and no value per visit, so its policy
value counts incremental visits and a policy that ranks well still chooses the whole list. It tests
the ranking at scale, not the operating point.

**The allowance is a mechanism.** The allowance is lifetime value at margin times a payback share,
weighted by channel mixes that are stated, not measured. It shows how an acquisition cost limit
enters the plan and where it binds; the number itself is the retailer's, leans optimistic because
the purchase model over predicts, and moves one for one with the stated mixes and payback share.

**Own's intervals are too narrow.** Own's bootstrap resamples weeks with carryover and saturation
held at their searched values, so its intervals leave out the uncertainty of the search itself. They
hold the truth 42% of the time in the recovery study against a
stated 90%. Read them as a floor on the uncertainty; bayes's are the ones to
quote.

**The API serves the own backend only.** The API serves own's calibrated curves: when a separate
client last checked the live instance, `/v1/health` named own-0c071596-calibrated. Bayes is
not served, the uplift learners are not served, and lifetime value reaches the API only as the
allowance file. A plan saved through the API is an own plan.

## What the CMO would push back on

**"The market is simulated."** It is, on purpose: a simulated market is the only place a mix model
can be graded against the answer. The build did that grading, 120 own fits and
18 bayes fits across 6 conditions, and
published where each backend falls short. It did not run on a real brand's panel, and until it does,
no return in this memo applies to one.

**"The email test is from a catalog retailer in 2008."** It is, and it is used only for what it can
support: a real randomized test on which to show the sample ratio gate, a segment analysis with a
multiple testing correction and the targeting protocol. The build does not carry its effect sizes
over to Alderquist, and on it the uplift learners did not beat the simple rule; the simulator, where
the effects are known, is where the learners were shown to work. An Alderquist holdout is the next
step, and the protocol is ready for it.

**"The agency's attribution report says otherwise."** It probably does, and on these paths every
rule does too: each gives display and retargeting about
23.0% of conversions against a true incremental share of
6.5%. The build graded the rules against the truth on
simulated paths and ran a geo test on that channel, which measured it directly. It has not seen the
agency's report or any real path data; the answer to the agency is a holdout on the channel, and
this build shows how to design, register and read one.

**"The model says cut the channel the CFO likes."** The plan cuts display and retargeting, and direct mail as far as
the change limit allows and holds online video at its floor.
Display and retargeting is the one channel the build measured directly: after calibration its return is
1.31 against a breakeven of 2.38
at the 42% margin, and the truth is lower still at
1.22, so that cut survives taking the experiment at its word. The other
cuts rest on the model alone, and the online video cut rests on the
allowance, the weakest number in this memo. The build did not test those channels. A
holdout on whichever one the CFO would defend is the cheapest way to settle it, and no plan here
moves a channel by more than 30% of last year's spend, so a wrong
cut is bounded.

> Alderquist is a fictional direct to consumer home goods brand and its market is simulated with known truth. The email experiment is Kevin Hillstrom's public 2008 dataset, the purchase history is the UCI Online Retail II dataset, and the large uplift set is Criteo's public research release. No real company's spend and no real customer's identity appears here.
