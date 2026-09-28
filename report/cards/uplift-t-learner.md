# Model card: the T learner for email targeting

Rendered from `results/manifest.json` by the claim gate; do not edit by hand. The contract below
is the one `docs/models.md` sets out, and every figure is a manifest value or table.

## Intended use

The T learner ranks customers by how much a marketing contact changes their chance of
converting, so that a campaign can contact the customers the message moves and leave alone the ones
who would buy anyway, the ones who will not buy either way and the ones it puts off. With the policy
value curve it chooses how many to contact: the share where profit per thousand customers on the
list peaks. It is meant for one decision, whether to send one marketing contact to a customer, on
data from a randomized holdout it can learn from. It is not meant for any other decision about a
person, for Alderquist's customers before it has been fit and graded on an Alderquist holdout, for a
channel with no randomized holdout to learn from, or for pricing ad exposure on Criteo, which
publishes no costs.

## Data and population

Three datasets, each split by customer into training, validation and test shares of
60%, 20% and 20%
with one seeded draw per customer, so no customer sits in two splits.

- **Hillstrom**: the men's merchandise email against no email, outcome conversion in the two weeks after the email; the women's arm is
  dropped. 25,470 customers to fit on, 8,583 to choose on
  and 8,560 to report on. Features: recency, purchase history in dollars, whether
  the customer bought men's or women's merchandise, whether they are new, zip code class and purchase
  channel. Source: real:hillstrom, 64,000 recent buyers, 2008, as of 2026-09-27.
- **The simulator**: 200,000 simulated customers under a randomized email, where both
  potential outcomes are known (119,603 to fit on,
  40,162 to choose on, 40,235 to report on).
  Features: recency, frequency, spend, tenure, category affinity, engagement, region and the share of
  visits on mobile. The true average effect is 4.48%, and
  15.1% of customers have a true effect below zero: the email
  makes them less likely to buy. Source: simulated, 200,000 customers, demonstration seed, seed 12, as of 2026-09-27.
- **Criteo**: the full v2.1 release, 13,979,592 rows with a treated share of
  85.0%, outcome visit (conversion is too rare to rank on). The learners are fit
  on a seeded 2,000,000 of the 8,388,844
  training rows; the 2,796,858 validation and
  2,793,890 test rows are scored whole. Features: the twelve anonymized fields
  the release carries. Source: real:criteo, the full v2.1 release, as of 2026-09-27.

## How it was fit

The T learner fits one outcome model per arm, one on the customers who were contacted and one on
those who were not, and scores each customer by the difference between the two predicted chances
of converting (`marginal_targeting.learners.TLearner`). It is simple and hard to get wrong, but each
arm's model sees only its own arm, and the two models' errors do not cancel, so the difference is
noisier than either model.

Every model is LightGBM, single threaded and seeded, with small trees:
200 rounds at a learning rate of 0.05,
15 leaves and at least 200
customers per leaf. The settings are modest on purpose: the outcomes are rare and the effects are a
point or two of conversion, so deeper trees fit noise in each arm (`marginal_targeting.learners`).

The protocol is the same on every dataset (`marginal_targeting.protocol`): fit on the training split
alone; on the validation split, choose the share to contact where profit per thousand customers on
the list peaks, on a grid from 5% to 100%
in steps of 5%; report every published figure from the test split,
scored once. Qini intervals come from a paired bootstrap of 200
replicates at 90%, every policy scored on the same resampled customers. The
chosen share must pass the interior test: strictly inside the grid, with the curve lower on both
sides, or the page calls the operating point degenerate. Profit on Hillstrom is the spend the email
causes at a 30% margin less $0.12
per email; on the simulator, $55 per conversion at a
42% margin less $0.12; on Criteo, incremental
visits with no cost. The Criteo run took 286 seconds against a budget of
900.

## Metrics

The T learner on each test split, beside emailing everyone. Values are per thousand customers
on the list: incremental profit in dollars on Hillstrom and the simulator, incremental visits on
Criteo. The chosen share is read on the validation split.

| Dataset | Qini coefficient | Qini interval | Top decile uplift | Chosen share | Operating point | Value on test | Everyone on test |
|---|---:|---:|---:|---:|---|---:|---:|
| Hillstrom | -0.109 | -1.197 to 0.941 | 0.59% | 95.0% | interior | $188 | $202 |
| Simulator | 8.924 | 7.627 to 10.030 | 9.83% | 80.0% | interior | $893 | $879 |
| Criteo v2.1 | 3.428 | 3.209 to 3.619 | 5.69% | 100.0% | degenerate | 10.4 | 10.4 |

Source: real:hillstrom, model t_learner, Hillstrom men's email against no email, test split of 8,560 customers (models fit on 25,470, shares chosen on 8,583), as of 2026-09-27.
Source: simulated, model t_learner, simulated customers, randomized email, test split of 40,235 (models fit on 119,603, shares chosen on 40,162), seed 12, as of 2026-09-27.
Source: real:criteo, model t_learner, Criteo v2.1, every row: test split of 2,793,890 users (models fit on a seeded 2,000,000 of 8,388,844 training rows, shares chosen on 2,796,858), as of 2026-09-27.

Why each operating point is what it is: on Hillstrom, the curve peaks at 95% and is lower at 90% and at 100%; on
the simulator, the curve peaks at 80% and is lower at 75% and at 85%; on Criteo,
the chosen share, 100%, is the largest on the grid: the curve is still rising where the list runs out.

**On Hillstrom**, the real randomized test, the T learner earned
$188 per thousand customers on test against
$207 for the sure things rule and
$202 for emailing everyone: it did not beat
the rule, and its Qini interval includes zero. The paired
differences, the same customers resampled for every policy:

| Comparison | Difference | Lower | Upper |
|---|---:|---:|---:|
| T learner minus X learner | 0.002 | -0.616 | 0.567 |
| T learner minus Sure things | -0.300 | -1.360 | 0.829 |
| X learner minus Sure things | -0.301 | -1.407 | 0.948 |

Source: real:hillstrom, Hillstrom men's email against no email, test split of 8,560 customers (models fit on 25,470, shares chosen on 8,583); T and X learners, the sure things rule and everyone, as of 2026-09-27.

**On the simulator**, where the true effect of the email on every customer is known, the error in
predicted uplift (PEHE) is 0.024 against an average true effect of
4.48%. At its chosen share the T learner contacts
96.6% of the persuadables and
11.4% of the sleeping dogs, and leaves
81 of the 1,843 conversions an
oracle would collect on the table, against 167 for emailing everyone.

| Policy | Share contacted | Persuadables | Sure things | Lost causes | Sleeping dogs | Regret (conversions) |
|---|---:|---:|---:|---:|---:|---:|
| T learner | 80.0% | 96.6% | 71.5% | 80.1% | 11.4% | 81 |
| X learner | 85.0% | 99.1% | 79.6% | 85.0% | 8.4% | 30 |
| Sure things | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 167 |
| Everyone | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 167 |
| Oracle (known truth) | 4.6% | 100.0% | 0.0% | 0.0% | 0.0% | 0 |

Source: simulated, simulated customers, randomized email, test split of 40,235 (models fit on 119,603, shares chosen on 40,162); the oracle contacts exactly the persuadables, seed 12, as of 2026-09-27.

| Comparison | Difference | Lower | Upper |
|---|---:|---:|---:|
| T learner minus X learner | -1.223 | -1.653 | -0.788 |
| T learner minus Sure things | 10.213 | 8.210 | 11.907 |
| X learner minus Sure things | 11.437 | 9.594 | 13.058 |

Source: simulated, simulated customers, randomized email, test split of 40,235 (models fit on 119,603, shares chosen on 40,162); T and X learners, the sure things rule and everyone, seed 12, as of 2026-09-27.

**On Criteo**, with no cost per contact, the policy value keeps rising to the end of the list, so a
ranking that beats random still chooses 100.0% of it.
The paired differences:

| Comparison | Difference | Lower | Upper |
|---|---:|---:|---:|
| T learner minus X learner | -0.279 | -0.483 | -0.094 |
| T learner minus Sure things | -0.201 | -0.443 | -0.010 |
| X learner minus Sure things | 0.077 | -0.132 | 0.255 |

Source: real:criteo, Criteo v2.1, every row: test split of 2,793,890 users (models fit on a seeded 2,000,000 of 8,388,844 training rows, shares chosen on 2,796,858); T and X learners, the sure things rule and everyone, as of 2026-09-27.

## The integration contract

A ticked line is met. Any other line names what it is instead: partly met, not built, or not
applicable, with the reason.

- [x] **trained**: Fit in the pipeline (`make targeting`) on each dataset's training split (60% of customers, split by customer with one seeded draw), against two baselines that are not straw men: the sure things rule and emailing everyone.
- [x] **timed**: The features describe each customer before the contact and the outcome follows it (on Hillstrom, conversion in the two weeks after the email); the share is chosen on validation before the test split is scored, once, and the manifest is as of 2026-09-27.
- [ ] **calibrated** (partly): Its scores are rankings, not calibrated probabilities; the Qini coefficient carries a paired bootstrap interval at 90% on each test split, and on the simulator the predicted uplift is checked against the true effect (PEHE 0.024).
- [x] **useful**: It picks who gets the email: the share contacted is chosen where profit peaks on validation, at $0.12 per email and a 30% margin on the spend it causes on Hillstrom; Criteo carries no cost, so there it only ranks.
- [ ] **fair** (not built): None of the features is a protected attribute, but zip code class on Hillstrom and region on the simulator can stand in for one, and the build did not compare who is contacted across them.
- [ ] **gated** (partly): The protocol refuses to choose a share on the test or the training split and refuses an outcome that is not binary, and the interior test marks an operating point on the edge of the grid as degenerate; no bound on the fit's quality fails it.
- [ ] **served** (not served): The API has no targeting route; the scores live in `results/targeting` and the site's marts.
- [x] **integrated**: The site's Targeting page reads its Qini and policy value curves and the quadrant table from the marts, and the quarterly review quotes its test split figures.
- [ ] **monitored** (not built): There is no scheduled refit and no check on how its ranking holds up over time; the run's steps are logged in `logs/targeting.log`.
- [x] **documented**: This card and `docs/evaluation.md`, rendered from the manifest by the claim gate.
- [x] **bounded**: The statement closes this card: Hillstrom and Criteo are public research releases and the simulated customers are generated, so no real customer of Alderquist is scored.
- [x] **validated**: Graded on randomized holdouts, the Hillstrom and Criteo test splits scored once, and on the simulator's known effects, never on the data it was fit on.
- [x] **explainable at the decision**: A reader sees the Qini curve with its bootstrap band, the policy value curve by share with the chosen share and its interior test, the top decile uplift, and on the simulator which quadrants the list reaches.

## Limitations

On the one real randomized test it has not shown it can rank: on Hillstrom it
earned less than the sure things rule and its Qini interval includes zero.
The evidence that it works comes from the simulator, where the effects were written to be found.

Hillstrom's features are few and coarse, and its effects are a point or less of conversion, so a
test split of 8,560 customers carries more noise than the differences between
policies: emailing everyone, which ranks no one, earns $83
on validation and $202 on test.

On Criteo the chosen share is 100.0%, a degenerate
operating point, because the release carries no cost per contact; the ranking is tested there, the
decision is not.

Its score is the difference of two separately fit models, so the noise in each arm's model lands in
the ranking. On Criteo it ranks below the X learner and below the sure things rule by paired
difference, and on the simulator its PEHE is 0.024 against the X
learner's 0.016.

The build did not check who it contacts across zip code classes or regions, and it is not served.

> Alderquist is a fictional direct to consumer home goods brand and its market is simulated with known truth. The email experiment is Kevin Hillstrom's public 2008 dataset, the purchase history is the UCI Online Retail II dataset, and the large uplift set is Criteo's public research release. No real company's spend and no real customer's identity appears here.
