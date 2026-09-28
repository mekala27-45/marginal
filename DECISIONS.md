# Decisions

Dated, in the order they were taken. Two are reversals of something the brief or an earlier
step had fixed, and are marked as such. Numbers quoted here are the state at the time of the
decision; the current figures are in `RESULTS.md`, which is rendered from the manifest.

## 2026-09-27: the brand is Alderquist, not Tillmark (reversal)

The brief named the brand Tillmark and asked for a web search before the first commit. The
search found a registered company under that name (Tillmark Oy, listed in a Finnish company
directory) and a public e-commerce project called tillmark on GitHub, so the name went. The
replacement, Alderquist, returned nothing but unrelated apparel brands sharing the word
"Alder". The name lives in one place, `packages/core/src/marginal_core/statements.py`, and the
statement gate reads it from there.

## 2026-09-27: the palette moved four slots to pass the ported validator (reversal)

The brief's categorical set was stated as validated, and the validator ported from the earlier
builds, with a card contrast check added because this build draws charts on white cards,
failed it: slot three in light mode fell under the adjacent separation target beside slot
four, and three dark slots fell under it against their neighbours or under contrast on the
dark surface. Rather than loosen the check, the slots moved: light slot three became `#63349B`;
dark slots two, four, six and eight became `#D19F2F`, `#EF894E`, `#94B741` and `#46BFA5`; the dark
diverging midpoint became `#29282D`. The rest is as the brief stated it. The validator runs in
CI against `web/src/theme/palette.json` and its summary is in the manifest under `palette.*`.

## 2026-09-27: Criteo ran on the full v2.1 release, with a declared training subsample

The brief made the ten percent file the mandatory run and the full release stretch. The ten
percent mirror the brief pointed to no longer exists, and the only copy that verifies by
checksum is Criteo's own full v2.1 release. So the full release ran: every test row is scored,
the two learners are fit on a seeded two million row subsample of the training split (the
first paragraph of the README says so), and every Criteo figure is labeled with the release.
Visit is the outcome, because conversion is too rare, and there is no cost per impression, so
the Criteo policy value is incremental visits per thousand users and no share is interior.

## 2026-09-27: PyMC-Marketing pinned, and NumPy and pydantic pinned with it

`pymc-marketing` is pinned to the 0.19 series after its 0.20 line changed the MMM constructor,
and NumPy is held under 2.4 and pydantic under 2.12 because the first import failed on both
newer lines. The pins are in the `bayes` extra of `packages/mmm/pyproject.toml` and in the
workspace lock; the API image installs without the extra.

## 2026-09-27: the own backend was re-specified after it credited a channel with a return of seventy six to one

The first `own` fit put the ceiling of one channel's Hill curve far above anything the data
could support, because nothing bounded it and the intercept was free to go negative. The fix
was structural, not a prior: a non negative intercept, a log linear baseline (the exponential
of the controls) with media entering additively, bounded transform parameters, a coarse grid on
in sample error before Nelder-Mead on the forecast objective, a small shape penalty, and a
ridge on the seasonal terms. The simulator's competitor and sales noise were lowered at the
same time so the recovery study measured identification rather than noise. Notebook 01 keeps
the search that overfit the validation origins as its dead end.

## 2026-09-27: the bayes recovery runs three seeds per condition with two short chains

Sampling a national weekly model with seven channels takes about four minutes per fit here.
Six conditions at three seeds is eighteen fits, about an hour and a half, and the count is
stated on every bayes figure. Two chains of four hundred draws after four hundred tuning
draws, with divergences and the largest R hat recorded and a fit failing above twenty
divergences or an R hat of 1.05. Several fits sat above the library's warning level of 1.01
without crossing the ceiling; the cards say so.

## 2026-09-27: the API deploys from a Windows machine, and the verification runs there too

The build sandbox cannot reach Fly, Neon or the deployed API (its egress proxy refuses them),
so `deploy/deploy.ps1` runs the same steps as `deploy/deploy.sh` from Ajay's PC, reading the
secrets from a `.env` beside the repository and never committing them, and `deploy/verify.ps1`
performs the separate client check from the same machine. The response it saw is committed as
`results/deploy/verification.json` and rendered into the README through the manifest.

## 2026-09-27: the geo test is registered locally when the API is unreachable, under the same hash

The registry client tries the API and falls back to a local record with the same design hash
and the same timestamps, and records which path it took (`geo.registered_via`). The canonical
run in this build took the local path for the reason above. The design and its result can be
replayed to the live registry from a separate client after the fact; the record says
"replayed" when that happens, never "registered", because the order (register, then generate
the data) is what pre-registration means.

## 2026-09-27: a calibration run for one backend keeps the other backend's entries

`marginal calibrate --backends bayes` used to overwrite the calibration manifest and drop the
`own` half. The stage now carries over the entries of any backend it did not run from the
previous manifest, so the page shows both halves whatever order they ran in.

## 2026-09-28: Online Retail II's two sheets overlap, and the overlap is dropped once

Both sheets of the workbook hold the first nine days of December 2010. The first pass counted
those rows twice and inflated the holdout revenue of the lifetime value check. The loader now
tags each row with its sheet, drops the first sheet's copy of the overlap before any other
cleaning, and publishes the count (`data.retail.overlap_rows`). The calibration window was
unaffected, so the fitted parameters did not change; the holdout actuals did.

## 2026-09-28: a channel that cannot meet its allowance is held at its floor and labeled

Under the calibrated curves online video never pays back within its acquisition cost
allowance at any admissible spend, so the constraint made the whole plan infeasible and the
optimizer failed. Failing the plan over one channel hides the finding. The optimizer now probes
each channel's allowance across its box, holds a channel that cannot meet it at its floor,
labels it "allowance (infeasible)" in the allocation, and the page names it.

## 2026-09-28: lifetime value runs before the budget

The build order fits the purchase model after the optimizer, but the optimizer reads the
allowance the purchase model writes. The pipeline order in the registry, the Makefile and the
rederive script now run `clv` before `budget`, and a test holds the three to the same order.

## 2026-09-28: the Hillstrom targeting result stands as it came out

On the real test split the sure things rule earned more per thousand customers than either
uplift learner, and every Qini interval includes zero. The share was chosen on validation and
reported on test as the brief requires; nothing was retuned after seeing the test split, and
the pages say the learners lost. The simulator, where the effects are known, shows the learners
winning clearly, which is the point of grading on known truth first.

## 2026-09-28: the regret study judges the plan without the allowance

The allowance comes from a UK gift retailer's purchase history and applies to the
demonstration brand as a demonstration of the mechanism. The regret study's markets have no
purchase history of their own, so their plans are judged under floors, ceilings and the change
limit only. The demonstration plan carries the allowance; the study does not; both say so.

## 2026-09-28: the recorded session was recorded against a local server

The site's fallback bundle is a session recorded with `scripts/record_session.py` against the
same API code running on a local Postgres, because the live API is unreachable from the build
sandbox. It is labeled "recorded session" on every control it feeds, and the live API is used
whenever the health probe answers.

## 2026-09-28: the site decodes parquet with hyparquet and hands DuckDB-WASM Arrow tables

The DuckDB-WASM bundle the site pins ships without the parquet extension and would fetch it
from a third party host at runtime. The site reads each mart over HTTP byte ranges with
hyparquet, registers it in DuckDB as an Arrow table, and runs every query in DuckDB in a
worker, so no chart depends on a runtime download from anywhere but the site's own origin.

## 2026-09-28: the demo GIF is not built

The brief's demo recording is a stretch item. With the deploy, the site and the rederive ahead
of it in the day, the GIF was dropped and the Makefile target removed rather than left pointing
at a script that does not exist.
