"""Batch 7 controlled Gemini-only executor for the paired semantic pilot.

This module is intentionally separate from TruthLens runtime provider routing.
It executes an already-created, label-blind semantic_eval_runner plan against
one fixed Gemini model/configuration, exactly once per planned job. It never
imports the production fallback router, never calls Cloudflare or Groq, and
never reads the benchmark reference labels.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

from .semantic_benchmark import BenchmarkInputError
from .semantic_eval_runner import (
    MANIFEST_VERSION,
    MAX_JOB_BYTES,
    _hash,
    _read_lines,
    _strict_json,
)

PROVIDER = "gemini"
MODEL_ID = "gemini-2.5-flash"
TEMPERATURE = 0.1
THINKING_BUDGET = 0
MAX_LIVE_REQUESTS = 16
HTTP_TIMEOUT_MS = 30_000
INTER_REQUEST_DELAY_SEC = 6.5
CONFIRMATION = "I_APPROVE_16_GEMINI_PILOT_REQUESTS"
EXECUTION_VERSION = "phase3-gemini-pilot-v1"
_ALLOWED_JOB_FIELDS = frozenset({
    "job_id", "case_id", "arm", "system_prompt", "user_prompt",
    "max_output_tokens",
})
_FORBIDDEN_LABEL_MARKERS = (
    '"reference_stance"', '"rationale"', '"reviewer_id"',
    '"review_status"', '"reviewed_on"',
)


def _json_line(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ) + "\n"


def _atomic_json(path, value):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as out:
        json.dump(value, out, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")
    tmp.replace(path)


def _file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _finish_reason_name(reason):
    if reason is None:
        return "MISSING"
    name = getattr(reason, "name", None)
    if isinstance(name, str) and name:
        return name.upper()
    value = getattr(reason, "value", None)
    if isinstance(value, str) and value:
        return value.upper().split(".")[-1]
    return str(reason).upper().split(".")[-1]


def _usage_int(usage, name):
    value = getattr(usage, name, None) if usage is not None else None
    if type(value) is int and 0 <= value <= 10_000_000:
        return value
    return None


def _generated_tokens(usage):
    candidate = _usage_int(usage, "candidates_token_count")
    thoughts = _usage_int(usage, "thoughts_token_count")
    if candidate is None and thoughts is None:
        prompt = _usage_int(usage, "prompt_token_count")
        total = _usage_int(usage, "total_token_count")
        if prompt is not None and total is not None and total >= prompt:
            return total - prompt
        return None
    return (candidate or 0) + (thoughts or 0)


def validate_live_plan(*, jobs_path, manifest_path):
    """Validate an immutable offline plan without reading gold/reference labels."""
    manifest = _strict_json(Path(manifest_path).read_text(encoding="utf-8"))
    if type(manifest) is not dict or manifest.get("schema_version") != MANIFEST_VERSION:
        raise BenchmarkInputError("Unexpected plan manifest")
    if manifest.get("status") != "OFFLINE_PLAN_ONLY_NOT_APPROVED_FOR_INFERENCE":
        raise BenchmarkInputError("Unexpected plan status")

    job_bytes = Path(jobs_path).read_bytes()
    if manifest.get("jobs_sha256") != _hash(job_bytes):
        raise BenchmarkInputError("Job plan differs from recorded manifest")
    jobs = _read_lines(jobs_path, max_chars=MAX_JOB_BYTES)

    paired = manifest.get("paired_jobs")
    request_limit = manifest.get("max_requests")
    if type(paired) is not int or paired != len(jobs):
        raise BenchmarkInputError("Job count mismatch")
    if type(request_limit) is not int or request_limit < paired:
        raise BenchmarkInputError("Plan request limit is invalid")
    if paired < 1 or paired > MAX_LIVE_REQUESTS or request_limit > MAX_LIVE_REQUESTS:
        raise BenchmarkInputError("Live pilot exceeds hard 16-request cap")

    expected_cap = manifest.get("output_token_cap_per_request")
    if type(expected_cap) is not int or not 1 <= expected_cap <= 256:
        raise BenchmarkInputError("Unexpected output-token cap")

    seen = set()
    counts = {"baseline": 0, "candidate": 0}
    for job in jobs:
        if set(job) != _ALLOWED_JOB_FIELDS:
            raise BenchmarkInputError("Unexpected live job fields")
        job_id = job.get("job_id")
        case_id = job.get("case_id")
        arm = job.get("arm")
        if (
            type(job_id) is not str or job_id in seen
            or type(case_id) is not str or not case_id
            or arm not in counts
            or job_id != f"{arm}.{case_id}"
            or type(job.get("system_prompt")) is not str
            or not job["system_prompt"].strip()
            or type(job.get("user_prompt")) is not str
            or not job["user_prompt"].strip()
            or job.get("max_output_tokens") != expected_cap
        ):
            raise BenchmarkInputError("Invalid live job contract")
        serialized = _json_line(job)
        if any(marker in serialized for marker in _FORBIDDEN_LABEL_MARKERS):
            raise BenchmarkInputError("Gold-label metadata leaked into live job")
        seen.add(job_id)
        counts[arm] += 1

    if counts["baseline"] != counts["candidate"] or sum(counts.values()) != paired:
        raise BenchmarkInputError("Paired arms are not balanced")
    if {j["case_id"] for j in jobs if j["arm"] == "baseline"} != {
        j["case_id"] for j in jobs if j["arm"] == "candidate"
    }:
        raise BenchmarkInputError("Baseline/candidate case sets differ")
    return jobs, manifest


def _build_client(api_key):
    """Lazy import so offline tests/tools never require the Gemini SDK."""
    from google import genai
    return genai.Client(api_key=api_key)


def _build_config(job):
    from google.genai import types
    return types.GenerateContentConfig(
        system_instruction=job["system_prompt"],
        response_mime_type="application/json",
        temperature=TEMPERATURE,
        max_output_tokens=job["max_output_tokens"],
        thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET),
        http_options=types.HttpOptions(
            timeout=HTTP_TIMEOUT_MS,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )


def _call_one(client, job, *, config_builder=_build_config, clock=time.perf_counter):
    started = clock()
    response = client.models.generate_content(
        model=MODEL_ID,
        contents=job["user_prompt"],
        config=config_builder(job),
    )
    latency_ms = max(0.0, (clock() - started) * 1000.0)

    candidates = getattr(response, "candidates", None)
    reason = None
    if isinstance(candidates, (list, tuple)) and candidates:
        reason = getattr(candidates[0], "finish_reason", None)
    finish_reason = _finish_reason_name(reason)
    if finish_reason != "STOP":
        raise RuntimeError(f"GEMINI_FINISH_{finish_reason}")

    raw = getattr(response, "text", None)
    if type(raw) is not str or not raw.strip() or len(raw) > 20_000:
        raise RuntimeError("INVALID_GEMINI_RESPONSE_TEXT")

    usage = getattr(response, "usage_metadata", None)
    input_tokens = _usage_int(usage, "prompt_token_count")
    output_tokens = _generated_tokens(usage)
    if output_tokens is not None and output_tokens > job["max_output_tokens"]:
        raise RuntimeError("GEMINI_OUTPUT_USAGE_EXCEEDS_PLAN")

    result = {
        "job_id": job["job_id"],
        "raw_response": raw,
        "latency_ms": round(latency_ms, 3),
        "provider": PROVIDER,
        "model_id": MODEL_ID,
        "temperature": TEMPERATURE,
    }
    if input_tokens is not None:
        result["input_tokens"] = input_tokens
    if output_tokens is not None:
        result["output_tokens"] = output_tokens
    return result


def execute_gemini_pilot(
    *, jobs_path, manifest_path, responses_path, attempts_path,
    execution_manifest_path, confirmation, api_key=None,
    client_factory=_build_client, config_builder=_build_config,
    clock=time.perf_counter, sleeper=time.sleep,
):
    """Execute exactly one Gemini attempt per planned job, with no fallback."""
    if confirmation != CONFIRMATION:
        raise BenchmarkInputError("Exact live-inference confirmation phrase required")
    jobs, plan = validate_live_plan(jobs_path=jobs_path, manifest_path=manifest_path)

    outputs = tuple(map(Path, (responses_path, attempts_path, execution_manifest_path)))
    if len({p.resolve() for p in outputs}) != len(outputs):
        raise BenchmarkInputError("Live output paths must be distinct")
    if any(p.exists() for p in outputs):
        raise BenchmarkInputError("Refusing to overwrite existing live pilot output")

    if api_key is None:
        # Match the Django project's local configuration behavior without
        # importing settings or the production provider router.
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        key = os.getenv("GEMINI_API_KEY", "")
    else:
        key = api_key
    if type(key) is not str or not key.strip():
        raise BenchmarkInputError("GEMINI_API_KEY is not configured")

    client = client_factory(key.strip())

    execution = {
        "schema_version": EXECUTION_VERSION,
        "status": "IN_PROGRESS",
        "source_plan_schema_version": plan["schema_version"],
        "source_jobs_sha256": plan["jobs_sha256"],
        "planned_jobs": len(jobs),
        "hard_request_cap": MAX_LIVE_REQUESTS,
        "provider": PROVIDER,
        "model_id": MODEL_ID,
        "temperature": TEMPERATURE,
        "thinking_budget": THINKING_BUDGET,
        "max_output_tokens_per_request": plan["output_token_cap_per_request"],
        "http_timeout_ms": HTTP_TIMEOUT_MS,
        "sdk_retry_attempts": 1,
        "inter_request_delay_sec": INTER_REQUEST_DELAY_SEC,
        "fallback_enabled": False,
        "gold_reference_read": False,
    }
    _atomic_json(execution_manifest_path, execution)

    successes = 0
    failures = 0
    input_total = 0
    output_total = 0
    # Exclusive creation occurs before the first provider call. A partial file
    # is intentionally preserved after failures/interruption for auditability.
    with Path(responses_path).open("x", encoding="utf-8", newline="\n") as responses, \
            Path(attempts_path).open("x", encoding="utf-8", newline="\n") as attempts:
        for index, job in enumerate(jobs):
            attempt_started = clock()
            try:
                result = _call_one(
                    client, job, config_builder=config_builder, clock=clock,
                )
            except Exception as exc:
                failures += 1
                latency_ms = max(0.0, (clock() - attempt_started) * 1000.0)
                attempts.write(_json_line({
                    "job_id": job["job_id"],
                    "outcome": "FAILED",
                    "error_type": type(exc).__name__,
                    "error_code": str(exc) if str(exc).startswith("GEMINI_")
                                  or str(exc).startswith("INVALID_GEMINI_") else "PROVIDER_ERROR",
                    "latency_ms": round(latency_ms, 3),
                }))
                attempts.flush()
                if index + 1 < len(jobs):
                    sleeper(INTER_REQUEST_DELAY_SEC)
                continue

            successes += 1
            input_total += result.get("input_tokens", 0)
            output_total += result.get("output_tokens", 0)
            responses.write(_json_line(result))
            responses.flush()
            attempts.write(_json_line({
                "job_id": job["job_id"],
                "outcome": "SUCCESS",
                "latency_ms": result["latency_ms"],
                "input_tokens": result.get("input_tokens"),
                "output_tokens": result.get("output_tokens"),
            }))
            attempts.flush()
            if index + 1 < len(jobs):
                sleeper(INTER_REQUEST_DELAY_SEC)

    execution.update({
        "status": "COMPLETED_WITH_FAILURES" if failures else "COMPLETED",
        "attempted_requests": len(jobs),
        "successful_responses": successes,
        "failed_requests": failures,
        "input_tokens_reported_total": input_total,
        "output_tokens_reported_total": output_total,
        "responses_sha256": _file_hash(responses_path),
        "attempts_sha256": _file_hash(attempts_path),
    })
    _atomic_json(execution_manifest_path, execution)
    return execution


def _cli(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--responses", required=True, type=Path)
    parser.add_argument("--attempts", required=True, type=Path)
    parser.add_argument("--execution-manifest", required=True, type=Path)
    parser.add_argument("--confirm-live-gemini", required=True)
    args = parser.parse_args(argv)
    try:
        result = execute_gemini_pilot(
            jobs_path=args.jobs,
            manifest_path=args.manifest,
            responses_path=args.responses,
            attempts_path=args.attempts,
            execution_manifest_path=args.execution_manifest,
            confirmation=args.confirm_live_gemini,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["failed_requests"] == 0 else 3
    except (OSError, ValueError, RuntimeError, SyntaxError) as exc:
        print(f"Gemini pilot error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
