# Model card: bayes, the PyMC-Marketing mix model

Rendered from `results/manifest.json` by the claim gate; do not edit by hand. The contract below
is the one `docs/models.md` sets out, and every figure is a manifest value or table.

## Intended use

The bayes backend fits the same model family as own, geometric carryover and Hill saturation on
the weekly panel, as a Bayesian model with PyMC-Marketing, so that every return comes with a
posterior interval. It is the build's cross check on own and the backend whose intervals can be
quoted, since on the recovery study they hold the truth at the stated level. It does not set the
plan and is not served: the plan and the API use own's curves. It is not meant for forecasting
sales, for a channel or a level of spend outside what it was fit on, for any real brand before it
has been fit and graded on that brand's panel, or, after calibration, for reading its narrow
interval on the tested channel as certainty, because that interval follows one experiment.

## Data and population

The same panel own is fit on: the demonstration brand's 156 weeks from
2023-10-02 to 2026-09-21, summed over 40 simulated geos,
simulated under rho 0.6, feedback on, with 38.0% of sales caused by paid
media and 62.0% baseline. The true channel parameters are in the table on
`report/cards/mmm-own.md`. The channel priors are stated in `marginal_mmm.bayes` and recorded with
every fit in `results/mmm/bayes_diagnostics.json`.

## How it was fit

PyMC-Marketing's `MMM`, with geometric adstock on normalized weights over the same lags own and the
simulator use, Hill saturation with the ceiling in front, an intercept, the controls (trend, log
price, promotion, holiday) and yearly Fourier seasonality. The baseline is additive here, where
own's is multiplicative; the recovery study grades what that difference costs. Sampling is NUTS on
one core, so a seed fixes every draw: 2 chains of 400
draws after 400 tuning steps, in 258.9 seconds on the
demonstration brand. The return is the posterior median of incremental revenue over spend, with
its 90% posterior interval. Spec hash `85e6f23579765fde`.

Calibration adds the posted lift result as the library's lift test measurement: the experiment's
revenue, turned into a national weekly change for the channel's change in spend, enters the
likelihood with the experiment's standard error, and the model is sampled again.

## Metrics

Return on ad spend on the demonstration brand, with the marginal return at current spend and the
half life of carryover, each beside the truth:

| Channel | Return | Lower | Upper | Truth (simulated) | Covers | Marginal return | True marginal | Half life (weeks) | True half life |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|
| Paid search | 2.98 | 1.85 | 5.03 | 3.15 | yes | 2.37 | 2.35 | 0.4 | 0.4 |
| Paid social | 3.84 | 2.09 | 6.74 | 2.37 | yes | 2.78 | 2.33 | 0.8 | 0.7 |
| Online video | 0.99 | 0.23 | 2.70 | 1.59 | yes | 0.90 | 1.43 | 0.7 | 1.6 |
| Display and retargeting | 2.26 | 1.12 | 4.56 | 1.22 | yes | 1.41 | 0.69 | 0.7 | 0.6 |
| Email | 8.44 | 3.99 | 17.60 | 7.70 | yes | 6.43 | 4.06 | 0.4 | 0.4 |
| Affiliate and promo codes | 1.65 | 0.66 | 3.81 | 2.74 | yes | 1.58 | 2.36 | 0.4 | 0.5 |
| Direct mail | 1.80 | 0.37 | 5.14 | 1.88 | yes | 1.67 | 1.52 | 1.1 | 2.1 |

Source: simulated, model bayes, demonstration brand, 156 weeks, condition rho 0.6, feedback on, seed 12, as of 2026-09-27.

The posterior intervals cover the truth in 7 of
7 channels. The model puts 53.7% of sales in
the baseline against a true 62.0%, leaves 0.7% of
sales unexplained, and has an unexplained variance share of 0.6%.

**Diagnostics.** The demonstration fit reported 0 divergences and a
largest R hat of 1.010, just under the level PyMC warns at.
The recovery fits were less clean: most reported a few divergences and an R hat above the level
PyMC warns at, though every one stayed under the ceilings the backend enforces and is marked ok in
`results/recovery/bayes_diagnostics.json`. Those per fit figures are not in the manifest.

**Recovery.** Refit on markets with known truth, 3 seeds in
each of 6 conditions (18 of
18 fits ran), the median absolute error in return across channels is
27.3% overall, from 17.7%
(rho 0.6, feedback on) to 34.4%
(rho 0.2, feedback on). Against the stated floor of 25%
it is over under these conditions:
rho 0.2, feedback off; rho 0.2, feedback on; rho 0.9, feedback off; rho 0.9, feedback on. Intervals hold the truth
98% of the time against a stated 90%.
With 3 seeds per condition, the intervals over seeds are wide:

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

**Calibration.** The lift test on display and retargeting moved that channel's return from
2.26 (1.12 to
4.56) to 1.42
(1.25 to 1.59) against a true
1.22. The interval narrowed past the truth: it held it before and sits
wholly above it after. The experiment's own estimate, $169,063, sits above the
true lift of $150,478, and the calibrated model follows the experiment, implying
$170,634 for the test where it implied $319,342
before. Across 3 seeds the error on the tested channel went from
57.8% to 14.7%,
a direction rather than a measurement at that count.

|  | Before | After | Truth (simulated) |
|---|---:|---:|---:|
| Return on ad spend | 2.26 | 1.42 | 1.22 |
| Interval lower | 1.12 | 1.25 | not applicable |
| Interval upper | 4.56 | 1.59 | not applicable |
| Marginal return | 1.41 | 1.15 | 0.69 |

Source: simulated, model bayes, demonstration brand, condition rho 0.6, feedback on, seed 12, as of 2026-09-27.

|  | Dollars |
|---|---:|
| Lift the model implied before | $319,342 |
| Lift the experiment found | $169,063 |
| Lift the model implies after | $170,634 |
| True lift (simulated) | $150,478 |

Source: simulated, model bayes, demonstration brand, condition rho 0.6, feedback on, seed 12, as of 2026-09-27.

|  | Before | After |
|---|---:|---:|
| Median absolute error, all channels | 17.7% | 14.7% |
| Median absolute error, tested channel | 57.8% | 14.7% |
| Interval coverage, all channels | 100.0% | 100.0% |

Source: simulated, model bayes, markets with known truth, demonstration condition, condition rho 0.6, feedback on, 3 seeds, as of 2026-09-27.

## The integration contract

A ticked line is met. Any other line names what it is instead: partly met, not built, or not
applicable, with the reason.

- [x] **trained**: Fit in the pipeline (`make recovery-bayes`) on the same 156 weeks as own, and set beside own and the truth, channel by channel, as the cross check in the quarterly review.
- [x] **timed**: The panel runs from 2023-10-02 to 2026-09-21 and the manifest is as of 2026-09-27; the fit sees no week after the panel's last, and the lift test it is calibrated on ran inside the panel, weeks 148 to 155.
- [x] **calibrated**: Its 90% posterior intervals hold the truth in 7 of 7 channels here and 98% of the time across the recovery study; after lift calibration the tested channel's interval misses the truth, as the metrics say.
- [ ] **useful** (partly): It informs the budget only through the cross check and the calibration comparison; the plan and the API use own's curves, so no dollar moves on bayes's estimates alone.
- [ ] **fair** (not applicable): Not applicable to people, because the model sees weekly national spend and sales and no customer; the parties a plan affects are the channels and the teams behind them.
- [ ] **gated** (partly): Each fit is checked against ceilings on divergences and R hat set in `marginal_mmm.interface` and marked failed when it crosses them (a test checks this); the status is reported, not raised, so a failed fit would not stop the pipeline, and every fit in this build is marked ok.
- [ ] **served** (not served): The API image is built without the bayes extra and no route fits or reads bayes curves; `/v1/models` lists the calibrated bayes export only as a file on disk.
- [x] **integrated**: The site's Mix page sets its returns and curves beside own's and the truth, and its recovery fits are the "before" of the bayes calibration study.
- [ ] **monitored** (not built): There is no scheduled refit or drift check, and the weekly refresh is a stretch goal; the recovery study's fits are logged in `logs/recovery_bayes.log`.
- [x] **documented**: This card, `docs/models.md` and `docs/evaluation.md`, all rendered from the manifest by the claim gate.
- [x] **bounded**: The statement closes this card: the brand is fictional and the market simulated, so every return here describes the simulator.
- [x] **validated**: Graded against the simulator's known truth, never against itself: 18 recovery fits across 6 conditions at 3 seeds each, and the truth beside every estimate on the demonstration brand.
- [x] **explainable at the decision**: A reader sees each channel's return with its posterior interval and the truth beside own's, and the response curves on the Mix page.

## Limitations

The recovery study rests on 3 seeds per condition, because
each fit samples for minutes; its per condition figures are indicative and the order of the
conditions could change with more seeds.

The demonstration fit ran 2 chains, fewer than PyMC recommends for a
reliable R hat, and most recovery fits reported a few divergences and an R hat above PyMC's warning
level while staying under the backend's ceilings. More chains and a higher target acceptance are
the first things to change if the study is rerun.

The baseline is additive where the simulator's demand is multiplicative, so some of the recovery
error may be the cost of that choice rather than of the sampler.

Calibration narrows the tested channel's interval until it follows one experiment, and that
experiment sits above the truth: the
calibrated interval misses the true
return. One experiment is not enough to make that interval trustworthy.

It is not served, so nothing a visitor to the API does uses it.

> Alderquist is a fictional direct to consumer home goods brand and its market is simulated with known truth. The email experiment is Kevin Hillstrom's public 2008 dataset, the purchase history is the UCI Online Retail II dataset, and the large uplift set is Criteo's public research release. No real company's spend and no real customer's identity appears here.
