# Experiments

Rendered from `results/manifest.json` by the claim gate; do not edit by hand.

Two experiments run in this build, in the order a measurement team works: design first, power
before data, registration of the design's hash before a single outcome is read, the sample ratio
gate, and only then the analysis, posted against the hash it was registered under.

## The geo lift test

**Design.** The test switches display and retargeting off, a spend change of
-100.0%, in 10 of the 40 simulated geos for
8 weeks, weeks 148 to 155 of the panel.
The other 30 geos are controls, and the 52 weeks
before the test are the pre period. Assignment is stratified: the geos are sorted by pre period
sales, cut into strata of four, and one geo is drawn from each, so the treated group spans the size
distribution. The treated geos are 5, 8, 9, 11, 16, 19, 20, 21, 34, 35. The channel is the one whose spend
follows last week's demand in the simulator, and the one every attribution rule over credits.

**Power by simulation.** Before the test's weeks are read, each candidate design is run on
60 fresh simulated markets from the same specification with the test
applied, and power is the share of runs whose difference in differences interval excludes zero.
The design above has power of 100% at the true effect; the table shows
how power falls when the test removes less of the channel's spend or runs for fewer weeks.

| Spend removed | Test length (weeks) | Simulations | Power | Mean true lift |
|---:|---:|---:|---:|---:|
| 100% | 4 | 60 | 100% | $76,605 |
| 100% | 8 | 60 | 100% | $152,790 |
| 50% | 4 | 60 | 100% | $41,681 |
| 50% | 8 | 60 | 100% | $87,706 |
| 25% | 4 | 60 | 57% | $18,820 |
| 25% | 8 | 60 | 88% | $39,852 |

Source: simulated, model did, 10 treated geos of 40, 8 weeks, condition rho 0.6, feedback on, seed 12, as of 2026-09-27.

**Pre-registration.** The design (units, assignment, channel, spend change, window, primary outcome
and analysis plan) is hashed with `marginal_core.hashing.design_hash` and registered before the
test's data is read: plan hash `53733a76fe1af6ec`, experiment id `076102e0-ebd0-5218-8433-fab40b6cff08`,
registered at 2026-09-27T21:45:07+00:00. Changing any part of the design changes the hash, and a
result can only be posted against the hash that was registered. In this build the registration and
the result went to the local registry, `results/experiments/registry.json`, because the build
sandbox could not reach the live API. The registry records the route each one took:
`local` for the registration and `local` for the result.

**The sample ratio gate.** A chi square test of the observed treated and control counts against the
planned ratio; no result is shown while it fails at p below 0.001, and the gate
refuses to pass on an empty assignment. Here it passed (p = 1.000).

**Difference in differences** on log sales with geo and week fixed effects, standard errors
clustered by geo, gives a change of
-0.0317 in log sales in the treated geos over the window, which is
$169,063 of revenue the channel caused there (standard error
$10,624, interval $151,588 to $186,538).

**Synthetic control** builds each treated aggregate from a weighted set of control geos fit on the
pre period (root mean squared error on the weekly pre period $3,052, largest
weight 16%) and reads the gap in the window: $167,952
($131,871 to $206,046). Inference is by placebo: the fit is repeated
200 times with groups of control geos of the same size in place of the
treated ones, the p value is the share of placebos with a gap at least as large
(0.000), and the interval is the placebo distribution around the estimate.

**Against the truth.** The simulator knows the true lift, $150,478. Difference in
differences is off by +12.4% and its interval misses
the truth; synthetic control is off by +11.6% and its interval
covers it. The difference in differences result is
the one posted and used to calibrate both mix models ($169,063, standard
error $10,624); `docs/evaluation.md` grades what that did.

| Method | Estimate | Lower | Upper | Truth (simulated) | Covers | Error |
|---|---:|---:|---:|---:|---|---:|
| Difference in differences | $169,063 | $151,588 | $186,538 | $150,478 | no | +12.4% |
| Synthetic control | $167,952 | $131,871 | $206,046 | $150,478 | yes | +11.6% |

Source: simulated, model did, 10 treated geos of 40, 8 weeks, condition rho 0.6, feedback on, seed 12, as of 2026-09-27.

## The registry

The API keeps the registry in Postgres. Writes need the token; reads do not.

| Route | What it does |
|---|---|
| `POST /v1/experiments` | Registers a design under its plan hash. Registering the same design twice returns the same experiment id. |
| `POST /v1/experiments/{experiment_id}/result` | Posts a result against the registered plan hash; refused when no experiment has that id, when the experiment has no plan hash, or when the hash does not match. |
| `GET /v1/experiments` | Every registered experiment with its results. |
| `GET /v1/experiments/{experiment_id}` | One experiment with its results. |
| `GET /v1/audit` | The audit log; every write adds its row there before its response is sent. |

When the API does not answer, the pipeline registers locally and says so in the registry file, as
it did in this build. The site's recorded session (`web/public/data/recorded_session.json`)
replays this design and its difference in differences result through the API code running against
a local Postgres, and a separate Windows client checked the live registry with its own verification
experiment (`docs/serving.md`). No record in the repository shows this design registered on the live
registry itself.

## The email experiment (Hillstrom)

Kevin Hillstrom's MineThatData file is a real randomized test: 64,000 recent
buyers of a catalog retailer, assigned in equal thirds to no email
(21,306), a men's merchandise email (21,307) or a women's
merchandise email (21,387) in 2008, with visits, conversions and spend recorded
over the 14 days that followed. The design was hashed and registered before
the analysis ran (plan hash `1a44a33031e3de84`, through the `local`
route), with the men's email as the primary arm and the correction for segments stated in advance.

The sample ratio gate passed (p = 0.904). Effects are treated minus
control with 90% intervals. The men's email raised conversion by
0.68% of customers (0.53% to
0.83%) and spend by $0.77 per customer
($0.53 to $1.01); at a 30%
margin on that spend and $0.12 per email, each email earned
$0.11. The women's email earned $0.01.

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

**Segments, with Benjamini-Hochberg.** The effect is estimated in each of the
7 purchase history segments, and the p values are corrected
by Benjamini-Hochberg across segments at the false discovery rate set in `marginal_experiments.email`.
On conversion 6 of the
7 segments stay significant after the correction; on spend,
5.

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

The targeting models built on this experiment, and why they did not beat a simple rule on it, are
in `report/cards/uplift-t-learner.md` and `report/cards/uplift-x-learner.md`.

> Alderquist is a fictional direct to consumer home goods brand and its market is simulated with known truth. The email experiment is Kevin Hillstrom's public 2008 dataset, the purchase history is the UCI Online Retail II dataset, and the large uplift set is Criteo's public research release. No real company's spend and no real customer's identity appears here.
