# Evaluation: how the build grades itself

Rendered from `results/manifest.json` by the claim gate; do not edit by hand.

The rule is short. No model is graded on the data it was fit or tuned on, and nothing is graded
against itself. On the simulator the answer is known, so every estimate sits beside the truth. On
real data the answer is a randomized holdout, read once. Where the data has to choose something (a
share of customers to contact, the weight an experiment carries, an allocation), the choice is made
on one split, reported on another, and has to pass an interior test. Intervals are at
90% throughout.

## The recovery study

Each mix model backend is refit on fresh simulated markets under 6
conditions: three levels of correlation between the channels' weekly spend (rho), each with and
without retargeting spend that follows last week's demand. Own runs
20 seeds per condition (120 fits) and bayes
3 (18 fits), because each bayes fit
samples for minutes. Every fit is graded per channel against the truth: bias (the signed error in
return as a share of the true return), median absolute error, and whether the interval covers the
truth; per condition, the rank agreement between the estimated and the true order of the channels
(Spearman's correlation). Each carries an interval over seeds. The error floor of
25% names the conditions where the median error across channels is over
it; it is a callout, not a gate.

Across all conditions own's median absolute error is 37.1% and
its intervals cover the truth 42% of the time; bayes's error is
27.3% and its coverage 98%.
Own's worst condition is rho 0.9, feedback on (46.2%)
and its best rho 0.6, feedback off (30.3%); bayes's
worst is rho 0.2, feedback on (34.4%) and its
best rho 0.6, feedback on (17.7%).

| Condition | Channel | Bias | Bias lower | Bias upper | Median abs error | Error lower | Error upper | Coverage | Rank agreement |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| rho 0.2, feedback off | Paid search | -0.4% | -7.8% | +7.7% | 18.0% | 13.3% | 23.4% | 15% | not applicable |
| rho 0.2, feedback off | Paid social | +21.6% | +3.4% | +45.8% | 15.4% | 11.5% | 29.2% | 30% | not applicable |
| rho 0.2, feedback off | Online video | +21.7% | -10.3% | +61.6% | 51.1% | 37.5% | 61.4% | 50% | not applicable |
| rho 0.2, feedback off | Display and retargeting | -7.2% | -21.5% | +9.0% | 28.5% | 15.8% | 48.3% | 55% | not applicable |
| rho 0.2, feedback off | Email | -14.8% | -33.1% | +7.7% | 49.0% | 32.2% | 56.1% | 30% | not applicable |
| rho 0.2, feedback off | Affiliate and promo codes | +8.0% | -8.7% | +25.0% | 30.6% | 19.3% | 57.5% | 30% | not applicable |
| rho 0.2, feedback off | Direct mail | -60.4% | -67.4% | -52.5% | 66.5% | 50.8% | 72.0% | 10% | not applicable |
| rho 0.2, feedback off | All channels | not applicable | not applicable | not applicable | 34.4% | not applicable | not applicable | 31% | 0.74 |
| rho 0.2, feedback on | Paid search | -4.2% | -12.1% | +6.0% | 18.5% | 12.8% | 20.9% | 15% | not applicable |
| rho 0.2, feedback on | Paid social | +16.1% | -1.3% | +39.6% | 16.8% | 8.9% | 34.1% | 30% | not applicable |
| rho 0.2, feedback on | Online video | +26.9% | -5.4% | +67.2% | 53.8% | 45.8% | 69.4% | 35% | not applicable |
| rho 0.2, feedback on | Display and retargeting | +28.4% | +7.9% | +51.4% | 38.4% | 29.6% | 58.2% | 30% | not applicable |
| rho 0.2, feedback on | Email | -19.7% | -36.9% | +1.9% | 45.1% | 27.0% | 52.9% | 30% | not applicable |
| rho 0.2, feedback on | Affiliate and promo codes | +2.7% | -13.0% | +22.0% | 23.0% | 16.6% | 48.3% | 35% | not applicable |
| rho 0.2, feedback on | Direct mail | -53.9% | -64.2% | -41.0% | 65.1% | 47.4% | 71.5% | 15% | not applicable |
| rho 0.2, feedback on | All channels | not applicable | not applicable | not applicable | 34.4% | not applicable | not applicable | 27% | 0.74 |
| rho 0.6, feedback off | Paid search | -8.4% | -15.6% | -0.4% | 21.3% | 11.7% | 27.7% | 15% | not applicable |
| rho 0.6, feedback off | Paid social | +25.1% | +7.8% | +44.0% | 23.1% | 10.5% | 45.2% | 40% | not applicable |
| rho 0.6, feedback off | Online video | +5.3% | -18.9% | +32.0% | 57.3% | 40.7% | 69.9% | 55% | not applicable |
| rho 0.6, feedback off | Display and retargeting | -15.8% | -29.9% | +0.6% | 34.2% | 23.4% | 43.7% | 60% | not applicable |
| rho 0.6, feedback off | Email | +1.5% | -21.3% | +29.8% | 29.4% | 23.9% | 43.7% | 45% | not applicable |
| rho 0.6, feedback off | Affiliate and promo codes | -2.8% | -15.6% | +11.8% | 23.8% | 15.4% | 43.9% | 55% | not applicable |
| rho 0.6, feedback off | Direct mail | -39.4% | -53.5% | -23.1% | 46.4% | 31.5% | 74.2% | 40% | not applicable |
| rho 0.6, feedback off | All channels | not applicable | not applicable | not applicable | 30.3% | not applicable | not applicable | 44% | 0.71 |
| rho 0.6, feedback on | Paid search | -4.4% | -13.4% | +5.2% | 21.3% | 14.8% | 29.9% | 15% | not applicable |
| rho 0.6, feedback on | Paid social | +20.7% | +4.6% | +39.7% | 25.2% | 11.5% | 37.8% | 35% | not applicable |
| rho 0.6, feedback on | Online video | -1.2% | -25.1% | +25.5% | 59.7% | 46.1% | 75.5% | 50% | not applicable |
| rho 0.6, feedback on | Display and retargeting | +33.4% | +15.8% | +52.1% | 36.1% | 21.4% | 64.4% | 55% | not applicable |
| rho 0.6, feedback on | Email | +0.6% | -19.6% | +24.4% | 38.2% | 27.8% | 48.3% | 35% | not applicable |
| rho 0.6, feedback on | Affiliate and promo codes | -10.9% | -22.0% | +1.5% | 27.3% | 20.7% | 42.1% | 50% | not applicable |
| rho 0.6, feedback on | Direct mail | -45.7% | -59.8% | -30.0% | 56.2% | 46.7% | 79.1% | 20% | not applicable |
| rho 0.6, feedback on | All channels | not applicable | not applicable | not applicable | 36.4% | not applicable | not applicable | 37% | 0.73 |
| rho 0.9, feedback off | Paid search | -4.2% | -15.7% | +8.5% | 22.4% | 10.1% | 27.8% | 45% | not applicable |
| rho 0.9, feedback off | Paid social | +9.1% | -4.4% | +24.0% | 31.1% | 19.2% | 38.4% | 45% | not applicable |
| rho 0.9, feedback off | Online video | +6.0% | -27.5% | +46.3% | 51.7% | 28.2% | 98.1% | 70% | not applicable |
| rho 0.9, feedback off | Display and retargeting | +9.7% | -22.5% | +47.6% | 80.9% | 69.8% | 100.0% | 45% | not applicable |
| rho 0.9, feedback off | Email | +11.5% | -13.3% | +37.6% | 45.7% | 19.6% | 86.1% | 75% | not applicable |
| rho 0.9, feedback off | Affiliate and promo codes | -21.6% | -37.3% | -4.6% | 33.6% | 24.7% | 47.4% | 80% | not applicable |
| rho 0.9, feedback off | Direct mail | -16.2% | -42.6% | +12.9% | 68.7% | 44.4% | 95.5% | 65% | not applicable |
| rho 0.9, feedback off | All channels | not applicable | not applicable | not applicable | 40.3% | not applicable | not applicable | 61% | 0.47 |
| rho 0.9, feedback on | Paid search | +4.2% | -10.6% | +20.9% | 26.9% | 19.4% | 39.9% | 20% | not applicable |
| rho 0.9, feedback on | Paid social | +2.7% | -11.6% | +19.0% | 32.7% | 14.6% | 41.9% | 50% | not applicable |
| rho 0.9, feedback on | Online video | +10.1% | -22.8% | +49.0% | 68.3% | 43.7% | 94.3% | 75% | not applicable |
| rho 0.9, feedback on | Display and retargeting | +67.8% | +40.4% | +96.8% | 63.0% | 30.0% | 122.1% | 45% | not applicable |
| rho 0.9, feedback on | Email | +3.0% | -23.3% | +31.8% | 60.4% | 43.8% | 83.6% | 50% | not applicable |
| rho 0.9, feedback on | Affiliate and promo codes | -17.6% | -34.8% | +2.8% | 41.0% | 31.0% | 59.6% | 75% | not applicable |
| rho 0.9, feedback on | Direct mail | -25.0% | -53.1% | +11.2% | 65.3% | 43.6% | 94.7% | 55% | not applicable |
| rho 0.9, feedback on | All channels | not applicable | not applicable | not applicable | 46.2% | not applicable | not applicable | 53% | 0.50 |

Source: simulated, model own, markets with known truth, 20 seeds, as of 2026-09-27.

| Condition | Channel | Bias | Bias lower | Bias upper | Median abs error | Error lower | Error upper | Coverage | Rank agreement |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| rho 0.2, feedback off | Paid search | +14.4% | -10.0% | +38.7% | 17.6% | 5.3% | 55.4% | 100% | not applicable |
| rho 0.2, feedback off | Paid social | +25.5% | +20.3% | +30.6% | 24.3% | 18.3% | 33.8% | 100% | not applicable |
| rho 0.2, feedback off | Online video | -16.4% | -44.7% | +12.0% | 34.7% | 33.5% | 50.4% | 100% | not applicable |
| rho 0.2, feedback off | Display and retargeting | +13.8% | -4.6% | +32.2% | 29.5% | 21.6% | 33.5% | 100% | not applicable |
| rho 0.2, feedback off | Email | -25.0% | -56.9% | +6.8% | 38.9% | 29.6% | 65.9% | 67% | not applicable |
| rho 0.2, feedback off | Affiliate and promo codes | +17.0% | +9.6% | +24.4% | 20.2% | 4.3% | 26.6% | 100% | not applicable |
| rho 0.2, feedback off | Direct mail | -10.1% | -40.7% | +20.6% | 45.9% | 30.1% | 46.0% | 100% | not applicable |
| rho 0.2, feedback off | All channels | not applicable | not applicable | not applicable | 30.1% | not applicable | not applicable | 95% | 0.80 |
| rho 0.2, feedback on | Paid search | +14.9% | -9.5% | +39.3% | 17.8% | 7.0% | 55.4% | 100% | not applicable |
| rho 0.2, feedback on | Paid social | +27.7% | +20.8% | +34.5% | 25.7% | 18.4% | 38.9% | 100% | not applicable |
| rho 0.2, feedback on | Online video | -14.1% | -42.8% | +14.7% | 43.1% | 42.2% | 43.1% | 100% | not applicable |
| rho 0.2, feedback on | Display and retargeting | +3.5% | -12.3% | +19.2% | 14.4% | 8.0% | 32.8% | 100% | not applicable |
| rho 0.2, feedback on | Email | -22.6% | -56.4% | +11.2% | 44.2% | 38.9% | 62.5% | 67% | not applicable |
| rho 0.2, feedback on | Affiliate and promo codes | +19.0% | +10.6% | +27.5% | 13.7% | 9.1% | 34.4% | 100% | not applicable |
| rho 0.2, feedback on | Direct mail | -10.5% | -42.4% | +21.3% | 47.2% | 32.7% | 48.3% | 100% | not applicable |
| rho 0.2, feedback on | All channels | not applicable | not applicable | not applicable | 34.4% | not applicable | not applicable | 95% | 0.79 |
| rho 0.6, feedback off | Paid search | +11.7% | +8.6% | +14.8% | 9.6% | 8.1% | 17.4% | 100% | not applicable |
| rho 0.6, feedback off | Paid social | +22.1% | +9.1% | +35.2% | 23.1% | 2.1% | 41.2% | 100% | not applicable |
| rho 0.6, feedback off | Online video | +3.5% | -43.3% | +50.3% | 55.0% | 19.9% | 85.3% | 100% | not applicable |
| rho 0.6, feedback off | Display and retargeting | -20.2% | -39.4% | -1.1% | 32.5% | 14.6% | 42.8% | 100% | not applicable |
| rho 0.6, feedback off | Email | +5.5% | -3.6% | +14.6% | 8.2% | 5.6% | 19.1% | 100% | not applicable |
| rho 0.6, feedback off | Affiliate and promo codes | +30.0% | -2.6% | +62.5% | 6.8% | 6.0% | 90.7% | 100% | not applicable |
| rho 0.6, feedback off | Direct mail | -1.1% | -25.1% | +22.8% | 34.5% | 6.2% | 37.3% | 100% | not applicable |
| rho 0.6, feedback off | All channels | not applicable | not applicable | not applicable | 19.1% | not applicable | not applicable | 100% | 0.82 |
| rho 0.6, feedback on | Paid search | +9.8% | +5.9% | +13.7% | 9.8% | 4.0% | 15.6% | 100% | not applicable |
| rho 0.6, feedback on | Paid social | +23.5% | +8.4% | +38.5% | 24.8% | 0.2% | 45.4% | 100% | not applicable |
| rho 0.6, feedback on | Online video | -0.6% | -36.8% | +35.7% | 47.2% | 15.9% | 61.4% | 100% | not applicable |
| rho 0.6, feedback on | Display and retargeting | +1.4% | -37.5% | +40.2% | 57.8% | 5.0% | 58.7% | 100% | not applicable |
| rho 0.6, feedback on | Email | +7.3% | -2.2% | +16.8% | 11.6% | 9.1% | 19.5% | 100% | not applicable |
| rho 0.6, feedback on | Affiliate and promo codes | +34.7% | +0.5% | +68.9% | 15.6% | 7.0% | 95.5% | 100% | not applicable |
| rho 0.6, feedback on | Direct mail | -12.5% | -32.7% | +7.7% | 20.4% | 17.7% | 40.3% | 100% | not applicable |
| rho 0.6, feedback on | All channels | not applicable | not applicable | not applicable | 17.7% | not applicable | not applicable | 100% | 0.85 |
| rho 0.9, feedback off | Paid search | -7.8% | -16.4% | +0.8% | 7.7% | 5.0% | 20.7% | 100% | not applicable |
| rho 0.9, feedback off | Paid social | +27.0% | +12.7% | +41.3% | 24.7% | 6.6% | 49.6% | 100% | not applicable |
| rho 0.9, feedback off | Online video | +2.4% | -26.6% | +31.5% | 35.7% | 22.9% | 51.4% | 100% | not applicable |
| rho 0.9, feedback off | Display and retargeting | +41.4% | +3.7% | +79.1% | 41.5% | 15.2% | 97.8% | 100% | not applicable |
| rho 0.9, feedback off | Email | +6.7% | -33.2% | +46.5% | 40.7% | 18.2% | 78.8% | 100% | not applicable |
| rho 0.9, feedback off | Affiliate and promo codes | +0.4% | -21.5% | +22.2% | 29.7% | 7.4% | 36.0% | 100% | not applicable |
| rho 0.9, feedback off | Direct mail | -1.3% | -35.7% | +33.1% | 39.4% | 20.5% | 63.8% | 100% | not applicable |
| rho 0.9, feedback off | All channels | not applicable | not applicable | not applicable | 29.7% | not applicable | not applicable | 100% | 0.80 |
| rho 0.9, feedback on | Paid search | -3.4% | -12.8% | +5.9% | 12.7% | 7.6% | 15.4% | 100% | not applicable |
| rho 0.9, feedback on | Paid social | +30.0% | +18.0% | +41.9% | 24.1% | 15.0% | 50.8% | 100% | not applicable |
| rho 0.9, feedback on | Online video | -1.4% | -27.6% | +24.8% | 30.6% | 13.3% | 48.0% | 100% | not applicable |
| rho 0.9, feedback on | Display and retargeting | +16.0% | -0.6% | +32.5% | 28.1% | 14.9% | 34.7% | 100% | not applicable |
| rho 0.9, feedback on | Email | +13.2% | -22.3% | +48.7% | 32.4% | 2.0% | 74.1% | 100% | not applicable |
| rho 0.9, feedback on | Affiliate and promo codes | +9.6% | -18.2% | +37.5% | 36.1% | 17.6% | 47.4% | 100% | not applicable |
| rho 0.9, feedback on | Direct mail | -2.0% | -36.5% | +32.4% | 45.7% | 6.0% | 57.7% | 100% | not applicable |
| rho 0.9, feedback on | All channels | not applicable | not applicable | not applicable | 28.1% | not applicable | not applicable | 100% | 0.87 |

Source: simulated, model bayes, markets with known truth, 3 seeds, as of 2026-09-27.

## The cross check

On the demonstration brand the two backends are set side by side, channel by channel, with the
truth beside both (the table is in the quarterly review and on the Mix page). The backends disagree
on a channel when their intervals do not overlap. Agreement between two models is not evidence that
either is right, which is why the truth column is there: own covers it in
2 of 7 channels and bayes in
7.

## The lift test against the truth

The geo lift test is analyzed two ways, and both are graded against the true lift the simulator
knows. Difference in differences estimates $169,063 ($151,588 to
$186,538); synthetic control estimates $167,952 ($131,871
to $206,046); the truth is $150,478. Synthetic control's inference is by
placebo: the same fit is repeated 200 times with control geos
standing in for the treated ones, the p value is the share of placebos with a gap at least as large
(0.000), and the interval is the placebo distribution around the estimate. Power
was estimated by simulation before the test ran (`docs/experiments.md`).

| Method | Estimate | Lower | Upper | Truth (simulated) | Covers | Error |
|---|---:|---:|---:|---:|---|---:|
| Difference in differences | $169,063 | $151,588 | $186,538 | $150,478 | no | +12.4% |
| Synthetic control | $167,952 | $131,871 | $206,046 | $150,478 | yes | +11.6% |

Source: simulated, model did, 10 treated geos of 40, 8 weeks, condition rho 0.6, feedback on, seed 12, as of 2026-09-27.

## Calibration, before and after

The lift result enters both backends, and each is graded before and after on the demonstration
brand and across seeds of the demonstration condition, each seed with its own geo test.

|  | Before | After | Truth (simulated) |
|---|---:|---:|---:|
| Return on ad spend | 1.62 | 1.31 | 1.22 |
| Interval lower | 1.18 | 1.27 | not applicable |
| Interval upper | 1.92 | 1.32 | not applicable |
| Marginal return | 0.76 | 0.55 | 0.69 |

Source: simulated, model own, demonstration brand, condition rho 0.6, feedback on, seed 12, as of 2026-09-27.

|  | Before | After |
|---|---:|---:|
| Median absolute error, all channels | 36.4% | 27.9% |
| Median absolute error, tested channel | 36.1% | 15.2% |
| Interval coverage, all channels | 37.1% | 37.1% |

Source: simulated, model own, markets with known truth, demonstration condition, condition rho 0.6, feedback on, 20 seeds, as of 2026-09-27.

|  | Before | After | Truth (simulated) |
|---|---:|---:|---:|
| Return on ad spend | 2.26 | 1.42 | 1.22 |
| Interval lower | 1.12 | 1.25 | not applicable |
| Interval upper | 4.56 | 1.59 | not applicable |
| Marginal return | 1.41 | 1.15 | 0.69 |

Source: simulated, model bayes, demonstration brand, condition rho 0.6, feedback on, seed 12, as of 2026-09-27.

|  | Before | After |
|---|---:|---:|
| Median absolute error, all channels | 17.7% | 14.7% |
| Median absolute error, tested channel | 57.8% | 14.7% |
| Interval coverage, all channels | 100.0% | 100.0% |

Source: simulated, model bayes, markets with known truth, demonstration condition, condition rho 0.6, feedback on, 3 seeds, as of 2026-09-27.

## The regret study

A plan is only as good as what it earns on the true curves. For each of
10 seeds of the demonstration condition the market is simulated,
the geo test is run on it, own is fit before and after calibration, each fit's plan is optimized
under the stated constraints, and every plan is evaluated on that market's true curves beside the
plan built on the truth, last year's mix and an equal split. The headline is the share of the truth
optimal gain each plan captured, with a bootstrap interval over seeds.

| Model | Seeds | Share of optimal gain captured | Lower | Upper | Gain over last year (weekly) | Lower | Upper | Beats last year |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| uncalibrated | 10 | 68% | 53% | 81% | $12,250 | $9,646 | $14,730 | 90% |
| calibrated | 10 | 67% | 53% | 80% | $12,149 | $9,555 | $14,640 | 90% |

Source: simulated, model optimizer, markets with known truth, demonstration condition, condition rho 0.6, feedback on, 10 seeds, as of 2026-09-27.

## Targeting: Qini, policy value and the split rule

Every targeting figure comes from a protocol that splits customers once, by key, into training,
validation and test shares of 60%, 20% and
20%. Models are fit on training; the share to contact is chosen on
validation; everything published is read from test, scored once. The code refuses to choose a share
on the test or the training split.

The **Qini curve** is the incremental outcome, per thousand customers on the list, as a growing
share is contacted in descending order of score; the **Qini coefficient** is the area between it and
the random diagonal. Intervals come from a paired bootstrap of 200
replicates: every policy is scored on the same resampled customers, so the difference between two
policies' coefficients has its own, narrower interval. The **policy value** is the incremental profit
per thousand customers on the list when the top share is contacted; the value per thousand
contacted is published beside it, but the share is not chosen on it, because it falls as the list
deepens whenever the ranking works.

On the simulator both potential outcomes are known, so two more measures can be read. **PEHE** is
the root mean squared error of predicted uplift against the true effect:
0.024 for the T learner and 0.016 for the X
learner. The **quadrants** say which customers each policy reaches at its chosen share, and the
**oracle regret** counts the conversions a policy leaves behind against an oracle that contacts
exactly the persuadables.

| Policy | Share contacted | Persuadables | Sure things | Lost causes | Sleeping dogs | Regret (conversions) |
|---|---:|---:|---:|---:|---:|---:|
| T learner | 80.0% | 96.6% | 71.5% | 80.1% | 11.4% | 81 |
| X learner | 85.0% | 99.1% | 79.6% | 85.0% | 8.4% | 30 |
| Sure things | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 167 |
| Everyone | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 167 |
| Oracle (known truth) | 4.6% | 100.0% | 0.0% | 0.0% | 0.0% | 0 |

Source: simulated, simulated customers, randomized email, test split of 40,235 (models fit on 119,603, shares chosen on 40,162); the oracle contacts exactly the persuadables, seed 12, as of 2026-09-27.

## Lifetime value: the holdout by decile

The purchase model is fit on the calibration window and judged on what the same customers did in
the holdout, by decile of their calibration purchase frequency, so an error that sits in one kind
of customer shows up where it sits. Predicted purchases are +48.5%
against actual overall and +11.6% in the tenth decile.

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

Source: real:retail, model bgnbd, 4,266 customers who bought by 2010-11-30 (of 5,878 in the file), calibration to 2010-11-30, as of 2026-09-27.

## Attribution grades

Each credit rule's share of conversions per channel is compared with the true incremental share,
the summed incremental credit of every touch on the simulated paths. A rule is graded by its mean
and largest share error in points, its rank agreement with the truth, and the channel it over
credits most.

| Rule | Mean share error (points) | Largest share error (points) | Rank agreement with truth | Over credits most | By (points) | Ratio to truth |
|---|---:|---:|---:|---|---:|---:|
| Last touch | 5.4 | 16.5 | 0.71 | Display and retargeting | 16.5 | 3.5 |
| First touch | 5.2 | 16.8 | 0.71 | Display and retargeting | 16.8 | 3.6 |
| Linear | 5.4 | 16.8 | 0.71 | Display and retargeting | 16.8 | 3.6 |
| Position based | 5.3 | 16.7 | 0.71 | Display and retargeting | 16.7 | 3.6 |
| Time decay | 5.4 | 16.8 | 0.71 | Display and retargeting | 16.8 | 3.6 |
| Shapley | 5.7 | 16.7 | 0.71 | Display and retargeting | 16.7 | 3.6 |

Source: simulated, model rules, 60,000 user paths, demonstration seed, seed 12, as of 2026-09-27.

## Benjamini-Hochberg

The one family of hypothesis tests in the build is the email effect by purchase history segment:
7 segments per outcome, corrected by
Benjamini-Hochberg across segments at the false discovery rate set in `marginal_experiments.email`.
The Qini differences between policies are reported as intervals, not tested, and are not corrected.

## Interior tests, and what "degenerate" means on a page

Three operating points are chosen by the data, and each has to be interior: strictly inside what
was allowed, with the objective worse on both sides. When one is not, the point is degenerate: the
answer came from the edge of the grid or the bounds, not from the data, and the page prints the
word and the reason beside the number instead of hiding it.

- **The calibration weight.** Own is refit with the experiment's weight halved, as stated and
  doubled. The gap between the lift the model implies and the lift the experiment found is
  $9,299, $4,606 and
  $1,553, so the test reads interior:
  the residual against the experiment shrinks as the weight grows and is not zero at the stated weight. A weight that reproduced the experiment exactly would be
  degenerate, because the weight and not the data would have chosen the fit.
- **The allocation.** Budget is moved between every pair of interior channels in both directions,
  and every move must lower expected profit. The plan reads interior, with
  2 interior channels: every reallocation between interior channels lowers expected profit.
- **The targeting share.** The share with the highest policy value on validation must sit strictly
  inside the grid, with lower values on both sides:

| Dataset | T learner | X learner | Sure things | Everyone |
|---|---|---|---|---|
| Hillstrom | interior at 95.0% | interior at 85.0% | interior at 85.0% | degenerate at 100.0% | 
| Simulator | interior at 80.0% | interior at 85.0% | degenerate at 100.0% | degenerate at 100.0% | 
| Criteo v2.1 | degenerate at 100.0% | degenerate at 100.0% | interior at 95.0% | degenerate at 100.0% | 

Source: real:hillstrom, model t_learner, Hillstrom men's email against no email, validation split of 8,583, as of 2026-09-27. Source: simulated, model t_learner, simulated customers, randomized email, validation split of 40,162, seed 12, as of 2026-09-27.
Source: real:criteo, model t_learner, Criteo v2.1, validation split of 2,796,858 users, as of 2026-09-27. Everyone contacts the whole list by definition;
it is the baseline the others are judged against, so it is degenerate by construction.

> Alderquist is a fictional direct to consumer home goods brand and its market is simulated with known truth. The email experiment is Kevin Hillstrom's public 2008 dataset, the purchase history is the UCI Online Retail II dataset, and the large uplift set is Criteo's public research release. No real company's spend and no real customer's identity appears here.
