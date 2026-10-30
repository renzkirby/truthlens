#!/usr/bin/env python3
"""Short, read-only TruthLens Community feed concurrency probe.

This utility intentionally performs one GET per simulated client and does not
create or mutate application data. It is designed for controlled production
smoke/load checks, not sustained benchmarking.

Authentication is read from TRUTHLENS_LOAD_TEST_TOKEN so JWTs do not need to be
placed in command history.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import statistics
import time

import requests


def percentile(values, percentile_value):
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * (percentile_value / 100)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def one_request(url, token, timeout):
    started = time.perf_counter()
    try:
        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": "TruthLens-Community-Load-Probe/1.0",
            },
            timeout=timeout,
        )
        duration = time.perf_counter() - started
        return response.status_code, duration, None
    except requests.RequestException as exc:
        duration = time.perf_counter() - started
        return None, duration, type(exc).__name__


def run_stage(url, token, concurrency, timeout):
    stage_started = time.perf_counter()
    results = []

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(one_request, url, token, timeout)
            for _ in range(concurrency)
        ]
        for future in as_completed(futures):
            results.append(future.result())

    elapsed = time.perf_counter() - stage_started
    latencies = [duration for _status, duration, _error in results]
    statuses = {}
    errors = {}

    for status, _duration, error in results:
        if status is not None:
            statuses[status] = statuses.get(status, 0) + 1
        if error:
            errors[error] = errors.get(error, 0) + 1

    successes = statuses.get(200, 0)
    success_rate = (successes / len(results) * 100) if results else 0

    return {
        "concurrency": concurrency,
        "requests": len(results),
        "successes": successes,
        "success_rate": success_rate,
        "statuses": statuses,
        "errors": errors,
        "elapsed": elapsed,
        "throughput": (len(results) / elapsed) if elapsed else 0,
        "p50": statistics.median(latencies) if latencies else None,
        "p95": percentile(latencies, 95),
        "p99": percentile(latencies, 99),
        "max": max(latencies) if latencies else None,
    }


def format_seconds(value):
    return "-" if value is None else f"{value:.3f}s"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        required=True,
        help="Production backend origin, e.g. https://api.example.com",
    )
    parser.add_argument(
        "--stages",
        default="10,25,40",
        help="Comma-separated concurrency stages. Default: 10,25,40",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Per-request timeout in seconds. Default: 15",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=2.0,
        help="Pause between stages in seconds. Default: 2",
    )
    args = parser.parse_args()

    token = os.environ.get("TRUTHLENS_LOAD_TEST_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "Set TRUTHLENS_LOAD_TEST_TOKEN to a valid access token first."
        )

    stages = []
    for raw in args.stages.split(","):
        value = int(raw.strip())
        if value < 1:
            raise SystemExit("Every stage must be at least 1.")
        stages.append(value)

    total_requests = sum(stages)
    if total_requests > 95:
        raise SystemExit(
            "This probe refuses more than 95 total requests per run so a "
            "single authenticated user stays below TruthLens's default "
            "100/minute user throttle. Run larger stages separately after "
            "the throttle window resets."
        )

    url = args.base_url.rstrip("/") + "/api/threads/"

    print("TruthLens Community read-load probe")
    print("Endpoint:", url)
    print("Stages:", stages)
    print("Total requests:", total_requests)
    print("Mutation risk: none (GET only)")
    print()

    for index, concurrency in enumerate(stages):
        result = run_stage(url, token, concurrency, args.timeout)

        print(f"=== CONCURRENCY {concurrency} ===")
        print("requests =", result["requests"])
        print("successes =", result["successes"])
        print("success_rate =", f'{result["success_rate"]:.1f}%')
        print("statuses =", result["statuses"])
        print("errors =", result["errors"])
        print("wall_time =", format_seconds(result["elapsed"]))
        print("throughput =", f'{result["throughput"]:.2f} req/s')
        print("p50 =", format_seconds(result["p50"]))
        print("p95 =", format_seconds(result["p95"]))
        print("p99 =", format_seconds(result["p99"]))
        print("max =", format_seconds(result["max"]))
        print()

        if index < len(stages) - 1:
            time.sleep(max(0, args.pause))


if __name__ == "__main__":
    main()
