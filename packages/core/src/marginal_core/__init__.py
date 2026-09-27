"""Shared models, formats, statements, hashing, paths and the manifest for marginal."""

from marginal_core.config import CHANNEL_LABELS, CHANNELS, POLICY, Policy
from marginal_core.manifest import Manifest
from marginal_core.model import MutableStrictModel, StrictModel
from marginal_core.statements import BRAND, STATEMENT

__all__ = [
    "BRAND",
    "CHANNELS",
    "CHANNEL_LABELS",
    "POLICY",
    "Manifest",
    "MutableStrictModel",
    "Policy",
    "STATEMENT",
    "StrictModel",
]
