"""Stage: targeting. Written at its step in the build order."""

from __future__ import annotations

from marginal_core.manifest import Manifest
from marginal_core.paths import Paths


def run(paths: Paths, as_of: str, seed: int, **options: str) -> Manifest:
    raise NotImplementedError("the targeting stage is built at its step in the build order")
