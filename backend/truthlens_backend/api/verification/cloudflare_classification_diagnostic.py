"""Separate Cloudflare-03: a single-case, 4096-token diagnostic.

NO live requests when preparing or dry-running. NO production routing changes.
Live use is independently gated, is single-use, and requires NEW permission.
The earlier Cloudflare-02 packet and its four-case code are not modified.
"""
import json
import os
import time
from pathlib import Path

from django.conf import settings

from ..investigation_classifier import classification_system_prompt
from .classification_capture_plan import (
    build_capture_plan, write_private_capture_package,
)
from .classification_contract import validate_classification_response
from .classification_quality_audit import (
    ClassificationAuditError, load_classification_corpus,
)
from .cloudflare_classification_capture import (
    _atomic_private_json, _file_json, _sha,
)
from .cloudflare_evaluation import (
    CloudflareEvaluationError, DEFAULT_MODEL, generate_evaluation_json,
    sanitized_cloudflare_error_code,
)


DIAGNOSTIC_PROFILE = "gemma4_one_case_4096_v1"
CASE_ID = "cross_spacecraft"
MAX_REQUESTS = 1
MAX_COMPLETION_TOKENS = 4096
HTTP_TIMEOUT = (3, 45)
LIVE_ENV = "TRUTHLENS_LIVE_CLOUDFLARE_CLASSIFICATION_DIAGNOSTIC"
CONFIRMATION = "I_APPROVE_ONE_CLOUDFLARE_4096_DIAGNOSTIC_CALL"
RAW_FILE = "cloudflare_diagnostic_raw_responses.json"
PREDICTIONS_FILE = "cloudflare_diagnostic_predictions.json"
JOURNAL_FILE = "cloudflare_diagnostic_attempts.json"
LOCK_FILE = "cloudflare_diagnostic.lock"
OUTPUT_NAMES = (RAW_FILE, PREDICTIONS_FILE, JOURNAL_FILE, LOCK_FILE)


def build_diagnostic_plan(cases):
    """Fixed one-case profile; never include review answers in provider inputs."""
    if len(cases) != 32 or any(
        item["review"]["status"] != "APPROVED" for item in cases
    ):
        raise ClassificationAuditError(
            "Diagnostic requires the fully approved 32-case review corpus."
        )
    plan = build_capture_plan(
        cases, provider="cloudflare", model_id=DEFAULT_MODEL,
        limit=1, case_ids=[CASE_ID],
    )
    plan["max_output_tokens"] = MAX_COMPLETION_TOKENS
    plan["diagnostic_profile"] = DIAGNOSTIC_PROFILE
    plan["http_timeout_connect_sec"] = HTTP_TIMEOUT[0]
    plan["http_timeout_read_inactivity_sec"] = HTTP_TIMEOUT[1]
    plan["reject_if_busy"] = True
    plan["fallback_enabled"] = False
    plan["retry_enabled"] = False
    return plan


def prepare_private_diagnostic(corpus_path, export_dir):
    """Explicitly create a NEW local private packet; ZERO API requests."""
    cases = load_classification_corpus(corpus_path)
    plan = build_diagnostic_plan(cases)
    path = write_private_capture_package(plan, export_dir)
    return {
        "status": "PRIVATE_DIAGNOSTIC_PREPARED_NO_PROVIDER_CALLS",
        "profile": DIAGNOSTIC_PROFILE,
        "provider": "cloudflare",
        "model_id": DEFAULT_MODEL,
        "case_ids": [CASE_ID],
        "planned_requests": MAX_REQUESTS,
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
        "http_timeout_read_inactivity_sec": HTTP_TIMEOUT[1],
        "corpus_sha256": plan["corpus_sha256"],
        "private_package_created": path.is_dir(),
        "provider_calls": 0,
        "db_writes": 0,
        "enforcement_approved": False,
    }


def validate_diagnostic_packet(corpus_path, packet_dir):
    """Preflight exact pinned inputs before even acquiring a live-use lock."""
    path = Path(packet_dir).expanduser().resolve()
    checkout = Path(__file__).resolve().parents[4]
    if not path.is_dir() or path.is_relative_to(checkout):
        raise ClassificationAuditError("Diagnostic packet must exist outside Git.")
    cases = load_classification_corpus(corpus_path)
    expected = build_diagnostic_plan(cases)
    found = _file_json(path / "capture_inputs.json", 128_000)
    if type(found) is not dict or found != expected:
        raise ClassificationAuditError(
            "Diagnostic manifest mismatch: use a pristine 4096-token one-case packet."
        )
    if _file_json(path / "predictions.json", 512_000) != {
        "schema_version": 1, "predictions": [],
    }:
        raise ClassificationAuditError("Diagnostic predictions template must be empty.")
    if any(
        (path / name).exists() or (path / name).is_symlink()
        for name in OUTPUT_NAMES
    ) or any(
        (path / (name + ".writing")).exists()
        for name in OUTPUT_NAMES[:-1]
    ):
        raise ClassificationAuditError(
            "Diagnostic packet already used or interrupted; never replay it."
        )
    prompt = classification_system_prompt()
    if not isinstance(prompt, str) or not 1 <= len(prompt) <= 10000:
        raise ClassificationAuditError("Unusable production classification prompt.")
    return path, expected, prompt


def diagnostic_summary(plan, prompt):
    return {
        "status": "DRY_RUN_READY_NO_PROVIDER_CALLS",
        "profile": DIAGNOSTIC_PROFILE,
        "provider": "cloudflare",
        "model_id": DEFAULT_MODEL,
        "case_ids": [CASE_ID],
        "planned_requests": MAX_REQUESTS,
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
        "http_timeout_connect_sec": HTTP_TIMEOUT[0],
        "http_timeout_read_inactivity_sec": HTTP_TIMEOUT[1],
        "temperature": 0.1,
        "response_format": "json_object",
        "reject_if_busy": True,
        "fallback_enabled": False,
        "retry_enabled": False,
        "corpus_sha256": plan["corpus_sha256"],
        "system_prompt_sha256": _sha(prompt),
        "provider_calls": 0,
        "db_writes": 0,
        "enforcement_approved": False,
    }


def _seal_packet(path):
    # Exclusive permanent lock BEFORE any possibility of inference. Never
    # delete or re-use on failure: Cloudflare might have billed the attempt.
    fd = os.open(path / LOCK_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("ONE_USE_ONLY; DO_NOT_REMOVE; REQUEST_MAY_HAVE_BEEN_BILLED\n")


def execute_diagnostic(corpus_path, packet_dir, *, execute_live=False,
                       confirmation=""):
    """Default read-only; one direct adapter request only after new approval."""
    path, plan, prompt = validate_diagnostic_packet(corpus_path, packet_dir)
    summary = diagnostic_summary(plan, prompt)
    if not execute_live:
        return summary
    if not (
        getattr(settings, "APP_ENV", None) == "development"
        and getattr(settings, "DEBUG", False) is True
        and os.getenv(LIVE_ENV) == "1"
        and confirmation == CONFIRMATION
    ):
        raise ClassificationAuditError(
            "Live diagnostic denied: requires dev settings and separate explicit authorization."
        )
    _seal_packet(path)
    result = {"schema_version": 1, "provider": "cloudflare",
              "profile": DIAGNOSTIC_PROFILE, "results": []}
    predictions = {"schema_version": 1, "predictions": []}
    journal = {
        "schema_version": 1,
        "provider": "cloudflare",
        "profile": DIAGNOSTIC_PROFILE,
        "model_id": DEFAULT_MODEL,
        "corpus_sha256": plan["corpus_sha256"],
        "system_prompt_sha256": _sha(prompt),
        "request_config": {
            "max_tokens": MAX_COMPLETION_TOKENS,
            "temperature": 0.1,
            "response_format": "json_object",
            "timeout_connect_sec": HTTP_TIMEOUT[0],
            "timeout_read_inactivity_sec": HTTP_TIMEOUT[1],
            "reject_if_busy": True,
            "retry": False, "fallback": False,
        },
        "attempts": [],
    }
    for filename, data in (
        (RAW_FILE, result),
        (PREDICTIONS_FILE, predictions),
        (JOURNAL_FILE, journal),
    ):
        _atomic_private_json(path / filename, data, exclusive=True)

    entry = plan["requests"][0]
    attempt = {
        "case_id": CASE_ID, "claim_sha256": entry["claim_sha256"],
        "status": "STARTED", "duration_ms": None, "valid_contract": None,
        "error_code": None, "usage": {},
    }
    journal["attempts"].append(attempt)
    # A crash after STARTED makes the packet permanently non-replayable.
    _atomic_private_json(path / JOURNAL_FILE, journal)
    metadata = {}
    started = time.perf_counter()
    try:
        raw = generate_evaluation_json(
            prompt, entry["claim_text"],
            model=DEFAULT_MODEL, max_completion_tokens=MAX_COMPLETION_TOKENS,
            http_timeout=HTTP_TIMEOUT, reject_if_busy=True,
            audit_metadata=metadata,
        )
    except CloudflareEvaluationError as exc:
        attempt["status"] = "PROVIDER_FAILED"
        attempt["error_code"] = sanitized_cloudflare_error_code(exc)
    except Exception:
        attempt["status"] = "PROVIDER_FAILED"
        attempt["error_code"] = "UNEXPECTED_PROVIDER_FAILURE"
    else:
        # Preserve exact provider-visible message.content even when invalid.
        result["results"].append({"case_id": CASE_ID, "raw_response": raw})
        _atomic_private_json(path / RAW_FILE, result)
        valid = validate_classification_response(raw, entry["claim_text"])
        attempt["valid_contract"] = bool(valid)
        if len(raw) <= 8000:
            predictions["predictions"].append({
                "case_id": CASE_ID, "raw_response": raw,
            })
            _atomic_private_json(path / PREDICTIONS_FILE, predictions)
            attempt["status"] = (
                "CAPTURED_VALID" if valid else "CAPTURED_INVALID_CONTRACT"
            )
        else:
            attempt["status"] = "CAPTURED_TOO_LARGE_TO_SCORE"
    attempt["duration_ms"] = max(
        0, round((time.perf_counter() - started) * 1000),
    )
    # Adapter sanitizes metadata; do not save vendor errors or reasoning text.
    attempt["usage"] = metadata
    _atomic_private_json(path / JOURNAL_FILE, journal)
    return {
        "status": "DIAGNOSTIC_FINISHED_NO_RETRIES",
        "profile": DIAGNOSTIC_PROFILE,
        "attempted_requests": len(journal["attempts"]),
        "captured_predictions": len(predictions["predictions"]),
        "valid_responses": int(attempt["status"] == "CAPTURED_VALID"),
        "case_ids": [CASE_ID],
        "raw_response_file": RAW_FILE,
        "audit_predictions_file": PREDICTIONS_FILE,
        "journal_file": JOURNAL_FILE,
        "enforcement_approved": False,
    }
