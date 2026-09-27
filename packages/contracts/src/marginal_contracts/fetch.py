"""`make data`: download what is missing when the host answers, verify every copy, and say
plainly what could not be fetched and where to put it."""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path

from marginal_contracts.sources import SOURCES, Source, Verification, verify


def download(item: Source, external: Path, timeout: float = 60.0) -> bool:
    external.mkdir(parents=True, exist_ok=True)
    target = external / item.filename
    partial = target.with_suffix(target.suffix + ".part")
    try:
        with urllib.request.urlopen(item.url, timeout=timeout) as response, partial.open("wb") as out:
            while chunk := response.read(1 << 20):
                out.write(chunk)
    except (urllib.error.URLError, OSError, ValueError):
        if partial.exists():
            partial.unlink()
        return False
    partial.replace(target)
    return True


def fetch_all(external: Path, *, attempt_download: bool = True) -> list[Verification]:
    results: list[Verification] = []
    for item in SOURCES:
        status = verify(external, item)
        if not status.present and attempt_download and download(item, external):
            status = verify(external, item)
        results.append(status)
    return results


def report(results: list[Verification]) -> str:
    lines = []
    for status in results:
        mark = "verified" if status.verified else "NOT VERIFIED"
        lines.append(f"{status.key:10} {mark:13} {status.detail}")
    return "\n".join(lines)
