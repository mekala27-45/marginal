# marginal

Marketing measurement and growth analytics for Alderquist, a fictional direct to consumer
home goods brand: a market simulator with known truth, two marketing mix model backends
graded on that truth and calibrated by experiments, a geo lift test designed with power and
analyzed as pre-registered, a real randomized email experiment, uplift models evaluated on
randomized holdouts with a policy value curve, lifetime value with a holdout validation
feeding an acquisition cost allowance, attribution rules beside incremental truth, a
constrained budget optimizer that equalizes marginal returns, a plan and experiment
registry on a live API, a quarterly review memo rendered from the manifest, and a site.

Every one of the eighteen mandatory steps in the build order is done; the checklist below
carries one line of evidence per item. Every dataset is used in full. The Criteo run used the
full v2.1 release (13,979,592 rows, every test row scored), not the ten
percent file the brief names, because that mirror no longer exists; the two learners were
fit on a seeded 2,000,000 row subsample of its training
split, and every Criteo figure is labeled with the release that ran. The API is live at
https://marginal-alderquist-api.fly.dev and was verified from a separate client (AJAY, Windows, PowerShell 5.1.26100.9444):
health ok, database ok, an
experiment registered, its result posted, a plan saved and all three read back through the
API, audit row before the response: yes.

Site: https://mekala27-45.github.io/marginal/ (Overview, Mix, Budget, Experiments, Targeting,
Report). Memo: `report/quarterly-review.md`. Results and the checklist: `RESULTS.md`.
Decisions: `DECISIONS.md`. Architecture: `ARCHITECTURE.md`. Runbook: `docs/runbook.md`.

> Alderquist is a fictional direct to consumer home goods brand and its market is simulated with known truth. The email experiment is Kevin Hillstrom's public 2008 dataset, the purchase history is the UCI Online Retail II dataset, and the large uplift set is Criteo's public research release. No real company's spend and no real customer's identity appears here.

## The two numbers

On the demonstration brand, reallocating the same weekly budget of $500,233
by marginal return, under the stated floors, ceilings, change limit and the acquisition cost
allowance, gains $18,334 a week over last year's
mix on the true curves ($953,345 a year), and the
calibrated model's plan captured 88% of the truth optimal
gain against 62% for the uncalibrated model.
That is one seed. Across the 10 seed regret study the
calibrated plan captured 67% of the optimal gain
(53% to
80%), a weekly gain of
$12,149 ($9,555 to
$14,640), and the uncalibrated plan captured
68%: on the study the one lift test does not
change how much of the gain the plan finds, because the plan depends on every channel's curve
and the test corrected one.

## What is here

- **A market with known truth.** 40 geos over 156 weeks,
  seven paid channels with true carryover, saturation and return, spend planned with a stated
  correlation between channels, and display and retargeting spend that follows demand.
  200,000 customers with known treatment effects and the four quadrants;
  60,000 user paths with the incremental credit of every touch known.
- **Two mix model backends on one interface.** `own` (geometric adstock, Hill saturation, a
  log linear baseline with additive media, a coarse grid then Nelder-Mead over rolling origins,
  a moving block bootstrap of 200 replicates) and `bayes`
  (PyMC-Marketing, the same transforms as priors, 2 chains of
  400 draws, divergences and R hat recorded). Graded on a recovery
  study of six conditions with 20 seeds for `own` and
  3 for `bayes`. Median absolute error on a
  channel's return: `own` 37.1% with
  42% interval coverage, worst in
  rho 0.9, feedback on at 46.2%;
  `bayes` 27.3% with
  98% coverage, worst in
  rho 0.2, feedback on at 34.4%.
- **A geo lift test with power.** Stratified assignment, pre-registered under plan hash
  `53733a76fe1af6ec` before its data existed, the SRM gate passed,
  difference in differences $169,063 ($151,588 to
  $186,538) and synthetic control $167,952 with
  200 placebo permutations, against a true lift of
  $150,478.
- **The loop.** The posted result becomes a pseudo observation for `own` and a lift test
  measurement for `bayes`. On the tested channel `own` moved from
  1.62 to 1.31 against a truth of
  1.22, and its error on that channel across
  20 seeds fell from
  36.1% to
  15.2%. The calibration weight passed its interior
  test (interior).
- **The real randomized experiment.** Hillstrom's 64,000 customers: the
  men's email raised conversion by 0.68%
  (0.53% to 0.83%) and spend by
  $0.77 per customer, with Benjamini-Hochberg across segments.
- **Uplift evaluated as uplift.** T and X learners with Qini and a policy value curve at a
  stated cost per email. On the real test split the sure things rule earned
  $207 per thousand customers and the T
  learner $188, with every Qini interval
  including zero; on the simulator, where the effects are known, the X learner's Qini is
  10.147 against 0.000 for everyone.
- **Lifetime value with a holdout.** BG/NBD and Gamma-Gamma fit by maximum likelihood on
  4,266 customers of Online Retail II and checked on the next year: the model
  over predicts holdout purchases by +48.5% overall
  (the fitted dropout probability after a purchase is 0.11%)
  and by +11.6% in the top decile; the
  PyMC-Marketing cross check agrees to 0.001%. The
  allowance it feeds into the optimizer holds Online video at its floor,
  because that channel's fitted curve never pays back within it.
- **Attribution beside the truth.** Six rules including exact Shapley over
  128 coalitions. Last touch hands display and retargeting
  23.0% of conversions against a true incremental
  share of 6.5%; the calibrated mix model says
  9.9%. Every rule over credits that channel most.
- **A registry on a live API.** Plans stored with the model version, the spec hash, the inputs'
  hash and the expected outcome with its interval; experiments with their plan hash; results
  refused without one; the audit row committed before the response. Writes are token gated,
  because this is a demonstration.

## The skills matrix

| Skill | Where it lives |
|---|---|
| Marketing mix modeling | `packages/mmm`, the mix page, `notebooks/01_simulator_and_recovery.ipynb` |
| Carryover and saturation transforms | `packages/mmm/src/marginal_mmm/transforms.py`, `docs/definitions.md` |
| Bayesian modeling | `packages/mmm/src/marginal_mmm/bayes.py`, the lifetime value cross check in `packages/clv` |
| Model validation against known truth | `packages/sim`, `packages/evaluation`, the recovery study in `RESULTS.md` |
| Geo experiments and synthetic control | `packages/experiments`, the experiments page, `notebooks/02_lift_test_and_calibration.ipynb` |
| Experiment design, power, pre-registration | `packages/experiments` (the plan hash, the power curve, the SRM gate) |
| Calibrating models with experiments | `packages/calibrate`, the before and after table in `report/quarterly-review.md` |
| Causal inference, uplift, heterogeneous treatment effects | `packages/targeting`, the targeting page, `notebooks/03_uplift_and_policy_value.ipynb` |
| Policy evaluation at a cost | the policy value curve and the chosen share, `packages/targeting/src/marginal_targeting/metrics.py` |
| Customer lifetime value | `packages/clv`, the holdout by decile in `report/cards/clv-bgnbd-gamma-gamma.md` |
| Attribution and its limits | `packages/attribution`, the three answers chart on the mix page |
| Budget optimization under constraints | `packages/budget`, the budget page, the regret study |
| Statistics | block bootstrap, placebo inference, Benjamini-Hochberg and coverage in `packages/evaluation` and `packages/experiments` |
| Simulation | `packages/sim` |
| SQL | the marts in `web/public/data`, queried in the browser by DuckDB-WASM (`web/src/lib/data.ts`) |
| APIs, persistence, deployment | `packages/api`, `fly.toml`, `scripts/check_persistence.py`, `deploy/` |
| Visualization | `web/`, the validated palette (`web/src/theme/palette.json`), one callout per chart |
| Communication | `report/quarterly-review.md` and the pushback paragraph on every page |
| Data licensing and provenance | `data/PROVENANCE.md`, the three declared licenses |

## The checklist (Section 20 of the brief)

Each line is done or not done, with one sentence of evidence.

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

Stretch items, listed and never counted: the Criteo full release (done, and it replaced the ten
percent run because the mirror is gone); the registry gates and the models page (not done);
the customers, attribution and explore pages (not done); Markov attribution (not done); the geo
hierarchy (not done); the containers in CI (`Dockerfile.api` is built by Fly on every deploy;
the pipeline container is not built in CI); the demo GIF (not done); the release workflow
(`.github/workflows/release.yml`, done); the load test (`scripts/load_test.py`, not run against
the live API).

## Running it

`docs/runbook.md` has every target. In short: `make setup`, place the three datasets under
`data/external` or let `make data` fetch them, then `make pipeline` (the bayes recovery is about
an hour of sampling), `make gates`, `make check`. `make rederive` runs the pipeline again from
the committed inputs and proves every published figure reproduces. `make deploy` (or
`deploy/deploy.ps1` on Windows) ships the API; `npm --prefix web run build` builds the site.

## Licensing and provenance

Code is Apache 2.0. Hillstrom's data is a public challenge release without a formal license
text, used with attribution; Online Retail II is CC BY 4.0 (the same source `pricepoint`, the
second project of this series, priced; here it is the purchase history); Criteo's uplift release is
CC BY-NC-SA 4.0, and the derived tables in `data/criteo` and `results/targeting` carry the
same terms. `data/PROVENANCE.md` has the checksums. No raw row of any of the three is committed,
and `scripts/scan_for_planted_identifiers.py` proves nothing that looks like a real person's
identity is either.
