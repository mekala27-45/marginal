"""The uplift learners, the sure things policy, and the split by customer.

Every model here is LightGBM on a stated feature set, single threaded and seeded, with small
trees by default (200 rounds at a learning rate of 0.05, 15 leaves, at least 200 customers per
leaf). The settings are deliberately modest. The outcomes are rare binary events and the
effects are a point or two of conversion, so deeper trees fit noise in each arm separately,
and the difference between two overfit arm models is mostly that noise.

Column wise histograms are forced and the deterministic flag is set because LightGBM otherwise
times row wise against column wise construction on each fit and keeps the faster, which can
change the trees between two runs of the same seed.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import polars as pl
from marginal_core.model import StrictModel
from marginal_core.seeds import rng, seeded_split

Flags = Sequence[int] | np.ndarray | pl.Series
"""A 0/1 vector: treatment flags or a binary outcome."""

SPLIT_SHARES = (0.6, 0.2, 0.2)
SPLIT_NAMES = ("train", "validation", "test")


class LearnerParams(StrictModel):
    """The LightGBM settings every model in this package shares."""

    n_estimators: int = 200
    learning_rate: float = 0.05
    num_leaves: int = 15
    min_child_samples: int = 200


def _model_seed(seed: int, *stream: str) -> int:
    """A LightGBM seed for one named model, so two models fit under one stated seed do not share it."""
    return int(rng(seed, "lightgbm", *stream).integers(0, 2**31 - 1))


def _settings(params: LearnerParams, seed: int) -> dict[str, Any]:
    return {
        "n_estimators": params.n_estimators,
        "learning_rate": params.learning_rate,
        "num_leaves": params.num_leaves,
        "min_child_samples": params.min_child_samples,
        "n_jobs": 1,
        "random_state": seed,
        "deterministic": True,
        "force_col_wise": True,
        "verbose": -1,
    }


# LightGBM is imported where a model is built, so the curves and metrics in this package (and
# the tests that need no model) work on a machine without it.


def _classifier(params: LearnerParams, seed: int) -> Any:
    from lightgbm import LGBMClassifier

    return LGBMClassifier(**_settings(params, seed))


def _regressor(params: LearnerParams, seed: int) -> Any:
    from lightgbm import LGBMRegressor

    return LGBMRegressor(**_settings(params, seed))


def feature_matrix(X: pl.DataFrame | np.ndarray, features: Sequence[str]) -> np.ndarray:
    """The stated features as a row major matrix.

    A frame is subset by name, so a column that is not in the stated set (the treatment flag,
    the outcome, the key) can never reach a model by accident. An array must already hold the
    stated features in the stated order; only its width can be checked.
    """
    if isinstance(X, pl.DataFrame):
        missing = [f for f in features if f not in X.columns]
        if missing:
            raise KeyError(f"the frame lacks the stated features {missing}")
        matrix = X.select(list(features)).to_numpy(order="c")
    else:
        matrix = np.asarray(X)
        if matrix.ndim != 2 or matrix.shape[1] != len(features):
            raise ValueError(
                f"expected a matrix of {len(features)} feature columns, got shape {matrix.shape}"
            )
    if matrix.dtype != np.float32:
        matrix = matrix.astype(np.float64, copy=False)
    if not np.all(np.isfinite(matrix)):
        raise ValueError("the feature matrix holds missing or infinite values")
    return np.ascontiguousarray(matrix)


def binary(values: Flags, name: str) -> np.ndarray:
    """A 0/1 vector as int8, refusing anything else rather than thresholding it silently."""
    array = values.to_numpy() if isinstance(values, pl.Series) else np.asarray(values)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one dimensional")
    if not np.isin(array, (0, 1)).all():
        raise ValueError(f"{name} must hold only 0 and 1")
    return array.astype(np.int8, copy=False)


def _arms(treated: np.ndarray, rows: int) -> tuple[np.ndarray, np.ndarray]:
    if treated.size != rows:
        raise ValueError(f"{treated.size} treatment flags for {rows} rows")
    t = treated == 1
    if t.all() or not t.any():
        raise ValueError("both arms need customers: an uplift model compares treated with control")
    return t, ~t


def _positive(model: Any, x: np.ndarray) -> np.ndarray:
    return np.asarray(model.predict_proba(x)[:, 1], dtype=np.float64)


class TLearner:
    """One outcome model per arm; the uplift is the difference of the two predicted probabilities.

    Simple and hard to get wrong, but each arm's model is fit on half the data and their errors
    do not cancel, so the difference is noisier than either model.
    """

    name = "t_learner"

    def __init__(self, features: Sequence[str], seed: int, params: LearnerParams | None = None) -> None:
        self.features = tuple(features)
        self.seed = seed
        self.params = params or LearnerParams()
        self._control: Any = None
        self._treated: Any = None

    def fit(self, X: pl.DataFrame | np.ndarray, treated: Flags, y: Flags) -> TLearner:
        x = feature_matrix(X, self.features)
        target = binary(y, "outcome")
        t, c = _arms(binary(treated, "treated"), x.shape[0])
        self._control = _classifier(self.params, _model_seed(self.seed, self.name, "control"))
        self._control.fit(x[c], target[c])
        self._treated = _classifier(self.params, _model_seed(self.seed, self.name, "treated"))
        self._treated.fit(x[t], target[t])
        return self

    def predict_uplift(self, X: pl.DataFrame | np.ndarray) -> np.ndarray:
        if self._control is None or self._treated is None:
            raise RuntimeError("fit the T learner before asking it for uplift")
        x = feature_matrix(X, self.features)
        return np.asarray(_positive(self._treated, x) - _positive(self._control, x))


class XLearner:
    """The two stage X learner of Kunzel, Sekhon, Bickel and Yu (2019).

    Stage one fits an outcome model per arm, as the T learner does. Each arm's customers then get
    an imputed effect from the other arm's model: a treated customer's outcome minus what the
    control model predicts for them, and the treated model's prediction for a control customer
    minus that customer's outcome. Stage two regresses the imputed effects on the features, once
    per arm, and the two effect models are blended with the propensity score as the weight on the
    control arm's model. Assignment is randomized, so the propensity is the treated share of the
    training split. The weighting puts most trust in the effect model whose imputations came from
    the better estimated outcome model, the one fit on the larger arm.
    """

    name = "x_learner"

    def __init__(self, features: Sequence[str], seed: int, params: LearnerParams | None = None) -> None:
        self.features = tuple(features)
        self.seed = seed
        self.params = params or LearnerParams()
        self.propensity: float | None = None
        self._effect_control: Any = None
        self._effect_treated: Any = None

    def fit(self, X: pl.DataFrame | np.ndarray, treated: Flags, y: Flags) -> XLearner:
        x = feature_matrix(X, self.features)
        target = binary(y, "outcome")
        t, c = _arms(binary(treated, "treated"), x.shape[0])
        outcome_control = _classifier(self.params, _model_seed(self.seed, self.name, "outcome_control"))
        outcome_control.fit(x[c], target[c])
        outcome_treated = _classifier(self.params, _model_seed(self.seed, self.name, "outcome_treated"))
        outcome_treated.fit(x[t], target[t])
        # Each arm is imputed from the model fit on the other arm, so no customer's own outcome
        # appears on both sides of its imputed effect.
        imputed_treated = target[t] - _positive(outcome_control, x[t])
        imputed_control = _positive(outcome_treated, x[c]) - target[c]
        self._effect_treated = _regressor(self.params, _model_seed(self.seed, self.name, "effect_treated"))
        self._effect_treated.fit(x[t], imputed_treated)
        self._effect_control = _regressor(self.params, _model_seed(self.seed, self.name, "effect_control"))
        self._effect_control.fit(x[c], imputed_control)
        self.propensity = float(t.mean())
        return self

    def predict_uplift(self, X: pl.DataFrame | np.ndarray) -> np.ndarray:
        if self.propensity is None:
            raise RuntimeError("fit the X learner before asking it for uplift")
        x = feature_matrix(X, self.features)
        tau_control = np.asarray(self._effect_control.predict(x), dtype=np.float64)
        tau_treated = np.asarray(self._effect_treated.predict(x), dtype=np.float64)
        return self.propensity * tau_control + (1.0 - self.propensity) * tau_treated


class SureThingsPolicy:
    """The policy most retailers run: contact the customers most likely to convert.

    One outcome model on every training customer, treatment ignored. It ranks by the probability
    of converting, which is not the probability of converting because of the email; the gap
    between the two is what the uplift learners are judged against.
    """

    name = "sure_things"

    def __init__(self, features: Sequence[str], seed: int, params: LearnerParams | None = None) -> None:
        self.features = tuple(features)
        self.seed = seed
        self.params = params or LearnerParams()
        self._model: Any = None

    def fit(self, X: pl.DataFrame | np.ndarray, y: Flags) -> SureThingsPolicy:
        x = feature_matrix(X, self.features)
        target = binary(y, "outcome")
        if target.size != x.shape[0]:
            raise ValueError(f"{target.size} outcomes for {x.shape[0]} rows")
        self._model = _classifier(self.params, _model_seed(self.seed, self.name))
        self._model.fit(x, target)
        return self

    def score(self, X: pl.DataFrame | np.ndarray) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("fit the sure things policy before scoring")
        return _positive(self._model, feature_matrix(X, self.features))


def split_customers(frame: pl.DataFrame, key: str, seed: int) -> pl.DataFrame:
    """Train, validation and test by customer, 60/20/20, one seeded draw per customer.

    seeded_split sorts on the key before it draws, so a query that returns the customers in a
    different order gives every customer the same split. The key must be unique: a customer on
    two rows could otherwise land in two splits and carry what the model learned into the test.
    Returns the frame sorted by the key with a `split` column.
    """
    if key not in frame.columns:
        raise KeyError(f"the frame has no key column {key!r}")
    if frame[key].n_unique() != frame.height:
        raise ValueError(f"{key} is not unique: the split is by customer, one row each")
    return seeded_split(frame, key, seed, SPLIT_SHARES, SPLIT_NAMES)
