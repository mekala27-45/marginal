# Notebooks

> Alderquist is a fictional direct to consumer home goods brand and its market is simulated with known truth. The email experiment is Kevin Hillstrom's public 2008 dataset, the purchase history is the UCI Online Retail II dataset, and the large uplift set is Criteo's public research release. No real company's spend and no real customer's identity appears here.

Three notebooks, executed with their outputs saved. Each one simulates what it needs or reads the committed files under `data/sim` and `results`. None opens `data/external`, so CI runs them without the three public datasets.

| Notebook | What it shows | The dead end it keeps |
|---|---|---|
| `01_simulator_and_recovery.ipynb` | The demonstration market and its true response curves, how closely the channels' spend moves under three values of rho, `own` fit against the truth, and a three seed recovery study beside the published one | The transform search that overfit the validation origins |
| `02_lift_test_and_calibration.ipynb` | A geo lift test designed, registered by its plan hash, checked by the SRM gate and read by difference in differences and synthetic control; power by simulation; `own` calibrated by the result | The synthetic control that put all its weight on one geo |
| `03_uplift_and_policy_value.ipynb` | A T learner on simulated customers with known effects, read by Qini, PEHE and the quadrants; the policy value curve with its interior test; the published Hillstrom, simulator and Criteo results | The uplift model that beat random on the training split and lost on the test split |

Every number a notebook prints comes from that notebook's run and says how many seeds it rests on, and none is copied into a document. Published figures are read from `results/manifest.json` and printed with their provenance.

Run one from the repository root, or all three the way CI does:

```
uv run jupyter nbconvert --to notebook --execute --inplace notebooks/01_simulator_and_recovery.ipynb
uv run pytest --nbmake notebooks -p no:cacheprovider
```

The first notebook is the slowest: its recovery cell runs six full fits of `own`.
