# Model card: own, the repository's marketing mix model

Rendered from `results/manifest.json` by the claim gate; do not edit by hand. The contract below
is the one `docs/models.md` sets out, and every figure is a manifest value or table.

## Intended use

The own backend estimates what each of Alderquist's 7 paid channels
returns per dollar, how long its effect lasts and where it saturates, from a weekly panel of spend
and sales, so that the budget optimizer can move money until the next dollar earns the same in
every channel; it is the backend the quarterly review's plan is built on and the one the API
serves. It is meant for reallocating a stated budget across these channels within the stated
constraints. It is not meant for forecasting sales, for judging a single campaign or creative, for
a channel it was not fit on, for a budget far outside the spend it has seen (its curves are
extrapolations there), or for any real brand before it has been fit and graded on that brand's
own panel.

## Data and population

The demonstration brand's national weekly panel: 156 weeks from
2023-10-02 to 2026-09-21, summed over 40 simulated geos, with
spend in each channel, sales, a price index, promotions and holidays. Spend averages
$491,817 a week and sales $3,159,578. The market is
simulated under the demonstration condition, rho 0.6, feedback on: the channels' weekly spend is
correlated (a target of 0.6, 0.55
achieved) and retargeting spend follows last week's demand. The truth is known:
38.0% of sales are caused by paid media and 62.0% are
baseline. The true channel parameters the model is trying to recover:

| Channel | Spend last year | True return | True marginal return | Carryover | Half life (weeks) | Half saturation | Slope |
|---|---:|---:|---:|---:|---:|---:|---:|
| Paid search | $6,742,809 | 3.15 | 2.35 | 0.20 | 0.4 | $117,000 | 1.6 |
| Paid social | $5,758,845 | 2.37 | 2.33 | 0.35 | 0.7 | $121,000 | 1.8 |
| Online video | $3,326,366 | 1.59 | 1.43 | 0.65 | 1.6 | $84,000 | 1.5 |
| Display and retargeting | $4,308,419 | 1.22 | 0.69 | 0.30 | 0.6 | $49,000 | 2.2 |
| Email | $803,597 | 7.70 | 4.06 | 0.15 | 0.4 | $9,000 | 2.4 |
| Affiliate and promo codes | $2,097,165 | 2.74 | 2.36 | 0.25 | 0.5 | $40,000 | 1.7 |
| Direct mail | $2,974,928 | 1.88 | 1.52 | 0.72 | 2.1 | $71,500 | 1.4 |

Source: simulated, 40 geos, 156 weeks, demonstration seed, condition rho 0.6, feedback on, seed 12, as of 2026-09-27.

## How it was fit

Sales in a week are organic demand, multiplicative in trend, price, promotion, holidays and
seasonality, plus each channel's adstocked and saturated spend times a non negative ceiling
(`marginal_mmm.own`). Carryover is geometric; saturation is a Hill curve with a half saturation
point and a slope. The transforms are searched in stated steps: a grid over carryover, half
saturation and slope, one channel at a time (336 evaluations); a ridge
penalty chosen on forecast error at 8 rolling origins held out in time;
then Nelder-Mead from the grid optimum, channel by channel and then jointly
(989 evaluations). The Nelder-Mead step ends at its evaluation cap
and does not report convergence, on this fit and on every recovery fit
(`results/mmm/own_diagnostics.json`, `results/recovery/own_diagnostics.json`). Intervals come from a
moving block bootstrap over weeks, 200 replicates of
8 week blocks at the 90% level, with the
transforms held at their searched values. The fit took 13.0 seconds; its spec
hash is `0c07159692e406de`.

Calibration adds the posted lift result as a pseudo observation: the lift the model implies for the
test's geos and weeks is pulled toward the experiment's estimate, with a weight set by the
experiment's precision against a stated residual scale, and the search runs again with that row in
place. The calibrated export, `own-0c071596-calibrated`, is the one the plan and the API use.

## Metrics

Return on ad spend on the demonstration brand, with the marginal return at current spend and the
half life of carryover, each beside the truth:

| Channel | Return | Lower | Upper | Truth (simulated) | Covers | Marginal return | True marginal | Half life (weeks) | True half life |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|
| Paid search | 2.38 | 2.24 | 2.61 | 3.15 | no | 2.17 | 2.35 | 0.4 | 0.4 |
| Paid social | 3.02 | 2.58 | 3.38 | 2.37 | no | 2.67 | 2.33 | 0.8 | 0.7 |
| Online video | 0.85 | 0.36 | 1.19 | 1.59 | no | 1.02 | 1.43 | 0.6 | 1.6 |
| Display and retargeting | 1.62 | 1.18 | 1.92 | 1.22 | yes | 0.76 | 0.69 | 0.4 | 0.6 |
| Email | 4.79 | 3.21 | 6.79 | 7.70 | no | 3.93 | 4.06 | 0.3 | 0.4 |
| Affiliate and promo codes | 1.60 | 1.27 | 2.00 | 2.74 | no | 1.83 | 2.36 | 0.3 | 0.5 |
| Direct mail | 1.93 | 0.38 | 4.05 | 1.88 | yes | 1.28 | 1.52 | 2.8 | 2.1 |

Source: simulated, model own, demonstration brand, 156 weeks, condition rho 0.6, feedback on, seed 12, as of 2026-09-27.

The intervals cover the truth in 2 of 7
channels. The model puts 66.1% of sales in the baseline against a true
62.0%, leaves 0.6% of sales unexplained, and has an
unexplained variance share of 0.4%.

**Recovery.** Refit on markets with known truth, 20 seeds in
each of 6 conditions (120 of
120 fits ran), the median absolute error in return across channels is
37.1% overall, from 30.3%
(rho 0.6, feedback off) to 46.2% in the worst
condition (rho 0.9, feedback on), over the stated
25% floor in every condition. Intervals hold the truth
42% of the time against a stated 90%.
Rank agreement with the true order of the channels is lowest where the channels' spend moves most
closely together: 0.50
(0.39 to
0.61) with feedback on and
0.47
(0.35 to
0.57) with it off.
Every channel and condition, with intervals over seeds:

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

**Calibration.** The lift test on display and retargeting moved that channel's return from
1.62 to 1.31 against a true
1.22; the interval covered
the truth before and misses it after,
because the experiment's estimate sits above
the truth and the calibrated fit follows it. Across 20 seeds, each
with its own test, the error on the tested channel went from
36.1% to 15.2%.

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

## The integration contract

A ticked line is met. Any other line names what it is instead: partly met, not built, or not
applicable, with the reason.

- [x] **trained**: Fit in the pipeline (`make recovery`) on the 156 weeks of the demonstration panel, with the transform search scored on 8 rolling origins held out in time, and its plan judged on the true curves against last year's mix and an equal split (the `budget.comparison` table in the memo).
- [x] **timed**: The panel runs from 2023-10-02 to 2026-09-21 and the manifest is as of 2026-09-27; the fit sees no week after the panel's last, and the lift test it is calibrated on ran inside the panel, weeks 148 to 155.
- [ ] **calibrated** (partly): Its 90% bootstrap intervals are checked against the truth and fall short: they cover it in 2 of 7 channels here and 42% of the time across the recovery study.
- [x] **useful**: It sets the weekly plan: at the 42% contribution margin its calibrated curves move last year's $500,233 a week between channels for a true gain of $18,334 a week on the demonstration brand.
- [ ] **fair** (not applicable): Not applicable to people, because the model sees weekly national spend and sales and no customer; the parties a plan affects are the channels and the teams behind them, and the change limit of 30% bounds how far one plan moves any of them.
- [ ] **gated** (partly): Tests check that every step of the search and the bootstrap ran and that a fit is reproducible from its seed, and the recovery stage counts the fits that ran (120 of 120); no diagnostic bound fails an own fit.
- [x] **served**: The API loads the calibrated export (own-0c071596-calibrated) when `results/calibrate/own_calibrated_model.json` exists and the uncalibrated one otherwise, answers `/v1/optimize` and `/v1/plans` with it and names it in `/v1/health` and `/v1/models`; when a separate client last checked the live instance it named the uncalibrated export, so the live URL serves the calibrated curves only after the redeploy in `docs/runbook.md`.
- [x] **integrated**: The budget stage builds the plan from its curves, the attribution stage reads its channel shares, and the site's Mix and Budget pages draw its returns, curves and plan from the marts.
- [ ] **monitored** (not built): There is no scheduled refit or drift check, and the weekly refresh is a stretch goal; what exists is the recovery study, rerun with the pipeline, and its log in `logs/recovery_own.log`.
- [x] **documented**: This card, `docs/models.md` and `docs/evaluation.md`, all rendered from the manifest by the claim gate.
- [x] **bounded**: The statement closes this card: the brand is fictional and the market simulated, so every return here describes the simulator.
- [x] **validated**: Graded against the simulator's known truth, never against itself: the truth sits beside every estimate on the demonstration brand, and the recovery study grades 120 fits across 6 conditions.
- [x] **explainable at the decision**: A reader of the plan sees each channel's return with its interval and the truth, the response curves on the Mix page, and in the allocation table the marginal return, the marginal profit and the bound each channel sits at.

## Limitations

The intervals are too narrow. The bootstrap holds carryover and saturation at their searched
values, so the uncertainty of the search itself is left out, and coverage in the recovery study is
42% against a stated 90%. Quote bayes's
intervals, or treat these as a floor, before reading a channel's interval as the range of its
return.

The error in return is over the stated floor in every condition of the recovery study,
and worst in rho 0.9, feedback on,
where the channels' spend moves most closely together: a brand that plans every channel on the
same calendar gives this model the least to learn from.

The Nelder-Mead step stops at its evaluation cap rather than at a convergence test, so a longer
search could move the transforms.

The simulator was written with the model family this backend fits, so the recovery study measures
estimation error, not the error of assuming the wrong family.

Calibration pulls the tested channel toward one experiment, and that experiment sits
above the truth; with one test the
model cannot tell the experiment's error from its own.

> Alderquist is a fictional direct to consumer home goods brand and its market is simulated with known truth. The email experiment is Kevin Hillstrom's public 2008 dataset, the purchase history is the UCI Online Retail II dataset, and the large uplift set is Criteo's public research release. No real company's spend and no real customer's identity appears here.
