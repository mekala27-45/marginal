"""The pipeline, one command per stage, in the order the Makefile runs them."""

from __future__ import annotations

import datetime as dt
import os

import typer
from marginal_core.paths import paths

app = typer.Typer(add_completion=False, help="marginal: marketing measurement for a fictional brand")

STAGES = (
    "data",
    "simulate",
    "recovery",
    "experiments",
    "calibrate",
    "budget",
    "targeting",
    "clv",
    "attribution",
    "manifest",
    "marts",
)

DEMONSTRATION_SEED = 12


def as_of() -> str:
    return os.environ.get("MARGINAL_AS_OF", dt.date.today().isoformat())


@app.command()
def data(no_download: bool = typer.Option(False, help="verify only, never try the hosts")) -> None:
    """Verify (and fetch when reachable) the three public datasets; write their summaries."""
    from marginal_registry.stages import data as stage

    manifest = stage.run(paths(), as_of(), DEMONSTRATION_SEED, attempt_download=not no_download)
    typer.echo(f"data: {manifest.counts()}")


@app.command()
def simulate() -> None:
    """The market with known truth for the demonstration seed."""
    from marginal_registry.stages import simulate as stage

    manifest = stage.run(paths(), as_of(), DEMONSTRATION_SEED)
    typer.echo(f"simulate: {manifest.counts()}")


@app.command()
def recovery(
    backend: str = typer.Option("own", help="own or bayes"),
    demo_only: bool = typer.Option(False, help="fit the demonstration brand only; keep the study on disk"),
) -> None:
    """The recovery study over seeds and conditions for one backend."""
    from marginal_registry.stages import recovery as stage

    manifest = stage.run(paths(), as_of(), DEMONSTRATION_SEED, backend=backend, demo_only=demo_only)
    typer.echo(f"recovery {backend}: {manifest.counts()}")


@app.command()
def experiments() -> None:
    """The geo lift test and the email experiment."""
    from marginal_registry.stages import experiments as stage

    manifest = stage.run(paths(), as_of(), DEMONSTRATION_SEED)
    typer.echo(f"experiments: {manifest.counts()}")


@app.command()
def calibrate() -> None:
    """The lift result into both backends; before and after."""
    from marginal_registry.stages import calibrate as stage

    manifest = stage.run(paths(), as_of(), DEMONSTRATION_SEED)
    typer.echo(f"calibrate: {manifest.counts()}")


@app.command()
def budget() -> None:
    """The constrained optimizer, the regret study and the precomputed surface."""
    from marginal_registry.stages import budget as stage

    manifest = stage.run(paths(), as_of(), DEMONSTRATION_SEED)
    typer.echo(f"budget: {manifest.counts()}")


@app.command()
def targeting() -> None:
    """Uplift models on Hillstrom, the simulator and Criteo."""
    from marginal_registry.stages import targeting as stage

    manifest = stage.run(paths(), as_of(), DEMONSTRATION_SEED)
    typer.echo(f"targeting: {manifest.counts()}")


@app.command()
def clv() -> None:
    """Lifetime value with the holdout and the allowance."""
    from marginal_registry.stages import clv as stage

    manifest = stage.run(paths(), as_of(), DEMONSTRATION_SEED)
    typer.echo(f"clv: {manifest.counts()}")


@app.command()
def attribution() -> None:
    """Six credit rules and Shapley beside the truth."""
    from marginal_registry.stages import attribution as stage

    manifest = stage.run(paths(), as_of(), DEMONSTRATION_SEED)
    typer.echo(f"attribution: {manifest.counts()}")


@app.command()
def manifest() -> None:
    """Merge every stage manifest into results/manifest.json."""
    from marginal_registry.stages import assemble

    merged = assemble.run(paths(), as_of(), DEMONSTRATION_SEED)
    typer.echo(f"manifest: {merged.counts()}")


@app.command()
def marts() -> None:
    """The DuckDB marts and the site bundle."""
    from marginal_registry.stages import marts as stage

    written = stage.run(paths())
    typer.echo(f"marts: {len(written)} files")


if __name__ == "__main__":
    app()
