# Contributing

## Setup

```bash
uv sync                      # Python 3.12 workspace and the dev group
npm --prefix web ci          # site dependencies
make data                    # verify the three public datasets (see data/PROVENANCE.md)
make check                   # lint, types, gates, tests
```

`make data` needs the three files under `data/external`; the Makefile prints the expected
paths and the checksums it verifies. Everything else runs offline.

## Rules the gates enforce

- No em or en dashes in authored files (`scripts/check_no_em_dash.py`).
- No filler vocabulary (`scripts/check_vocabulary.py`).
- The statement on every page, document, card and API response (`scripts/check_statement.py`,
  `tests/api/test_statement_on_every_endpoint.py`).
- No number typed by hand into a document. Documents are rendered from
  `results/manifest.json` by `scripts/check_published_numbers.py --write`, and CI
  re-renders and diffs every file.
- No card number, SSN pattern, email address, raw data row or planted token in anything
  published (`scripts/scan_for_planted_identifiers.py`).
- The palette passes the validator in both modes (`scripts/validate_palette.js`).

Each gate has three tests: it passes clean input, it fails on the defect it exists for,
and it refuses to report a pass when it was given nothing to check.

## Commits

Conventional commits: `feat(scope):`, `fix(scope):`, `test(scope):`, `docs:`, `ci:`,
`chore:`. One logical change per commit. The tag goes up after the commits, never in the
same push.
