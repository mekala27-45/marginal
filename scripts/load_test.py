"""Latency of POST /v1/optimize from a stated load: p50 and p99 over N sequential requests plus
a burst of concurrent ones, against a running server.

    python scripts/load_test.py --base-url http://127.0.0.1:8080 --requests 60 --concurrency 8
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


async def _one(client: httpx.AsyncClient, base: str, budget: float) -> float:
    started = time.perf_counter()
    response = await client.post(f"{base}/v1/optimize", json={"total_budget": budget}, timeout=60.0)
    response.raise_for_status()
    return (time.perf_counter() - started) * 1000.0


async def run(base: str, requests: int, concurrency: int) -> dict[str, float | int | str]:
    async with httpx.AsyncClient() as client:
        health = await client.get(f"{base}/v1/health", timeout=30.0)
        health.raise_for_status()
        sequential = [await _one(client, base, 500_000.0 + 1_000.0 * i) for i in range(requests)]
        burst = await asyncio.gather(
            *[_one(client, base, 480_000.0 + 2_000.0 * i) for i in range(concurrency)]
        )
    quantiles = statistics.quantiles(sequential, n=100)
    return {
        "base_url": base,
        "requests": requests,
        "concurrency": concurrency,
        "p50_ms": round(statistics.median(sequential), 1),
        "p99_ms": round(quantiles[98], 1),
        "max_ms": round(max(sequential), 1),
        "burst_max_ms": round(max(burst), 1),
        "errors": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--requests", type=int, default=60)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--out", default=str(ROOT / "results" / "api" / "load_test.json"))
    args = parser.parse_args()
    result = asyncio.run(run(args.base_url.rstrip("/"), args.requests, args.concurrency))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
