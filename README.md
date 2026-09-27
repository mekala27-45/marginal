# marginal

Marketing measurement and growth analytics for Alderquist, a fictional direct to consumer
home goods brand: a market simulator with known truth, two marketing mix model backends
graded on that truth and calibrated by experiments, a geo lift test designed with power and
analyzed as pre-registered, a real randomized email experiment, uplift models evaluated on
randomized holdouts with a policy value curve, lifetime value with a holdout validation
feeding an acquisition cost allowance, attribution rules beside incremental truth, a
constrained budget optimizer that equalizes marginal returns, a plan and experiment
registry on a live API, a quarterly review memo rendered from the manifest, and a site.

Build in progress. Stage manifests present: data, simulate. The Criteo run
uses the full v2.1 release (13,979,592 rows), because the ten percent mirror no
longer exists; see `data/PROVENANCE.md`.

> Alderquist is a fictional direct to consumer home goods brand and its market is simulated with known truth. The email experiment is Kevin Hillstrom's public 2008 dataset, the purchase history is the UCI Online Retail II dataset, and the large uplift set is Criteo's public research release. No real company's spend and no real customer's identity appears here.
