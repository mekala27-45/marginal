"""Reset and rederive: clear what the demo recording created, run the pipeline again from the
committed inputs, and prove the published figures reproduce.

Runs after the demo recording and before the tag. Three parts:

1. Reset (``--reset``): delete the plans and experiments the site recording and the separate
   client verification created in the registry, by their stated notes and names, leaving the
   audit log alone. Needs DATABASE_URL (or MARGINAL_RESET_DATABASE_URL) and psycopg.
2. Rederive: run every stage in the order the registry declares (``marginal_registry.stages
   .assemble.ORDER``), then merge the manifest, render every document and write the marts, with
   the committed manifest's as of date so the comparison is like for like.
3. Compare: every value and every table of the new manifest against the manifest that was on
   disk before the run. Floats may differ by one part in a billion (parallel sums); anything
   else is drift and the script exits non zero unless ``--allow-drift`` is passed. Then the
   gates run.

    uv run python scripts/reset_and_rederive.py                 # full run, compare, gates
    uv run python scripts/reset_and_rederive.py --stages clv,budget,attribution
    uv run python scripts/reset_and_rederive.py --compare-only  # judge the last run's manifest
    DATABASE_URL=... uv run python scripts/reset_and_rederive.py --reset --stages none

The summary is written to results/rederive.json and the log to logs/rederive.log.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))

from marginal_registry.stages.assemble import ORDER

RECORDING_NOTES = (
    "recorded session for the site's fallback bundle",
    "persistence check",
    "verification from a separate client",
)
RECORDING_NAMES = ("verification from a separate client", "persistence check")
RELATIVE_TOLERANCE = 1e-9
STAGE_COMMANDS: dict[str, list[str]] = {
    "data": ["data"],
    "simulate": ["simulate"],
    "recovery_own": ["recovery", "--backend", "own"],
    "recovery_bayes": ["recovery", "--backend", "bayes"],
    "experiments": ["experiments"],
    "calibrate": ["calibrate"],
    "clv": ["clv"],
    "budget": ["budget"],
    "targeting": ["targeting"],
    "attribution": ["attribution"],
}
GATES = (
    "scripts/check_no_em_dash.py",
    "scripts/check_vocabulary.py",
    "scripts/check_statement.py",
    "scripts/check_published_numbers.py",
    "scripts/scan_for_planted_identifiers.py",
)


def log(handle: Any, message: str) -> None:
    line = f"{datetime.now(UTC).strftime('%H:%M:%S')} {message}"
    print(line, flush=True)
    handle.write(line + "\n")
    handle.flush()


def reset_registry(url: str, handle: Any) -> dict[str, int]:
    """Delete the rows the recording and the verification created, and nothing else."""
    import psycopg

    plain = url.replace("postgresql+psycopg://", "postgresql://")
    counts = {"plans": 0, "experiment_results": 0, "experiments": 0}
    with psycopg.connect(plain) as conn, conn.cursor() as cur:
        cur.execute("delete from plans where note = any(%s)", (list(RECORDING_NOTES),))
        counts["plans"] = cur.rowcount
        cur.execute(
            "delete from experiment_results where experiment_id in "
            "(select experiment_id from experiments where name = any(%s))",
            (list(RECORDING_NAMES),),
        )
        counts["experiment_results"] = cur.rowcount
        cur.execute("delete from experiments where name = any(%s)", (list(RECORDING_NAMES),))
        counts["experiments"] = cur.rowcount
        conn.commit()
    log(handle, f"reset: removed {counts}")
    return counts


def run_stage(name: str, env: dict[str, str], handle: Any) -> float:
    started = time.time()
    command = ["uv", "run", "marginal", *STAGE_COMMANDS[name]]
    log(handle, "run " + " ".join(command))
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
    handle.write(result.stdout)
    handle.write(result.stderr)
    if result.returncode != 0:
        log(handle, f"stage {name} failed with exit code {result.returncode}")
        print(result.stdout[-4000:])
        print(result.stderr[-4000:])
        raise SystemExit(f"stage {name} failed")
    seconds = time.time() - started
    log(handle, f"stage {name} finished in {seconds:,.0f} seconds")
    return seconds


def run_python(script: list[str], env: dict[str, str], handle: Any) -> bool:
    command = ["uv", "run", "python", *script]
    log(handle, "run " + " ".join(command))
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
    handle.write(result.stdout)
    handle.write(result.stderr)
    if result.returncode != 0:
        print(result.stdout[-3000:])
        print(result.stderr[-3000:])
    return result.returncode == 0


def _same_scalar(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a == b)
    if isinstance(a, int | float) and isinstance(b, int | float):
        if isinstance(a, float) and isinstance(b, float) and (math.isnan(a) and math.isnan(b)):
            return True
        return math.isclose(float(a), float(b), rel_tol=RELATIVE_TOLERANCE, abs_tol=1e-12)
    return bool(a == b)


TIMING_SUFFIX = "_seconds"


def compare(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Every difference between two manifests, as one line each. Wall clock timings (keys ending
    in ``_seconds``) are reported by ``timing_differences`` instead; they are not claims."""
    drift: list[str] = []
    for bucket in ("values", "tables"):
        old = before.get(bucket, {})
        new = after.get(bucket, {})
        for key in sorted(set(old) | set(new)):
            if key not in new:
                drift.append(f"{bucket} {key}: missing after the rederive")
                continue
            if key not in old:
                drift.append(f"{bucket} {key}: new since the committed manifest")
                continue
            if bucket == "values":
                if key.endswith(TIMING_SUFFIX):
                    continue
                if not _same_scalar(old[key]["value"], new[key]["value"]):
                    drift.append(f"value {key}: {old[key]['value']!r} became {new[key]['value']!r}")
            else:
                rows_old, rows_new = old[key]["rows"], new[key]["rows"]
                if len(rows_old) != len(rows_new) or old[key]["columns"] != new[key]["columns"]:
                    drift.append(f"table {key}: shape changed")
                    continue
                for i, (ro, rn) in enumerate(zip(rows_old, rows_new, strict=True)):
                    for j, (a, b) in enumerate(zip(ro, rn, strict=True)):
                        if not _same_scalar(a, b):
                            drift.append(f"table {key} row {i} col {j}: {a!r} became {b!r}")
    return drift


def timing_differences(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    for key, entry in after.get("values", {}).items():
        if key.endswith(TIMING_SUFFIX) and key in before.get("values", {}):
            out[key] = [before["values"][key]["value"], entry["value"]]
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stages", default="all", help="comma separated stage names, 'all' or 'none'")
    parser.add_argument(
        "--as-of", default=None, help="override the as of date (default: the committed manifest's)"
    )
    parser.add_argument(
        "--reset", action="store_true", help="delete the recording's rows from the registry first"
    )
    parser.add_argument(
        "--compare-only", action="store_true", help="only compare results/manifest.json with the snapshot"
    )
    parser.add_argument("--allow-drift", action="store_true")
    parser.add_argument("--skip-gates", action="store_true")
    args = parser.parse_args()

    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    manifest_path = ROOT / "results" / "manifest.json"
    snapshot_path = ROOT / "results" / "manifest.before-rederive.json"
    summary_path = ROOT / "results" / "rederive.json"
    with (logs / "rederive.log").open("a", encoding="utf-8") as handle:
        log(handle, "reset and rederive started")
        summary: dict[str, Any] = {"started_at": datetime.now(UTC).isoformat(), "stages": {}, "reset": None}

        if args.reset:
            url = os.environ.get("MARGINAL_RESET_DATABASE_URL") or os.environ.get("DATABASE_URL")
            if not url:
                raise SystemExit("--reset needs DATABASE_URL or MARGINAL_RESET_DATABASE_URL")
            summary["reset"] = reset_registry(url, handle)

        if not args.compare_only:
            if not manifest_path.exists():
                raise SystemExit("results/manifest.json is missing; there is nothing to compare against")
            shutil.copyfile(manifest_path, snapshot_path)
            before = json.loads(snapshot_path.read_text(encoding="utf-8"))
            env = {**os.environ, "MARGINAL_AS_OF": args.as_of or str(before["as_of"])}
            stages = (
                list(ORDER)
                if args.stages == "all"
                else []
                if args.stages == "none"
                else args.stages.split(",")
            )
            unknown = [s for s in stages if s not in STAGE_COMMANDS]
            if unknown:
                raise SystemExit(f"unknown stages: {unknown}; choose from {list(STAGE_COMMANDS)}")
            for name in stages:
                summary["stages"][name] = run_stage(name, env, handle)
            if stages:
                started = time.time()
                for command in (["uv", "run", "marginal", "manifest"], ["uv", "run", "marginal", "marts"]):
                    log(handle, "run " + " ".join(command))
                    result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
                    handle.write(result.stdout + result.stderr)
                    if result.returncode != 0:
                        print(result.stderr[-3000:])
                        raise SystemExit("merging the manifest or writing the marts failed")
                if not run_python(["scripts/check_published_numbers.py", "--write"], env, handle):
                    raise SystemExit("rendering the documents failed")
                summary["stages"]["manifest_render_marts"] = time.time() - started
        else:
            if not snapshot_path.exists():
                raise SystemExit("no snapshot to compare against; run without --compare-only first")
            before = json.loads(snapshot_path.read_text(encoding="utf-8"))

        after = json.loads(manifest_path.read_text(encoding="utf-8"))
        drift = compare(before, after)
        summary["values_compared"] = len(after.get("values", {}))
        summary["tables_compared"] = len(after.get("tables", {}))
        summary["drift"] = drift
        summary["timing_differences"] = timing_differences(before, after)
        for line in drift[:200]:
            log(handle, "drift: " + line)
        log(
            handle,
            f"compared {summary['values_compared']} values and {summary['tables_compared']} tables; {len(drift)} drifted",
        )

        gates_ok = True
        if not args.skip_gates:
            for gate in GATES:
                ok = run_python([gate], dict(os.environ), handle)
                log(handle, f"gate {gate}: {'passed' if ok else 'FAILED'}")
                gates_ok = gates_ok and ok
        summary["gates_passed"] = gates_ok
        summary["finished_at"] = datetime.now(UTC).isoformat()
        summary["reproduced"] = not drift and gates_ok
        summary_path.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        log(handle, f"summary written to {summary_path.relative_to(ROOT)}")
        if drift and not args.allow_drift:
            print(f"{len(drift)} published figures did not reproduce; see logs/rederive.log")
            return 1
        if not gates_ok:
            return 1
        print("every published figure reproduced and every gate passed" if not drift else "drift allowed")
        return 0


if __name__ == "__main__":
    sys.exit(main())
