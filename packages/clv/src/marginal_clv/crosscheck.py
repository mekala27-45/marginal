"""A cross check of the repository's BG/NBD and Gamma-Gamma fits against PyMC-Marketing.

PyMC-Marketing's BetaGeoModel and GammaGammaModel are fit to the same frame by MAP
(pymc.find_MAP). Two settings make that MAP the maximum likelihood estimate the repository
computes, so the check compares implementations rather than modelling choices:

  every parameter gets a HalfFlat prior. The library's default BG/NBD priors are informative
  (Weibull on r and alpha, a Beta mean and a Pareto concentration behind a and b) and would pull
  the MAP away from the maximum of the likelihood. find_MAP leaves out the log Jacobian of the
  log transform, so under flat priors its answer is the maximum likelihood estimate.

  the optimizer's tolerances are tightened to the repository's level. BG/NBD's likelihood has
  the flat ridge in a and b that marginal_clv.bgnbd describes, and at scipy's default tolerances
  the library stops on it (on the retail file, a and b about 1.5 percent short of the optimum):
  a difference in stopping rules, not in the models.

The record gives each parameter from both fits, their largest relative difference, and each
model's log likelihood gap: the repository's log likelihood at its own estimates minus at the
library's, both computed by the repository. A gap near zero beside a visible parameter
difference means both fits sit on the same flat stretch of the likelihood; a clearly positive
gap means the library stopped short, a negative one that the repository did.

The library is imported inside the function, so marginal_clv works without it; the record then
says available=False and why.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd
import polars as pl
from marginal_core.model import StrictModel

from marginal_clv.bgnbd import BGNBD
from marginal_clv.bgnbd import PARAMETERS as BGNBD_PARAMETERS
from marginal_clv.gamma_gamma import PARAMETERS as GAMMA_GAMMA_PARAMETERS
from marginal_clv.gamma_gamma import GammaGamma

FRAME_COLUMNS = ("customer_id", "frequency", "recency", "T", "monetary")
MAP_SETTINGS: dict[str, Any] = {
    "options": {"ftol": 1e-15, "gtol": 1e-10, "maxiter": 5000},
    "maxeval": 20000,
}
METHOD = "MAP by pymc.find_MAP (L-BFGS-B), HalfFlat priors on every parameter, tolerances tightened"


class ParameterComparison(StrictModel):
    model: str
    parameter: str
    repository: float
    pymc: float | None
    relative_difference: float | None


class CrossCheck(StrictModel):
    available: bool
    reason: str | None
    library_version: str | None
    method: str
    customers: int
    repeat_customers: int
    parameters: list[ParameterComparison]
    max_relative_difference: float | None
    bgnbd_log_likelihood_gap: float | None
    gamma_gamma_log_likelihood_gap: float | None
    seconds: float | None


def _point(model: Any, names: tuple[str, ...]) -> dict[str, float]:
    """The MAP estimate of each named parameter from a fitted library model."""
    idata = model.idata
    if idata is None:
        raise RuntimeError("the PyMC-Marketing model returned no inference data")
    return {name: float(np.asarray(idata.posterior[name]).reshape(-1)[0]) for name in names}


def cross_check(
    frame: pl.DataFrame, bgnbd: BGNBD | None = None, gamma_gamma: GammaGamma | None = None
) -> CrossCheck:
    """Fit PyMC-Marketing to ``frame`` and compare its estimates with the repository's.

    ``frame`` is an rfm_frame. The repository's models are fit here when not passed in.
    """
    missing = [c for c in FRAME_COLUMNS if c not in frame.columns]
    if missing:
        raise KeyError(f"the cross check needs {missing}")
    bg = bgnbd if bgnbd is not None else BGNBD().fit(frame["frequency"], frame["recency"], frame["T"])
    gg = gamma_gamma if gamma_gamma is not None else GammaGamma().fit(frame["frequency"], frame["monetary"])
    repeat = frame.filter(pl.col("frequency") > 0)
    repository = [("bgnbd", name, value) for name, value in bg.params.items()] + [
        ("gamma_gamma", name, value) for name, value in gg.params.items()
    ]

    try:
        import pymc_marketing
        from pymc_extras.prior import Prior
        from pymc_marketing.clv import BetaGeoModel, GammaGammaModel
    except ImportError as exc:
        return CrossCheck(
            available=False,
            reason=f"PyMC-Marketing is not importable: {exc}",
            library_version=None,
            method=METHOD,
            customers=frame.height,
            repeat_customers=repeat.height,
            parameters=[
                ParameterComparison(model=m, parameter=n, repository=v, pymc=None, relative_difference=None)
                for m, n, v in repository
            ],
            max_relative_difference=None,
            bgnbd_log_likelihood_gap=None,
            gamma_gamma_log_likelihood_gap=None,
            seconds=None,
        )

    started = time.perf_counter()
    # Built from numpy columns so the conversion does not depend on pyarrow.
    rfm = pd.DataFrame(
        {
            "customer_id": frame["customer_id"].to_numpy(),
            "frequency": frame["frequency"].to_numpy().astype(np.float64),
            "recency": frame["recency"].to_numpy().astype(np.float64),
            "T": frame["T"].to_numpy().astype(np.float64),
        }
    )
    spend = pd.DataFrame(
        {
            "customer_id": repeat["customer_id"].to_numpy(),
            "frequency": repeat["frequency"].to_numpy().astype(np.float64),
            "monetary_value": repeat["monetary"].to_numpy().astype(np.float64),
        }
    )
    flat_bg = {name: Prior("HalfFlat") for name in BGNBD_PARAMETERS}
    bg_model = BetaGeoModel(model_config=flat_bg)
    bg_model.fit(data=rfm, method="map", progressbar=False, **MAP_SETTINGS)
    flat_gg = {name: Prior("HalfFlat") for name in GAMMA_GAMMA_PARAMETERS}
    gg_model = GammaGammaModel(model_config=flat_gg)
    gg_model.fit(data=spend, method="map", progressbar=False, **MAP_SETTINGS)
    seconds = time.perf_counter() - started

    library_bg = _point(bg_model, BGNBD_PARAMETERS)
    library_gg = _point(gg_model, GAMMA_GAMMA_PARAMETERS)
    library = {"bgnbd": library_bg, "gamma_gamma": library_gg}
    rows = [
        ParameterComparison(
            model=m,
            parameter=n,
            repository=v,
            pymc=library[m][n],
            relative_difference=abs(library[m][n] - v) / abs(v),
        )
        for m, n, v in repository
    ]
    at_library_bg = BGNBD(r=library_bg["r"], alpha=library_bg["alpha"], a=library_bg["a"], b=library_bg["b"])
    at_library_gg = GammaGamma(p=library_gg["p"], q=library_gg["q"], v=library_gg["v"])
    x, t_x, age, monetary = frame["frequency"], frame["recency"], frame["T"], frame["monetary"]
    bg_gap = bg.log_likelihood(x, t_x, age) - at_library_bg.log_likelihood(x, t_x, age)
    gg_gap = gg.log_likelihood(x, monetary) - at_library_gg.log_likelihood(x, monetary)
    return CrossCheck(
        available=True,
        reason=None,
        library_version=str(pymc_marketing.__version__),
        method=METHOD,
        customers=frame.height,
        repeat_customers=repeat.height,
        parameters=rows,
        max_relative_difference=max(r.relative_difference for r in rows if r.relative_difference is not None),
        bgnbd_log_likelihood_gap=bg_gap,
        gamma_gamma_log_likelihood_gap=gg_gap,
        seconds=round(seconds, 1),
    )
