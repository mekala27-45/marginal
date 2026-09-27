"""The statement that appears on every surface.

Written once here. Pages, API responses, the memo, the cards and every rendered
document read it from this module, and a gate checks each surface.
"""

from __future__ import annotations

BRAND = "Alderquist"

STATEMENT = (
    f"{BRAND} is a fictional direct to consumer home goods brand and its market is simulated "
    "with known truth. The email experiment is Kevin Hillstrom's public 2008 dataset, the "
    "purchase history is the UCI Online Retail II dataset, and the large uplift set is Criteo's "
    "public research release. No real company's spend and no real customer's identity appears here."
)


def statement_markdown() -> str:
    """The statement as a Markdown block quote, for documents."""
    return f"> {STATEMENT}"


def statement_payload() -> dict[str, str]:
    """The statement as a JSON-ready mapping, for API response bodies."""
    return {"statement": STATEMENT}


def contains_statement(text: str) -> bool:
    """True when the statement appears verbatim, allowing for line wrapping."""
    flat = " ".join(text.split())
    return " ".join(STATEMENT.split()) in flat
