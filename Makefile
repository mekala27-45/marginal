# The pipeline in the order it runs. docs/runbook.md describes each target;
# tests/core/test_make_order.py fails if the Makefile's order disagrees with the stage order.

PY := uv run python
M := uv run marginal

.PHONY: help setup data simulate recovery recovery-bayes experiments calibrate budget targeting clv attribution manifest render marts pipeline gates lint types test check rederive web deploy verify-api demo load-test clean

help:
	@grep -E '^[a-z-]+:' Makefile | sed 's/:.*//' | tr '\n' ' '; echo

setup:
	uv sync
	npm --prefix web ci

# The three public datasets. Place the files under data/external if this machine cannot
# reach the hosts; the target prints the expected paths and verifies the checksums either way.
data:
	$(M) data

simulate:
	$(M) simulate

recovery:
	$(M) recovery --backend own

recovery-bayes:
	$(M) recovery --backend bayes

experiments:
	$(M) experiments

calibrate:
	$(M) calibrate

budget:
	$(M) budget

targeting:
	$(M) targeting

clv:
	$(M) clv

attribution:
	$(M) attribution

manifest:
	$(M) manifest

render:
	$(PY) scripts/check_published_numbers.py --write

marts:
	$(M) marts

pipeline: simulate recovery recovery-bayes experiments calibrate clv budget targeting attribution manifest render marts

gates:
	$(PY) scripts/check_no_em_dash.py
	$(PY) scripts/check_vocabulary.py
	$(PY) scripts/check_statement.py
	$(PY) scripts/check_published_numbers.py
	$(PY) scripts/scan_for_planted_identifiers.py
	node scripts/validate_palette.js --config web/src/theme/palette.json

lint:
	uv run ruff check .
	uv run ruff format --check .

types:
	uv run mypy

test:
	uv run pytest --cov --cov-report=term-missing:skip-covered

check: lint types gates test

rederive:
	$(PY) scripts/reset_and_rederive.py

web:
	npm --prefix web run build

# Deploys the API to Fly with the Neon connection string as a secret. Needs flyctl and the
# variables in .env; the sandbox that built this repository could not reach Fly, so the
# same steps live in deploy/deploy.ps1 for a Windows machine.
deploy:
	sh deploy/deploy.sh

verify-api:
	$(PY) scripts/check_persistence.py --base-url "$${MARGINAL_API_BASE:-http://127.0.0.1:8080}"

demo:
	$(PY) scripts/build_demo_gif.py

load-test:
	$(PY) scripts/load_test.py --base-url "$${MARGINAL_API_BASE:-http://127.0.0.1:8080}"

clean:
	rm -rf results/scratch web/out logs/*.log
