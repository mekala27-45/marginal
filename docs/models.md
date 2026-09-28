# Models and the integration contract

Rendered from `results/manifest.json` by the claim gate; do not edit by hand.

Five models make or inform a decision in this build. Each has a card in `report/cards/`,
rendered from the manifest with the same sections in the same order: intended use, data and
population, how it was fit, metrics, the integration contract, limitations and the statement. A
card with a section or a contract line missing does not render.

## The cards

| Card | What it is | The decision it informs | Served |
|---|---|---|---|
| [mmm-own](../report/cards/mmm-own.md) | The repository's mix model: geometric carryover, Hill saturation, a stated search and block bootstrap intervals | The weekly budget plan | Yes: its curves answer `/v1/optimize` and `/v1/plans` |
| [mmm-bayes](../report/cards/mmm-bayes.md) | The same model family fit by PyMC-Marketing, with posterior intervals | The cross check on own | No |
| [uplift-t-learner](../report/cards/uplift-t-learner.md) | One outcome model per arm; the uplift is their difference | Who gets the email | No |
| [uplift-x-learner](../report/cards/uplift-x-learner.md) | The two stage learner, built on imputed effects | Who gets the email | No |
| [clv-bgnbd-gamma-gamma](../report/cards/clv-bgnbd-gamma-gamma.md) | Purchase frequency and spend per purchase, giving lifetime value | The acquisition cost allowance | Its allowance, through the optimizer |

## The contract

Every card answers thirteen lines, one sentence of evidence each. They are the model integration
contract carried from Day 8 and Day 9 of this series. A line a model does not meet says so, as
"partly", "not built" or "not applicable, because ...", and its box stays empty: a card that
stretched a line to tick it would be worse than one that leaves the box open.

| Line | What it asks | What it means in this build |
|---|---|---|
| trained | In the pipeline, against a baseline, on a stated split | Every model is fit by a `make` target, never in a notebook. The mix models' plans are judged against last year's mix and an equal split on the true curves; the learners against the sure things rule and emailing everyone; lifetime value against the holdout year. The splits are stated: rolling origins in time for the mix models, 60%, 20% and 20% by customer for the learners, a calibration window and a holdout for lifetime value. |
| timed | The data the model saw and the as of date are stated; nothing after it | The panel's weeks, the Hillstrom outcome window, the lifetime value calibration end and the manifest's as of date (2026-09-27) are printed on each card. |
| calibrated | An interval or a calibration check against held out truth | Interval coverage against the simulator's truth in the recovery study (stated level 90%), Qini intervals from a paired bootstrap, and the lifetime value holdout by decile. |
| useful | A decision it informs, with the cost or margin stated | The contribution margin of 42%; $0.12 per email and a 30% margin on the spend it causes; a payback share of 70% of lifetime value at margin. |
| fair | Who is affected and how the build checked (features, segments) | The mix models see no person. The learners use no protected attribute, but zip code class and region can stand in for one and were not checked. Lifetime value has no demographic field; its segments are purchase frequency. |
| gated | A test that fails the fit when a diagnostic is out of bounds | Only partly met anywhere. Bayes fits are checked against ceilings on divergences and R hat and marked failed, but not stopped; the targeting protocol refuses to choose on the test split; a lifetime value fit on the edge of its parameter space is not called converged. The hardest gate in the build sits on the experiments, not on a model: no result is shown while the sample ratio gate fails. |
| served | Where it is served (the API's `/v1/models`, `/v1/optimize`) or "not served" | Only own's curves are served; see below. |
| integrated | The page or the stage that consumes it | The budget stage, the attribution stage and the site's pages, named on each card. |
| monitored | The recovery log or "not built" (the weekly refresh is stretch) | Not built for any model. The recovery studies and the targeting run keep logs under `logs/`; nothing refits on a schedule. |
| documented | This card, rendered from the manifest | The five cards, this document and `docs/evaluation.md`, all rendered by the claim gate. |
| bounded | The statement; the brand is fictional and the market simulated | The statement closes every card, and the cards say which data are simulated and which are public releases. |
| validated | Graded against known truth or a randomized holdout, never itself | The mix models against the simulator's truth; the learners on the Hillstrom and Criteo test splits and the simulator's known effects; lifetime value on its holdout year. |
| explainable at the decision | What a reader of a decision sees: curves, marginal returns, intervals, Qini and policy value, the holdout table | Response curves and marginal returns with intervals for the plan; Qini and policy value curves with the chosen share for targeting; the holdout by decile and the allowance for lifetime value. |

## Which models serve

The API serves one model: own's response curves. At start it loads
`results/calibrate/own_calibrated_model.json` when the calibration stage has run and
`results/mmm/own_model.json` otherwise, and names the one it loaded in `/v1/health`
(`model_version`) and `/v1/models` (`serving`). `/v1/optimize` and `/v1/plans` run the budget
optimizer on it, with the lifetime value allowance from `results/clv/allowance.json` unless a
request turns it off. `/v1/models` also lists the other exports on disk, the uncalibrated own
model and the calibrated bayes model, as files; no route uses them.

The calibrated export in this build is `own-0c071596-calibrated`. When a separate client last
checked the live instance, `/v1/health` named the uncalibrated own export: the image it runs was built
without the calibrated export, and the redeploy in `docs/runbook.md` is what puts the calibrated
curves behind the live URL. Bayes, the two learners and the lifetime value model itself are not
served.

> Alderquist is a fictional direct to consumer home goods brand and its market is simulated with known truth. The email experiment is Kevin Hillstrom's public 2008 dataset, the purchase history is the UCI Online Retail II dataset, and the large uplift set is Criteo's public research release. No real company's spend and no real customer's identity appears here.
