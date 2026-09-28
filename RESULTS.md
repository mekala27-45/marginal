# Results

Rendered from `results/manifest.json` (as of 2026-09-27, demonstration seed
12); `scripts/check_published_numbers.py` re-renders this file and fails CI if
it differs. Stages present in the manifest: data, simulate, recovery_own, recovery_bayes, experiments, calibrate, clv, budget, targeting, attribution. Every table names
its source, model, population, seed count and condition in the line beneath it.

> Alderquist is a fictional direct to consumer home goods brand and its market is simulated with known truth. The email experiment is Kevin Hillstrom's public 2008 dataset, the purchase history is the UCI Online Retail II dataset, and the large uplift set is Criteo's public research release. No real company's spend and no real customer's identity appears here.

## The checklist (Section 20 of the brief)

| | Item | Status | Evidence |
|---|---|---|---|
| 1 | Three datasets fetched with checksums, provenance and licenses, every row used; the Criteo release stated in the first paragraph | done | `data/PROVENANCE.md`; Hillstrom 64,000 rows, Online Retail II 1,067,371 rows, Criteo 13,979,592 rows, all verified by checksum by `make data`; the first paragraph names the full v2.1 release and the training subsample. |
| 2 | Simulator with known truth; truth tables committed | done | `data/sim/` holds the geo panel, the national panel, `truth_channels.parquet`, `customers_truth.parquet` and `paths.parquet` for the demonstration seed; `tests/sim`. |
| 3 | Evaluation harness: the recovery runner, paired bootstrap, Benjamini-Hochberg, labels on every figure | done | `packages/evaluation`; every manifest entry carries source, model, population, seeds and condition; `tests/evaluation`. |
| 4 | Mix model `own` with curves, marginal returns and intervals; the recovery study on six conditions with at least twenty seeds | done | 120 fits ran (120 completed) across 6 conditions and 20 seeds; `results/recovery/own_summary.parquet`. |
| 5 | Mix model `bayes` on the same interface; the cross check table with the truth column; the recovery study on the stated seeds | done | 18 sampled fits across six conditions and 3 seeds; the cross check table in `RESULTS.md` (disagreements beyond intervals: none). |
| 6 | Geo lift test: power curve, registered plan hash, SRM gate, DiD and synthetic control with placebo inference; estimate against truth | done | Plan hash `53733a76fe1af6ec`, power at the true effect 100% from 60 simulations per design point, SRM passed, DiD error +12.4%, synthetic control error +11.6% with placebo p value 0.000. |
| 7 | API deployed on Fly with Neon; live URL in the README; verified from a separate client | done | https://marginal-alderquist-api.fly.dev, checked from AJAY, Windows, PowerShell 5.1.26100.9444 at 2026-09-28T00:03:22.3292486Z: yes; `results/deploy/verification.json`. |
| 8 | Plans and results observed from an independent connection; audit before response; the out of process check | done | `tests/api/test_registry.py` (`test_plan_is_committed`, `test_experiment_result_is_committed`, `test_audit_precedes_response`) and `scripts/check_persistence.py --start-server` in CI. |
| 9 | Calibration: a posted lift result changes both backends; before and after recovery error; the interior test on the weight | done | `own` error on the tested channel 36.1% to 15.2% over 20 seeds; `bayes` 17.7% to 14.7% over 3 seeds; weight test interior. |
| 10 | Budget optimizer with constraints and the equalization check; the regret study; the two headline numbers with intervals; the interior test on the allocation | done | Marginal returns equal across interior channels (yes, spread 0.000), solver "Optimization terminated successfully" from 8 starts, allocation interior; the regret study over 10 seeds in `results/budget/regret_summary.parquet`. |
| 11 | Targeting: T and X learners; Qini, uplift and policy value with intervals on Hillstrom; the chosen share on validation reported on test with its interior test; PEHE and quadrants on the simulator; the Criteo table | done | `results/targeting/`; Hillstrom T learner share 95.0% (interior); PEHE 0.016 for the X learner; Criteo X learner Qini 3.706 on the full release. |
| 12 | The Hillstrom experiment: SRM gate, effects by arm, outcome and segment | done | SRM passed; `results/experiments/email_effects.parquet` and `email_segments.parquet`, 6 of 7 segments significant after Benjamini-Hochberg. |
| 13 | Lifetime value with the holdout by decile, the cross check, the allowance wired into the optimizer | done | `results/clv/holdout_by_decile.parquet`; cross check difference 0.001%; `results/clv/allowance.json` read by `marginal budget` and by the API. |
| 14 | Attribution: six rules beside the truth and the mix model | done | `results/attribution/comparison.parquet`; over credit of display and retargeting by last touch 16.5 points (3.5 times the truth). |
| 15 | Overview, mix, budget with the slider, experiments, targeting and the report live on GitHub Pages, working from the recorded session when the API is asleep | done | `web/` with the six routes, `.github/workflows/pages.yml`, `web/public/data/recorded_session.json`, Playwright tests under `web/tests`. |
| 16 | RESULTS.md with every figure re-derived by the gate, a specific limitations section, a model card under the contract for every model | done | `RESULTS.md` and five cards under `report/cards/` are rendered from the manifest and diffed whole file by `scripts/check_published_numbers.py`. |
| 17 | README with the matrix and this checklist; DECISIONS.md with at least ten dated entries and two reversals; three executed notebooks with a dead end each; the pushback paragraph on every page and in the memo | done | This file; `DECISIONS.md`; `notebooks/` run by nbmake in CI; the paragraph closes every route and the memo. |
| 18 | Coverage at or above the floor, mypy strict clean, ruff clean, zero em dashes, zero banned vocabulary, palette validator green, forty to sixty commits, the rederive run before the tag, v0.1.0 pushed after the commits, Apache 2.0 with the three data terms declared, repo described, topics set | done | `make check` in CI; palette green with 0 failures; `results/rederive.json`; the tag pushed after the last commit. |

Stretch items, never counted: Criteo full release (done, in place of the ten percent run,
whose mirror is gone); registry gates and the models page (not done); customers, attribution
and explore pages (not done); Markov attribution (not done); geo hierarchy (not done);
containers in CI (not done; Fly builds `Dockerfile.api` on deploy); demo GIF (not done);
release workflow (done); load test against the live API (not run).

## The two numbers

| | Demonstration brand (one seed) | Regret study (10 seeds) |
|---|---:|---:|
| Weekly gain over last year's mix, same budget, true curves | $18,334 | $12,149 ($9,555 to $14,640) |
| Annual | $953,345 | |
| Share of the truth optimal gain captured, calibrated model | 88% | 67% (53% to 80%) |
| Share captured, uncalibrated model | 62% | 68% (53% to 81%) |

Source: simulated, model optimizer, demonstration brand, calibrated own curves, condition rho 0.6, feedback on, seed 12, as of 2026-09-27. Source: simulated, model optimizer, markets with known truth, demonstration condition, condition rho 0.6, feedback on, 10 seeds, as of 2026-09-27.

| Model | Seeds | Share of optimal gain captured | Lower | Upper | Gain over last year (weekly) | Lower | Upper | Beats last year |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| uncalibrated | 10 | 68% | 53% | 81% | $12,250 | $9,646 | $14,730 | 90% |
| calibrated | 10 | 67% | 53% | 80% | $12,149 | $9,555 | $14,640 | 90% |

Source: simulated, model optimizer, markets with known truth, demonstration condition, condition rho 0.6, feedback on, 10 seeds, as of 2026-09-27.

| Plan | True weekly profit | Gain over last year (weekly) | Gain over last year (annual) |
|---|---:|---:|---:|
| Calibrated model's plan | $36,354 | $18,334 | $953,345 |
| Uncalibrated model's plan | $30,862 | $12,842 | $667,778 |
| Truth optimal plan | $38,872 | $20,852 | $1,084,278 |
| Last year's mix | $18,020 | $0 | $0 |
| Equal split | -$56,079 | -$74,100 | -$3,853,187 |

Source: simulated, model optimizer, demonstration brand, calibrated own curves, condition rho 0.6, feedback on, seed 12, as of 2026-09-27.

The plan on the demonstration brand. Marginal returns are equal across the interior channels
(yes; spread 0.000), the solver
reported "Optimization terminated successfully" on the kept solution from 8
starts, and the allocation is interior: every reallocation between interior channels lowers expected profit.
The allowance was applied (yes); it cannot be met by
Online video at any admissible spend, so that channel is held at its
floor and labeled.

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

## The recovery study

Median absolute error of the estimated return per channel, interval coverage against the
nominal 90%, and the agreement between the estimated and the true
ranking of channels by marginal return, by condition. The stated floor for the error is
25%; `own` crosses it in every condition
(rho 0.2, feedback off, rho 0.2, feedback on, rho 0.6, feedback off, rho 0.6, feedback on, rho 0.9, feedback off, rho 0.9, feedback on) and `bayes` in
rho 0.2, feedback off, rho 0.2, feedback on, rho 0.9, feedback off, rho 0.9, feedback on. The worst condition for `own` is
rho 0.9, feedback on (46.2%), which is
the one that looks like a real market; the worst for `bayes` is
rho 0.2, feedback on (34.4%), and
its intervals cover the truth 98% of the time against
42% for `own`, whose block bootstrap intervals are too narrow.

| Condition | own error | own coverage | own rank agreement | bayes error | bayes coverage | bayes rank agreement |
|---|---:|---:|---:|---:|---:|---:|
| rho 0.2, feedback off | 34.4% | 31% | 0.74 (0.66 to 0.81) | 30.1% | 95% | 0.80 (0.74 to 0.86) |
| rho 0.2, feedback on | 34.4% | 27% | 0.74 (0.66 to 0.81) | 34.4% | 95% | 0.79 (0.74 to 0.83) |
| rho 0.6, feedback off | 30.3% | 44% | 0.71 (0.63 to 0.78) | 19.1% | 100% | 0.82 (0.71 to 0.93) |
| rho 0.6, feedback on | 36.4% | 37% | 0.73 (0.66 to 0.79) | 17.7% | 100% | 0.85 (0.73 to 0.96) |
| rho 0.9, feedback off | 40.3% | 61% | 0.47 (0.35 to 0.57) | 29.7% | 100% | 0.80 (0.68 to 0.92) |
| rho 0.9, feedback on | 46.2% | 53% | 0.50 (0.39 to 0.61) | 28.1% | 100% | 0.87 (0.82 to 0.92) |

Source: simulated, model own, markets with known truth, 20 seeds, as of 2026-09-27. Source: simulated, model bayes, markets with known truth, 3 seeds, as of 2026-09-27.
`own`: 120 fits, 120 ran. `bayes`:
18 fits, 18 ran, each with
2 chains of 400 draws.

Per channel and condition, `own`:

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

Per channel and condition, `bayes`:

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

Both backends on the demonstration brand (rho 0.6, feedback on), the truth in the last
column. Disagreements beyond the intervals: none.

| Channel | own | own lower | own upper | bayes | bayes lower | bayes upper | Truth (simulated) | Disagree |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Paid search | 2.38 | 2.24 | 2.61 | 2.98 | 1.85 | 5.03 | 3.15 | no |
| Paid social | 3.02 | 2.58 | 3.38 | 3.84 | 2.09 | 6.74 | 2.37 | no |
| Online video | 0.85 | 0.36 | 1.19 | 0.99 | 0.23 | 2.70 | 1.59 | no |
| Display and retargeting | 1.62 | 1.18 | 1.92 | 2.26 | 1.12 | 4.56 | 1.22 | no |
| Email | 4.79 | 3.21 | 6.79 | 8.44 | 3.99 | 17.60 | 7.70 | no |
| Affiliate and promo codes | 1.60 | 1.27 | 2.00 | 1.65 | 0.66 | 3.81 | 2.74 | no |
| Direct mail | 1.93 | 0.38 | 4.05 | 1.80 | 0.37 | 5.14 | 1.88 | no |

Source: simulated, model both, demonstration brand, seed 12, as of 2026-09-27.

| Channel | Return | Lower | Upper | Truth (simulated) | Covers | Marginal return | True marginal | Half life (weeks) | True half life |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|
| Paid search | 2.38 | 2.24 | 2.61 | 3.15 | no | 2.17 | 2.35 | 0.4 | 0.4 |
| Paid social | 3.02 | 2.58 | 3.38 | 2.37 | no | 2.67 | 2.33 | 0.8 | 0.7 |
| Online video | 0.85 | 0.36 | 1.19 | 1.59 | no | 1.02 | 1.43 | 0.6 | 1.6 |
| Display and retargeting | 1.62 | 1.18 | 1.92 | 1.22 | yes | 0.76 | 0.69 | 0.4 | 0.6 |
| Email | 4.79 | 3.21 | 6.79 | 7.70 | no | 3.93 | 4.06 | 0.3 | 0.4 |
| Affiliate and promo codes | 1.60 | 1.27 | 2.00 | 2.74 | no | 1.83 | 2.36 | 0.3 | 0.5 |
| Direct mail | 1.93 | 0.38 | 4.05 | 1.88 | yes | 1.28 | 1.52 | 2.8 | 2.1 |

Source: simulated, model own, demonstration brand, 156 weeks, condition rho 0.6, feedback on, seed 12, as of 2026-09-27. Residual as a share of sales 0.6%.

| Channel | Return | Lower | Upper | Truth (simulated) | Covers | Marginal return | True marginal | Half life (weeks) | True half life |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|
| Paid search | 2.98 | 1.85 | 5.03 | 3.15 | yes | 2.37 | 2.35 | 0.4 | 0.4 |
| Paid social | 3.84 | 2.09 | 6.74 | 2.37 | yes | 2.78 | 2.33 | 0.8 | 0.7 |
| Online video | 0.99 | 0.23 | 2.70 | 1.59 | yes | 0.90 | 1.43 | 0.7 | 1.6 |
| Display and retargeting | 2.26 | 1.12 | 4.56 | 1.22 | yes | 1.41 | 0.69 | 0.7 | 0.6 |
| Email | 8.44 | 3.99 | 17.60 | 7.70 | yes | 6.43 | 4.06 | 0.4 | 0.4 |
| Affiliate and promo codes | 1.65 | 0.66 | 3.81 | 2.74 | yes | 1.58 | 2.36 | 0.4 | 0.5 |
| Direct mail | 1.80 | 0.37 | 5.14 | 1.88 | yes | 1.67 | 1.52 | 1.1 | 2.1 |

Source: simulated, model bayes, demonstration brand, 156 weeks, condition rho 0.6, feedback on, seed 12, as of 2026-09-27. Divergences 0, largest R hat
1.010, residual share 0.7%.

## The geo lift test

Display and retargeting, spend change -100.0% in 10
treated geos against 30 controls, weeks 148 to
155 after a 52 week pre period. Plan hash
`53733a76fe1af6ec`, registered 2026-09-27T21:45:07+00:00 (local).
SRM gate passed (p 1.000). Power at the true effect
100%.

| Method | Estimate | Lower | Upper | Truth (simulated) | Covers | Error |
|---|---:|---:|---:|---:|---|---:|
| Difference in differences | $169,063 | $151,588 | $186,538 | $150,478 | no | +12.4% |
| Synthetic control | $167,952 | $131,871 | $206,046 | $150,478 | yes | +11.6% |

Source: simulated, model did, 10 treated geos of 40, 8 weeks, condition rho 0.6, feedback on, seed 12, as of 2026-09-27. Synthetic control: 200 placebo
permutations, p 0.000, largest donor weight 16%.

| Spend removed | Test length (weeks) | Simulations | Power | Mean true lift |
|---:|---:|---:|---:|---:|
| 100% | 4 | 60 | 100% | $76,605 |
| 100% | 8 | 60 | 100% | $152,790 |
| 50% | 4 | 60 | 100% | $41,681 |
| 50% | 8 | 60 | 100% | $87,706 |
| 25% | 4 | 60 | 57% | $18,820 |
| 25% | 8 | 60 | 88% | $39,852 |

Source: simulated, model did, 10 treated geos of 40, 8 weeks, condition rho 0.6, feedback on, seed 12, as of 2026-09-27.

## Calibration, before and after

|  | Before | After | Truth (simulated) |
|---|---:|---:|---:|
| Return on ad spend | 1.62 | 1.31 | 1.22 |
| Interval lower | 1.18 | 1.27 | not applicable |
| Interval upper | 1.92 | 1.32 | not applicable |
| Marginal return | 0.76 | 0.55 | 0.69 |

Source: simulated, model own, demonstration brand, condition rho 0.6, feedback on, seed 12, as of 2026-09-27.

|  | Dollars |
|---|---:|
| Lift the model implied before | $212,748 |
| Lift the experiment found | $169,063 |
| Lift the model implies after | $173,669 |
| True lift (simulated) | $150,478 |

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

|  | Dollars |
|---|---:|
| Lift the model implied before | $319,342 |
| Lift the experiment found | $169,063 |
| Lift the model implies after | $170,634 |
| True lift (simulated) | $150,478 |

|  | Before | After |
|---|---:|---:|
| Median absolute error, all channels | 17.7% | 14.7% |
| Median absolute error, tested channel | 57.8% | 14.7% |
| Interval coverage, all channels | 100.0% | 100.0% |

Source: simulated, model bayes, markets with known truth, demonstration condition, condition rho 0.6, feedback on, 3 seeds, as of 2026-09-27.

The weight the experiment carries in `own` is interior:
the residual against the experiment shrinks as the weight grows and is not zero at the stated weight (residual against the experiment at half the weight
$9,299, at the stated weight
$4,606, at double $1,553).
After calibration the `bayes` interval covers the truth: no
(before: yes); the lift test measurement pulls the posterior
to the experiment's estimate, which itself sits above the truth.

## The Hillstrom experiment

SRM gate passed (p 0.904). Cost per email
$0.12, margin on spend 30%.

| Arm | Outcome | No email | Email | Effect | Lower | Upper |
|---|---|---:|---:|---:|---:|---:|
| mens | visit | 0.1062 | 0.1828 | 0.0766 | 0.0710 | 0.0822 |
| mens | conversion | 0.0057 | 0.0125 | 0.0068 | 0.0053 | 0.0083 |
| mens | spend | 0.6528 | 1.4226 | 0.7698 | 0.5309 | 1.0087 |
| womens | visit | 0.1062 | 0.1514 | 0.0452 | 0.0399 | 0.0506 |
| womens | conversion | 0.0057 | 0.0088 | 0.0031 | 0.0018 | 0.0045 |
| womens | spend | 0.6528 | 1.0772 | 0.4244 | 0.2100 | 0.6388 |

Source: real:hillstrom, 64,000 recent buyers, three arms, as of 2026-09-27.

| History segment | Effect | Lower | Upper | p | p adjusted | Significant |
|---|---:|---:|---:|---:|---:|---|
| 1) $0 - $100 | 0.50% | 0.28% | 0.72% | 0.000 | 0.001 | yes |
| 2) $100 - $200 | 0.48% | 0.21% | 0.75% | 0.004 | 0.006 | yes |
| 3) $200 - $350 | 0.85% | 0.47% | 1.23% | 0.000 | 0.001 | yes |
| 4) $350 - $500 | 0.87% | 0.24% | 1.50% | 0.022 | 0.026 | yes |
| 5) $500 - $750 | 0.83% | 0.27% | 1.40% | 0.015 | 0.021 | yes |
| 6) $750 - $1,000 | 2.00% | 0.89% | 3.11% | 0.003 | 0.006 | yes |
| 7) $1,000 + | 0.93% | -0.58% | 2.44% | 0.312 | 0.312 | no |

Source: real:hillstrom, 64,000 recent buyers, three arms, as of 2026-09-27. Benjamini-Hochberg across segments.

## Targeting

| Policy | Qini coefficient | Lower | Upper | Chosen share | Value on validation | Value on test |
|---|---:|---:|---:|---:|---:|---:|
| T learner | -0.109 | -1.197 | 0.941 | 95.0% | $87 | $188 |
| X learner | -0.110 | -1.245 | 1.039 | 85.0% | $106 | $180 |
| Sure things | 0.191 | -0.716 | 1.214 | 85.0% | $84 | $207 |
| Everyone | 0.000 | 0.000 | 0.000 | 100.0% | $83 | $202 |

Source: real:hillstrom, Hillstrom men's email against no email, test split of 8,560 customers (models fit on 25,470, shares chosen on 8,583); T and X learners, the sure things rule and everyone, as of 2026-09-27.

| Comparison | Difference | Lower | Upper |
|---|---:|---:|---:|
| T learner minus X learner | 0.002 | -0.616 | 0.567 |
| T learner minus Sure things | -0.300 | -1.360 | 0.829 |
| X learner minus Sure things | -0.301 | -1.407 | 0.948 |

| Policy | Qini coefficient | Lower | Upper | Chosen share | Value on validation | Value on test |
|---|---:|---:|---:|---:|---:|---:|
| T learner | 8.924 | 7.627 | 10.030 | 80.0% | $892 | $893 |
| X learner | 10.147 | 8.848 | 11.252 | 85.0% | $912 | $923 |
| Sure things | -1.290 | -2.368 | -0.076 | 100.0% | $809 | $879 |
| Everyone | 0.000 | 0.000 | 0.000 | 100.0% | $809 | $879 |

Source: simulated, simulated customers, randomized email, test split of 40,235 (models fit on 119,603, shares chosen on 40,162); T and X learners, the sure things rule and everyone, seed 12, as of 2026-09-27. PEHE: T learner 0.024,
X learner 0.016. Regret against the oracle policy (per thousand
customers): T learner 81, X learner
30, sure things 167,
everyone 167.

| Policy | Share contacted | Persuadables | Sure things | Lost causes | Sleeping dogs | Regret (conversions) |
|---|---:|---:|---:|---:|---:|---:|
| T learner | 80.0% | 96.6% | 71.5% | 80.1% | 11.4% | 81 |
| X learner | 85.0% | 99.1% | 79.6% | 85.0% | 8.4% | 30 |
| Sure things | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 167 |
| Everyone | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 167 |
| Oracle (known truth) | 4.6% | 100.0% | 0.0% | 0.0% | 0.0% | 0 |

Source: simulated, simulated customers, randomized email, test split of 40,235 (models fit on 119,603, shares chosen on 40,162); the oracle contacts exactly the persuadables, seed 12, as of 2026-09-27.

| Policy | Qini coefficient | Lower | Upper | Chosen share | Value on validation | Value on test |
|---|---:|---:|---:|---:|---:|---:|
| T learner | 3.428 | 3.209 | 3.619 | 100.0% | 10.6 | 10.4 |
| X learner | 3.706 | 3.515 | 3.929 | 100.0% | 10.6 | 10.4 |
| Sure things | 3.629 | 3.438 | 3.861 | 95.0% | 10.6 | 10.4 |
| Everyone | 0.000 | 0.000 | 0.000 | 100.0% | 10.6 | 10.4 |

Source: real:criteo, Criteo v2.1, every row: test split of 2,793,890 users (models fit on a seeded 2,000,000 of 8,388,844 training rows, shares chosen on 2,796,858); T and X learners, the sure things rule and everyone, as of 2026-09-27. The full v2.1 release: 13,979,592
rows, 2,000,000 used to fit, 2,793,890
scored on test. Visit is the outcome and there is no cost per contact, so the chosen shares are
not interior.

## Lifetime value

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

Source: real:retail, model bgnbd, 4,266 customers who bought by 2010-11-30 (of 5,878 in the file), calibration to 2010-11-30, as of 2026-09-27. Predicted over actual purchases
+48.5% overall,
+11.6% in the top decile; the fitted
dropout probability after a purchase is 0.11%.

| Segment | Customers | Mean lifetime value | Allowance |
|---|---:|---:|---:|
| One time (no repeat purchase) | 1,508 | $815.94 | $239.89 |
| Occasional (1 to 2 repeat purchases) | 1,371 | $1,246.01 | $366.33 |
| Regular (3 to 5 repeat purchases) | 778 | $2,055.69 | $604.37 |
| Frequent (6 or more repeat purchases) | 609 | $6,658.60 | $1,957.63 |
| All customers | 4,266 | $2,014.33 | $592.21 |

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

## Attribution beside the truth

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

Source: simulated, model rules, 60,000 user paths, demonstration seed, seed 12, as of 2026-09-27. Shapley over 128
coalitions (127 observed on
60,000 paths with 10,861 conversions); credit
sums to the conversion count: yes.

## The live API, from a separate client

https://marginal-alderquist-api.fly.dev, checked from AJAY, Windows, PowerShell 5.1.26100.9444 at 2026-09-28T00:03:22.3292486Z:
health ok, database ok, serving model
own-0c071596-uncalibrated; experiment `2fb962a7-49d4-5a58-91a3-c5c7bd10009a` registered under plan
hash `b5b891c8e2b241d3`, its result read back as $123,456, plan
`09bfc021-89cd-42a1-9bb7-cfbcfda2681f` saved and read back, 3 audit entries,
audit row before the response yes, statement present
yes, passed yes.

## Limitations

- The market is simulated. The recovery study says how far the models are from a known truth
  under six conditions; it says nothing about how far they would be on a real brand's panel,
  whose conditions are unknown. The demonstration brand is one seed of one condition.
- `own` under covers: its block bootstrap intervals hold the truth
  42% of the time against a nominal
  90%, and its search rarely reports convergence. The pages show the
  intervals anyway and this line says what they are worth.
- `bayes` ran on 3 seeds per condition, so its
  recovery figures are coarse, and several fits reported divergences or an R hat above the
  library's warning level while staying under the stated ceilings.
- One experiment. The calibration table has one row per backend, and on the regret study one
  test does not change how much of the optimal gain the plan captures.
- The email test is a catalog retailer's from 2008 and the men's arm only; the effects are
  small and the uplift learners did not beat the sure things rule on its test split.
- The purchase history is a UK online gift retailer's, largely wholesale customers, 2009 to
  2011, printed in the repository's dollar format; the lifetime value model over predicts the
  holdout, and the allowance built on it is a demonstration of the mechanism.
- Criteo publishes no cost per impression, so its policy value is incremental visits per
  thousand users and no share is interior.
- The geo test was registered locally: the build sandbox could not reach the live API, so the
  registry client fell back to the local record with the same hash.
- The API serves the `own` backend only, in one region, behind one shared write token.

## Model cards

`report/cards/mmm-own.md`, `report/cards/mmm-bayes.md`, `report/cards/uplift-t-learner.md`,
`report/cards/uplift-x-learner.md`, `report/cards/clv-bgnbd-gamma-gamma.md`, each under the
contract in `docs/models.md`.

> Alderquist is a fictional direct to consumer home goods brand and its market is simulated with known truth. The email experiment is Kevin Hillstrom's public 2008 dataset, the purchase history is the UCI Online Retail II dataset, and the large uplift set is Criteo's public research release. No real company's spend and no real customer's identity appears here.
