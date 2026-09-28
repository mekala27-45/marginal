# Data provenance

Rendered from `results/manifest.json` by the claim gate; do not edit by hand.

Nothing raw is committed. `make data` looks for the three files under `data/external`,
downloads each one when its host answers, and verifies the checksum either way. The
committed folders `data/hillstrom`, `data/retail` and `data/criteo` hold derived
aggregates only, and the identifier scan fails the build if a raw header appears
anywhere published.

| Dataset | File | License | Published MD5 | SHA-256 (first 16) | Rows |
|---|---|---|---|---|---:|
| Hillstrom email experiment (MineThatData E-Mail Analytics and Data Mining Challenge, March 2008) | hillstorm_no_indices.csv.gz | Public challenge release without a formal license text | a68a81291f53a14f4e29002629803ba3 | bab6578f60db5d79 | 64,000 |
| Online Retail II (UCI Machine Learning Repository, dataset 502) | online+retail+ii.zip | CC BY 4.0 | none published | 572e36277c2390fb | 1,067,371 |
| Criteo Uplift Prediction Dataset v2.1 (Criteo AI Lab) | criteo-uplift-v2.1.csv.gz | CC BY-NC-SA 4.0 | d2236769ef69e9be52556110102911ec | 2716e1bf0fd157a9 | 13,979,592 |

Source: static, the three public releases, as of 2026-09-27.

## Hillstrom email experiment

- Source: https://hillstorm1.s3.us-east-2.amazonaws.com/hillstorm_no_indices.csv.gz
- Citation: Hillstrom, K. (2008). The MineThatData E-Mail Analytics and Data Mining Challenge. MineThatData blog.
- Terms: Public challenge release without a formal license text. Kevin Hillstrom released the file in March 2008
  for the MineThatData challenge with no formal license text. It is used here for a non
  commercial portfolio with attribution, through the scikit-uplift mirror, whose MD5
  (a68a81291f53a14f4e29002629803ba3) that project publishes.
- SHA-256 of the verified copy: `bab6578f60db5d792f1c2372c502f029152a5249cf5ea84390f3b7f885d7234f`
- Rows: 64,000 customers; arms of 21,306 (no email),
  21,307 (men's email) and 21,387 (women's email).
- Outcome window: two weeks. Population: recent buyers of a catalog retailer in 2008.
- Committed: `data/hillstrom/summary.json` (arm counts and outcome rates). The rows stay external.

## Online Retail II

- Source: https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip
- Citation: Chen, D. (2019). Online Retail II. UCI Machine Learning Repository. https://doi.org/10.24432/C5CG6D
- Terms: CC BY 4.0. The same source pricepoint (Day 2 of this series) priced;
  here it is the purchase history lifetime value is fit on.
- SHA-256 of the verified copy: `572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb` (the UCI page publishes no checksum;
  a different copy fails verification on purpose so the row counts below stay tied to this file).
- Rows: 1,067,371 transactions from 2009-12-01 to
  2011-12-09. The workbook's two sheets both hold 1 to 9 December 2010, so the
  first sheet's 22,523 rows for those days were dropped before anything
  else. Cleaning then removed 19,165 credit
  notes (invoices starting with C), 234,568 rows without a customer id
  (22.9% of the non credit rows) and 70
  non positive adjustments, leaving 791,045 rows,
  5,878 customers and 33,107 customer days.
- Windows: calibration to 2010-11-30, holdout from 2010-12-01.
- Committed: `data/retail/purchases.parquet` (customer id, day, revenue, lines) and `summary.json`.
  Customer ids are the dataset's own pseudonymous integers.

## Criteo Uplift Prediction Dataset

- Source: http://go.criteo.net/criteo-research-uplift-v2.1.csv.gz
- Citation: Diemert, E., Betlei, A., Renaudin, C., Amini, M. (2018). A Large Scale Benchmark for Uplift Modeling. AdKDD and TargetAd Workshop, KDD 2018.
- Terms: CC BY-NC-SA 4.0. Non commercial use with attribution; every derived table
  under `data/criteo` and `results/targeting` carries the same terms.
- Published MD5: d2236769ef69e9be52556110102911ec. SHA-256 of the verified copy: `2716e1bf0fd157a93b5bf86924d9088419dfbac2022c6cd90030220634f616dc`.
- Rows: 13,979,592, treated share 85.0%, visit rate
  4.70%, conversion rate 0.29%, exposure rate
  3.06%.
- Which release ran: the full v2.1 release, every row. The ten percent mirror the prompt named
  no longer exists (the scikit-uplift bucket answers NoSuchBucket), so the full file was fetched
  from Criteo AI Lab and verified against the MD5 scikit-uplift publishes for it.
- Committed: `data/criteo/summary.json`. The rows stay external.

> Alderquist is a fictional direct to consumer home goods brand and its market is simulated with known truth. The email experiment is Kevin Hillstrom's public 2008 dataset, the purchase history is the UCI Online Retail II dataset, and the large uplift set is Criteo's public research release. No real company's spend and no real customer's identity appears here.
