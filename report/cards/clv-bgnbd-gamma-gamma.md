# Model card: BG/NBD and Gamma-Gamma lifetime value

Rendered from `results/manifest.json` by the claim gate; do not edit by hand. The contract below
is the one `docs/models.md` sets out, and every figure is a manifest value or table.

## Intended use

BG/NBD predicts how many purchases a customer will make and whether they are still a customer;
Gamma-Gamma predicts how much they spend when they buy. Together they give each customer's
lifetime value over the next 12 months, and from it the acquisition
cost allowance: the most a channel may spend to acquire a customer, which the budget optimizer and
the API apply. The transactions are a UK online gift retailer's, largely wholesale customers, from
2009 to 2011, and Alderquist's market is simulated, so the allowance is a demonstration of the
mechanism, not a number for Alderquist. It is not meant for valuing Alderquist's customers, for
one customer's value (the holdout grades deciles and totals, not individuals), for customers the
model has not seen, or for pricing an acquisition before it is refit on the brand's own purchase
history.

## Data and population

Online Retail II from the UCI Machine Learning Repository: 1,067,371 transaction
lines from 2009-12-01 to 2011-12-09. After the sheet overlap
is dropped and credit notes, lines without a customer id and non positive adjustments are removed
(`data/PROVENANCE.md` has each count), 791,045 lines remain, from
5,878 customers over 33,107 customer days.
Source: real:retail, UK online gift retailer, 2009 to 2011, as of 2026-09-27.

The models are fit on the 4,266 customers who bought by 2010-11-30,
2,758 of them repeat buyers, and judged on what those customers did from
2010-12-01 to 2011-12-09. The 1,612
customers whose first purchase falls in the holdout are counted but not predicted, because the
models describe customers they have seen. The committed frame holds a pseudonymous customer id, a
day, revenue and lines, nothing else. Amounts are the retailer's own, in pounds sterling, printed
in the repository's dollar format. Source: real:retail, model bgnbd, 4,266 customers who bought by 2010-11-30 (of 5,878 in the file), calibration to 2010-11-30, as of 2026-09-27.

## How it was fit

Both models are written in the repository (`marginal_clv`) and fit by maximum likelihood on the
calibration window, with BFGS on the log parameters and the analytic gradient. BG/NBD took
43 evaluations and converged,
judged by the largest gradient component at the answer and not by the optimizer's flag alone. On this file its
likelihood has a long, nearly flat ridge along which a and b grow together, so the tolerance is
tight on purpose. Gamma-Gamma uses the repeat purchases of repeat customers only, and assumes that
spend per purchase does not depend on how often a customer buys; the correlation between the two
among repeat customers is 0.184, which does not rule the model out.

Lifetime value is the discounted expected revenue over 12 months at an
annual rate of 10%, computed at the calibration end from the
models the holdout judged, not refit on the whole file. The allowance is lifetime value times the
42% contribution margin times a payback share of
70%: per purchase frequency segment, overall, and per channel as a mix
weighted mean of the segment allowances. The channel mixes are stated assumptions in
`marginal_clv.value`, because the retail file records no channel. The budget optimizer turns a
channel's incremental revenue into customers at $443.24 per acquisition,
the mean revenue on a customer's first purchase day, and holds spend per customer under the
channel's allowance.

As a cross check, PyMC-Marketing fits the same two models to the same frame by maximum a posteriori
under flat priors.

## Metrics

The parameters, beside PyMC-Marketing's. The largest relative difference across them is
0.001%.

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

**The holdout.** The model expected 19,057 purchases in the
holdout and the customers made 12,835, a difference of
+48.5%; predicted revenue is $9,259,114.73
against $7,139,918.88, a difference of +29.7%.
The mean absolute error per customer is 2.59 purchases and
$1,365.09 of revenue. The over prediction comes from the dropout parameters: the
fitted chance that a customer stops buying after a purchase is 0.11%,
close to zero, so the model treats nearly every customer who went quiet as still active and keeps
predicting purchases for them. The tenth decile, the customers who bought most often in the
calibration window, is much closer: +11.6%.

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

Source: real:retail, model bgnbd, 4,266 customers who bought by 2010-11-30 (of 5,878 in the file), calibration to 2010-11-30, as of 2026-09-27. Deciles are of purchase frequency in the calibration window.

**Lifetime value** over the horizon has a mean of $2,014.33, a median of
$1,149.20 and a ninetieth percentile of $3,301.15 per customer.

**The allowance**, by segment and by channel:

| Segment | Customers | Mean lifetime value | Allowance |
|---|---:|---:|---:|
| One time (no repeat purchase) | 1,508 | $815.94 | $239.89 |
| Occasional (1 to 2 repeat purchases) | 1,371 | $1,246.01 | $366.33 |
| Regular (3 to 5 repeat purchases) | 778 | $2,055.69 | $604.37 |
| Frequent (6 or more repeat purchases) | 609 | $6,658.60 | $1,957.63 |
| All customers | 4,266 | $2,014.33 | $592.21 |

Source: real:retail, model bgnbd, 4,266 customers who bought by 2010-11-30 (of 5,878 in the file), calibration to 2010-11-30, as of 2026-09-27.

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

**Where it binds.** In the plan at last year's budget the allowance
binds on affiliate and promo codes, and it holds online video at the
lowest spend the constraints allow, -30.0% from last year, because that
channel's curve cannot meet its allowance of $517.73 at any spend
the constraints allow. Source: simulated, model optimizer, demonstration brand, calibrated own curves, condition rho 0.6, feedback on, seed 12, as of 2026-09-27.

## The integration contract

A ticked line is met. Any other line names what it is instead: partly met, not built, or not
applicable, with the reason.

- [ ] **trained** (partly): Fit in the pipeline (`make clv`) on the calibration window to 2010-11-30 and judged against what the same customers did in the holdout, with PyMC-Marketing as a cross check; no simpler benchmark, such as last year's purchases carried forward, was fit beside it.
- [x] **timed**: The calibration window ends 2010-11-30 and the holdout runs from 2010-12-01 to 2011-12-09; a test checks the two never overlap, and lifetime value is computed at the calibration end from the models the holdout judged.
- [ ] **calibrated** (partly): The holdout by decile checks predicted purchases and revenue against actual, and `results/clv/calibration_plot.parquet` makes the same check in bins of predicted purchases; the check shows an over prediction of +48.5%, and no interval is published for lifetime value or the allowance.
- [x] **useful**: It sets the acquisition cost allowance the plan and the API apply: lifetime value times the 42% margin times a payback share of 70%, $592.21 per customer overall.
- [ ] **fair** (partly): The frame holds a pseudonymous id, a day, revenue and lines, with no demographic field to check; the allowance differs by purchase frequency segment by design, and the channel mixes that weight the segments are stated, not measured.
- [ ] **gated** (partly): A fit whose maximum sits on the edge of the parameter space is not called converged (a test checks this), and the stage refuses an empty or overlapping window; a fit that does not converge is published with its flag rather than stopped.
- [ ] **served** (partly): The model is not served, its allowance is: the API reads `results/clv/allowance.json` and applies it in `/v1/optimize` and `/v1/plans` unless a request turns it off.
- [x] **integrated**: The budget stage and the API apply the allowance, the site's Budget page shows where it binds, and the quarterly review's lifetime value section quotes the holdout and the allowance.
- [ ] **monitored** (not built): There is no refit on new purchases and no check of the holdout error over time; the weekly refresh is a stretch goal.
- [x] **documented**: This card and `data/PROVENANCE.md`, rendered from the manifest by the claim gate.
- [x] **bounded**: The statement closes this card, and the intended use above says it plainly: the customers are a UK gift retailer's, the market they are applied to is simulated, and the allowance demonstrates the mechanism.
- [x] **validated**: Judged on the holdout year of the same customers, by decile of calibration frequency, and cross checked against PyMC-Marketing, never on the window it was fit on.
- [x] **explainable at the decision**: A reader sees the holdout by decile, the parameters beside PyMC-Marketing's, the lifetime value distribution, the allowance by segment and by channel, and in the plan the channels where it binds.

## Limitations

It over predicts: its holdout purchases are +48.5% against
what the customers bought, so every lifetime value and every allowance built on it leans
optimistic. A model in which customers can drop out between purchases, such as Pareto/NBD, is the
next thing to try.

The customers are a UK online gift retailer's, largely wholesale buyers, whose purchase rhythm and
basket sizes are not those of a direct to consumer home goods brand. The amounts are pounds
sterling, and the plan applies them to Alderquist's dollars one for one.

The channel allowances rest on segment mixes that are stated, not measured, and move one for one
with them. A segment is a customer's purchase frequency in the calibration window, which also
reflects how long they have been a customer; reading it as the kind of customer a channel acquires
is the simplification the mixes rest on.

No interval is published for lifetime value or the allowance.

> Alderquist is a fictional direct to consumer home goods brand and its market is simulated with known truth. The email experiment is Kevin Hillstrom's public 2008 dataset, the purchase history is the UCI Online Retail II dataset, and the large uplift set is Criteo's public research release. No real company's spend and no real customer's identity appears here.
