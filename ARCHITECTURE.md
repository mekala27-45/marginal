# Architecture

`marginal` is a pipeline that ends in a manifest, and three things read the manifest: the
documents, the site and the API. Nothing on any surface is typed by hand.

```
  SOURCES        simulator (market panel, customers, paths; truth tables),
                 Hillstrom email experiment, Online Retail II, Criteo uplift
        |  contracts        typed frames, checksums, provenance, definitions
        |  experiments      design, pre-registration, SRM gate, analysis
        |  mix models       own | bayes, one interface, one recovery study
        |  calibrate        experiment results become constraints and priors
        |  clv              purchase model, holdout check, acquisition allowance
        |  budget           response curves, constrained plan, regret
        |  targeting        uplift models, policy value at a contact cost
        |  attribution      credit rules beside incremental truth
        v
  EVALUATION     never grades itself: recovery against known truth, lift against
                 a randomized control, lifetime value against a holdout, plans
                 against the truth optimal plan, rules against known credit
        v
  results/manifest.json    every estimate, interval, truth value, table, label
        |  render           README, RESULTS, the memo, the cards, the docs
        |  marts            parquet for DuckDB-WASM, the site bundle
        v
  FLY API        /v1/plans, /v1/experiments, /v1/optimize, /v1/models, /v1/audit
  GITHUB PAGES   overview, mix, budget, experiments, targeting, report
```

## Why the mix model is graded on a simulator before it is shown on the brand

A mix model's return figures cannot be checked on real data. The counterfactual, the sales
that would have happened without the spend, is never observed, so a bar chart of return on
ad spend by channel from a real panel is a claim with no test behind it. The only evidence
that the method works is its error on markets where the truth is known, across enough seeds
and conditions to say when it fails. That is what `packages/sim` and `packages/evaluation`
exist for: the simulator writes the true carryover, saturation and return of every channel
to a truth table, the recovery runner fits each backend on many seeded markets under six
conditions (spend correlation between channels at three levels, demand feedback on
retargeting on and off), and the study reports bias, median absolute error, interval
coverage and rank agreement per backend, condition and channel. Every mix model figure on
the demonstration brand is drawn beside its truth, and every recovery figure carries its
seed count and condition. The condition that looks like a real market, high correlation
with feedback, is where `own` is worst, and the pages say so.

## Why the experiment sits upstream of the budget

The lift test is the one number in the system that does not depend on the model being right.
A geo holdout, assigned by stratified randomization, registered under a plan hash before its
data existed, passed through the SRM gate and analysed as pre-registered, measures what the
channel caused in those geos over those weeks. `packages/calibrate` turns that measurement
into a constraint on `own` (a pseudo observation weighted by the inverse of the experiment's
variance) and a lift test measurement on `bayes` (a shift in the saturation priors), and only
the calibrated curves reach the optimizer. If the model and the experiment disagree, the
experiment wins, and the before and after table shows how far the model moved. The budget
page consumes the curves; it never sees the panel.

## The packages

- `core`: the policy (every margin, cost, horizon and threshold, once), the manifest and its
  provenance, the statement, number formats, seeds, hashing, paths.
- `contracts`: the three public datasets, their checksums, licenses and loaders, and the
  reduction to committed aggregates; no raw row is committed.
- `sim`: the market (geos by weeks, seven channels, adstock and Hill truth, planned spend with
  a stated correlation, demand feedback), the customers with known effects and quadrants, and
  the user paths with known incremental credit.
- `evaluation`: the recovery runner, bootstrap and paired bootstrap intervals,
  Benjamini-Hochberg, coverage, rank agreement.
- `mmm`: one interface (`fit`, `contributions`, `response_curve`, `marginal_return`,
  `intervals`, `calibrate`), two backends, one export record the optimizer and the API read.
- `experiments`: geo lift design, power by simulation, the plan hash and SRM gate ported from
  readout, difference in differences and synthetic control with placebo inference, the
  Hillstrom analysis.
- `calibrate`: the loop, the before and after, the interior test on the weight.
- `clv`: BG/NBD and Gamma-Gamma written in the repository, the holdout by decile, the
  PyMC-Marketing cross check, the allowance.
- `budget`: the constrained optimizer (SLSQP from several starts, the solver status kept),
  the equalization check, the interior test, the regret study.
- `targeting`: T and X learners, Qini and uplift curves, the policy value curve, the
  validation then test protocol, PEHE and quadrants.
- `attribution`: five heuristic rules and exact Shapley over channel subsets, graded against
  the true incremental share.
- `registry`: the CLI, the stages in order, the manifest merge, the marts.
- `render`: the claim gate as a document renderer.
- `api`: FastAPI over SQLModel and Postgres; plans, experiments, results, audit log.

## Where state lives

Everything the pipeline derives is a file under `results/` or `data/sim`, committed, and
reproduced by `make rederive`. The registry (plans, experiments, results, the audit log) is
the only mutable state, in Neon Postgres behind the API on Fly; every write commits its row
and its audit row before the response is built, and the tests observe the rows from a second
connection. The site is static: DuckDB-WASM queries the committed marts in the browser, the
manifest supplies every printed number, and a recorded session stands in for the API when it
is asleep, labeled as recorded.

## The claim gate

Every document is a Jinja template over the manifest, rendered by `packages/render` and
compared whole file in CI. A number appears in a document only if a stage wrote it to the
manifest with its source, model, population, seed count and condition; a digit typed into a
template's prose fails the gate unless it is on a short list of names that contain digits.
The same manifest feeds the site's callouts, so the memo and the page cannot disagree.

## What is deliberately not here

No authentication beyond a shared write token, no rate limiting, one region, one shared CPU
machine that sleeps when idle. No model on the API but `own`. No language model writes any
sentence about a number. No real brand's spend and no real customer's identity, anywhere.
