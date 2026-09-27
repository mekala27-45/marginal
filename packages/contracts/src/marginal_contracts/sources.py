"""The three public datasets: where they come from, what they are, and how a copy is verified.

Nothing raw is committed. `make data` looks for each file under data/external, downloads it
when the host is reachable, and verifies the checksum either way. The MD5s for the two
scikit-uplift mirrors are the ones that project publishes in sklift/datasets/datasets.py;
the UCI workbook has no published checksum, so the SHA-256 of the copy this build used is
recorded here and a different copy fails verification on purpose.
"""

from __future__ import annotations

from pathlib import Path

from marginal_core.hashing import file_md5, file_sha256
from marginal_core.model import StrictModel


class Source(StrictModel):
    key: str
    title: str
    filename: str
    url: str
    md5: str | None
    sha256: str | None
    license: str
    terms: str
    citation: str
    rows_expected: int


SOURCES: tuple[Source, ...] = (
    Source(
        key="hillstrom",
        title="Hillstrom email experiment (MineThatData E-Mail Analytics and Data Mining Challenge, March 2008)",
        filename="hillstorm_no_indices.csv.gz",
        url="https://hillstorm1.s3.us-east-2.amazonaws.com/hillstorm_no_indices.csv.gz",
        md5="a68a81291f53a14f4e29002629803ba3",
        sha256="bab6578f60db5d792f1c2372c502f029152a5249cf5ea84390f3b7f885d7234f",
        license="Public challenge release without a formal license text",
        terms=(
            "Released by Kevin Hillstrom in March 2008 for the MineThatData challenge with no formal license "
            "text; used here for a non commercial portfolio with attribution, through the scikit-uplift mirror "
            "whose MD5 is published by that project."
        ),
        citation="Hillstrom, K. (2008). The MineThatData E-Mail Analytics and Data Mining Challenge. MineThatData blog.",
        rows_expected=64000,
    ),
    Source(
        key="retail",
        title="Online Retail II (UCI Machine Learning Repository, dataset 502)",
        filename="online+retail+ii.zip",
        url="https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip",
        md5=None,
        sha256="572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb",
        license="CC BY 4.0",
        terms="Creative Commons Attribution 4.0; the same source pricepoint (Day 2 of this series) priced.",
        citation="Chen, D. (2019). Online Retail II. UCI Machine Learning Repository. https://doi.org/10.24432/C5CG6D",
        rows_expected=1067371,
    ),
    Source(
        key="criteo",
        title="Criteo Uplift Prediction Dataset v2.1 (Criteo AI Lab)",
        filename="criteo-uplift-v2.1.csv.gz",
        url="http://go.criteo.net/criteo-research-uplift-v2.1.csv.gz",
        md5="d2236769ef69e9be52556110102911ec",
        sha256="2716e1bf0fd157a93b5bf86924d9088419dfbac2022c6cd90030220634f616dc",
        license="CC BY-NC-SA 4.0",
        terms=(
            "Creative Commons Attribution NonCommercial ShareAlike 4.0: non commercial use with attribution, and "
            "every derived table in this repository carries the same terms."
        ),
        citation=(
            "Diemert, E., Betlei, A., Renaudin, C., Amini, M. (2018). A Large Scale Benchmark for Uplift "
            "Modeling. AdKDD and TargetAd Workshop, KDD 2018."
        ),
        rows_expected=13979592,
    ),
)


def source(key: str) -> Source:
    for item in SOURCES:
        if item.key == key:
            return item
    raise KeyError(f"no source named {key!r}")


class Verification(StrictModel):
    key: str
    path: str
    present: bool
    md5: str | None
    sha256: str | None
    verified: bool
    detail: str


def verify(external: Path, item: Source) -> Verification:
    path = external / item.filename
    if not path.exists():
        return Verification(
            key=item.key,
            path=str(path),
            present=False,
            md5=None,
            sha256=None,
            verified=False,
            detail=f"missing: place {item.filename} at {path} (from {item.url})",
        )
    sha = file_sha256(path)
    md5 = file_md5(path) if item.md5 else None
    ok = sha == item.sha256 and (item.md5 is None or md5 == item.md5)
    expected = (item.sha256 or "")[:12]
    detail = "checksum matches" if ok else f"checksum mismatch: sha256 {sha[:12]}, expected {expected}"
    if item.md5 and md5 != item.md5:
        detail = f"published MD5 mismatch: {md5}, expected {item.md5}"
    return Verification(
        key=item.key, path=str(path), present=True, md5=md5, sha256=sha, verified=ok, detail=detail
    )
