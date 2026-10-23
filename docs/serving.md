# Serving: the API and the site

Rendered from `results/manifest.json` by the claim gate; do not edit by hand.

## The API

A FastAPI application (`packages/api/src/marginal_api/app.py`) that keeps the plan and experiment
registry in Postgres, runs the budget optimizer live on the served model, and lists the models on
disk. It is live at https://marginal-alderquist-api.vercel.app.

| Route | Token | What it does |
|---|---|---|
| `GET /v1/health` | no | Status, whether the database answers, the environment, and the model version it serves. |
| `GET /v1/models` | no | Every model export on disk (version, backend, spec hash, whether calibrated, data source, file) and which one is served. |
| `POST /v1/optimize` | no | A plan for a stated total budget and constraints, with the allowance unless turned off; not stored. |
| `POST /v1/plans` | yes | The same plan, stored with its model version, spec hash, inputs hash and expected profit with its interval. |
| `GET /v1/plans`, `GET /v1/plans/{plan_id}` | no | Stored plans, newest first, or one plan. |
| `POST /v1/experiments` | yes | Registers a design under its plan hash; the same design twice returns the same id. |
| `POST /v1/experiments/{experiment_id}/result` | yes | Posts a result against the registered plan hash; refused without a registered experiment or when the hash does not match. |
| `GET /v1/experiments`, `GET /v1/experiments/{experiment_id}` | no | Registered experiments with their results. |
| `GET /v1/audit` | no | The audit log, newest first. |
| `GET /v1/ping-db` | no | A bare database round trip. |

**The envelope.** Every response body, errors included, carries the statement and `served_at`, the
time the response was built. A test walks the route table, not a hand kept list, and fails if any
route's body lacks the statement (`tests/api/test_registry.py`).

**Token gated writes.** The three routes that store something need the write token as a bearer
token; without it the request is refused as unauthorized and nothing is written. The token is one
shared secret, set in the Vercel project settings and never committed. `/v1/optimize` stores nothing and needs no token.

**The audit row before the response.** Every write adds its row, then its audit row, then commits,
and only then builds the response, so a response can never exist without its audit record. Tests
read the rows back through a second database connection, never the application's own session, and
check that the audit row's time precedes the response's `served_at`.

**The out of process check.** `scripts/check_persistence.py --start-server` runs the migrations on
the database named by `MARGINAL_TEST_DATABASE_URL` (or `DATABASE_URL`), starts the API in a child
process against it, registers an experiment, posts a result and saves a plan over HTTP, then reads
all three back through a psycopg connection it opens itself. CI runs it on every push to main and
every pull request, against a fresh Postgres service. With `--base-url` the same check drives a live
server and reads back through the API's own GET routes.

**Vercel and Neon.** The API runs as a container function on the Vercel Hobby plan, built from
`Dockerfile.vercel`. That file is `Dockerfile.api` with one change: it serves on the port Vercel
sends traffic to. The image is Python 3.12 with the API package only (the bayes extra is left
out, so the image stays small) and copies the fitted exports it serves: `results/mmm`,
`results/calibrate`, `results/clv` and the experiment registry. On start it runs the migrations,
which do nothing after the first run, and then serves. Vercel starts an instance on the first
request after idle and scales back to zero, so that first request waits a second or so.

To set it up, import the repository in Vercel, pick the Container preset and point it at
`Dockerfile.vercel`. `DATABASE_URL`, `MARGINAL_WRITE_TOKEN` and `MARGINAL_CORS_ORIGINS` go in the
project's environment variables, never in the repository. The database is Postgres on Neon. Every
push to main redeploys.

`fly.toml`, `deploy/deploy.sh` and `deploy/deploy.ps1` are the former Fly route, kept for history.
The Fly account now asks for a card, so the API moved; `DECISIONS.md` has the reasons.

**What is served.** The API loads `results/calibrate/own_calibrated_model.json` when the calibration
stage has run, and `results/mmm/own_model.json` otherwise, and names the one it loaded in
`/v1/health`. The calibrated export in this build is `own-0c071596-calibrated`.

## The separate client verification

`results/deploy/verification.json` records a check of the live URL from a Windows machine running
PowerShell, outside the build sandbox and outside Vercel, made with `deploy/verify.ps1`. It found the
health route ok and the database ok; registered a verification experiment and posted a result
against its plan hash; saved a plan; read the experiment, its result and the plan back through the
API; found the registration's audit row timed before the response's `served_at`; found the
statement in the body; and passed.

The model version `/v1/health` named at that check (2026-10-23T17:56:55.3504903Z) was
`own-0c071596-calibrated`. The experiment the check registered was a verification experiment
with its own plan hash, not the geo lift design: in this build the design (plan hash
`53733a76fe1af6ec`) and its result were registered locally, because the build sandbox could
not reach the API. The same design and result were then replayed to the live registry from a
separate client (replayed, 2026-10-23T17:56:58.5704445Z, experiment
`076102e0-ebd0-5218-8433-fab40b6cff08`, plan hash matches: yes), and
the verification's own rows were removed afterwards by `deploy/reset-registry.ps1`, which leaves
the audit log alone (`results/deploy/reset.json`).

## The site

A Next.js 15 static export served by GitHub Pages under `/marginal`, with six pages: Overview, Mix,
Budget, Experiments, Targeting and Report. Everything a page shows comes from `web/public/data`,
written by `make marts` and committed; the site never recomputes it.

- **The marts.** Every chart is a query over a parquet file in `web/public/data`, run in the browser
  by DuckDB-WASM in a worker that starts after the first paint. Printed figures come from the
  manifest copied beside the marts, through a formatter that mirrors `marginal_core.formats`.
- **The live API.** The Budget and Experiments pages call the API named at build time by the
  `MARGINAL_API_URL` repository variable, and the Vercel address when it is empty. The first call
  probes `/v1/health` and gives up after a few seconds.
- **The recorded session.** If the API is asleep or unreachable, those pages answer for the rest of
  the visit from `web/public/data/recorded_session.json`, a session recorded by
  `scripts/record_session.py` against the API running locally on a Postgres database, not against
  the live URL. The budget slider then reads the precomputed surface, labelled "precomputed", and a
  saved plan shows the recorded save, labelled "recorded". A chip beside each affected control says
  which source it is using.
- **Saving a plan** from the site needs the write token, typed beside the button and held in memory
  only.

## What is not built

- **Authentication beyond the token.** There are no users, roles or per client keys; one shared
  token gates every write, and reads are open.
- **A warm instance.** The function scales to zero when idle, so the first request after a quiet
  spell waits for a cold start; the site falls back to the recording if it waits too long.
- **Rate limiting.** None, on any route.
- **A scheduled refresh.** Nothing refits or re-records on a schedule.

> Alderquist is a fictional direct to consumer home goods brand and its market is simulated with known truth. The email experiment is Kevin Hillstrom's public 2008 dataset, the purchase history is the UCI Online Retail II dataset, and the large uplift set is Criteo's public research release. No real company's spend and no real customer's identity appears here.
