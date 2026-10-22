"""Private, bounded 32-case Cloudflare subject-quality capture preparation.

This is separate from Cloudflare-02/03 and the optional paired benchmark.
Default is OFFLINE. Even a valid packet does not authorize live inference.
The later live path is dev-only, one-use and stops at first nonvalid result.
No ORM, Celery, Gemini/Groq fallback or production classification writes.
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

PROFILE = "gemma4_approved_32_accuracy_v1"
EXPECTED_CORPUS_SHA256 = (
    "40974b32aa0d7a32ec201f85bc703c14650c3c34d5bae9dbd01bb83ac53bb6af"
)
EXPECTED_PROMPT_SHA256 = (
    "abaf4338206d8a1857c3d682ff6dd971a775f7be45f0b425e8d45d9243756067"
)
MAX_ATTEMPTS = 32
COMPLETION_TOKENS = 4096
HTTP_TIMEOUT = (3, 45)
LIVE_ENV = "TRUTHLENS_LIVE_CLOUDFLARE_CLASSIFICATION_ACCURACY"
CONFIRMATION = "I_APPROVE_THIRTY_TWO_CLOUDFLARE_ACCURACY_ATTEMPTS"
LOCK_FILE = "cloudflare_accuracy.lock"
RAW_FILE = "cloudflare_accuracy_raw_responses.json"
PREDICTIONS_FILE = "cloudflare_accuracy_predictions.json"
JOURNAL_FILE = "cloudflare_accuracy_attempts.json"
OUTPUT_FILES = (LOCK_FILE, RAW_FILE, PREDICTIONS_FILE, JOURNAL_FILE)


def build_accuracy_plan(cases):
    """Require exactly the independently reviewed local 32-case corpus."""
    if len(cases) != MAX_ATTEMPTS or any(
        c["review"]["status"] != "APPROVED" for c in cases
    ):
        raise ClassificationAuditError(
            "All 32 separately reviewed subject cases are required."
        )
    plan = build_capture_plan(
        cases, provider="cloudflare", model_id=DEFAULT_MODEL,
        limit=MAX_ATTEMPTS, case_ids=[c["id"] for c in cases],
    )
    if plan["corpus_sha256"] != EXPECTED_CORPUS_SHA256:
        raise ClassificationAuditError(
            "The reference approval fingerprint does not match the pinned review."
        )
    if _sha(classification_system_prompt()) != EXPECTED_PROMPT_SHA256:
        raise ClassificationAuditError(
            "The classification prompt has changed; this study needs review."
        )
    plan.update({
        "accuracy_profile": PROFILE,
        "max_output_tokens": COMPLETION_TOKENS,
        "http_timeout_connect_sec": HTTP_TIMEOUT[0],
        "http_timeout_read_inactivity_sec": HTTP_TIMEOUT[1],
        "temperature": 0.1,
        "response_format": "json_object",
        "reject_if_busy": True,
        "fallback_enabled": False,
        "retry_enabled": False,
        "stop_on_first_nonvalid": True,
        "system_prompt_sha256": EXPECTED_PROMPT_SHA256,
    })
    return plan


def prepare_private_accuracy_packet(corpus_path, export_dir):
    """Create a brand-new private packet; zero provider calls."""
    plan = build_accuracy_plan(load_classification_corpus(corpus_path))
    path = write_private_capture_package(plan, export_dir)
    return {
        "status": "PRIVATE_ACCURACY_PACKET_PREPARED_NO_PROVIDER_CALLS",
        "profile": PROFILE,
        "model_id": DEFAULT_MODEL,
        "planned_requests": MAX_ATTEMPTS,
        "max_completion_tokens": COMPLETION_TOKENS,
        "http_timeout_read_inactivity_sec": HTTP_TIMEOUT[1],
        "corpus_sha256": plan["corpus_sha256"],
        "system_prompt_sha256": EXPECTED_PROMPT_SHA256,
        "private_package_created": path.is_dir(),
        "provider_calls": 0,
        "db_writes": 0,
        "enforcement_approved": False,
        "live_authorized": False,
    }


def validate_accuracy_packet(corpus_path, packet_dir):
    """Reject changed inputs, unsafe paths, used packets or partial writes."""
    packet = Path(packet_dir).expanduser().resolve()
    repo_root = Path(__file__).resolve().parents[4]
    if not packet.is_dir() or packet.is_relative_to(repo_root):
        raise ClassificationAuditError(
            "Accuracy packet must exist in a private location outside Git."
        )
    if any((packet / name).exists() or (packet / name).is_symlink()
           for name in OUTPUT_FILES):
        raise ClassificationAuditError(
            "Accuracy packet used or interrupted; never replay it."
        )
    if any((packet / (name + ".writing")).exists()
           for name in OUTPUT_FILES[1:]):
        raise ClassificationAuditError(
            "Interrupted accuracy output exists; never replay this packet."
        )
    plan = build_accuracy_plan(load_classification_corpus(corpus_path))
    actual = _file_json(packet / "capture_inputs.json", 128_000)
    if type(actual) is not dict or actual != plan:
        raise ClassificationAuditError(
            "Accuracy packet manifest mismatch; preserve original approved inputs."
        )
    if _file_json(packet / "predictions.json", 512_000) != {
        "schema_version": 1, "predictions": [],
    }:
        raise ClassificationAuditError(
            "Accuracy packet's blank prediction template was modified."
        )
    if any((packet / name).is_symlink()
           for name in ("capture_inputs.json", "predictions.json")):
        raise ClassificationAuditError("Private packet inputs may not be symlinks.")
    return packet, plan, classification_system_prompt()


def accuracy_dry_run_summary(plan):
    """Safe summary: no claim text or reviewer labels exposed."""
    return {
        "status": "DRY_RUN_READY_NO_PROVIDER_CALLS",
        "profile": PROFILE,
        "provider": "cloudflare",
        "model_id": DEFAULT_MODEL,
        "case_ids": [r["case_id"] for r in plan["requests"]],
        "planned_requests": MAX_ATTEMPTS,
        "max_completion_tokens": COMPLETION_TOKENS,
        "http_timeout_connect_sec": HTTP_TIMEOUT[0],
        "http_timeout_read_inactivity_sec": HTTP_TIMEOUT[1],
        "corpus_sha256": plan["corpus_sha256"],
        "system_prompt_sha256": EXPECTED_PROMPT_SHA256,
        "temperature": 0.1,
        "response_format": "json_object",
        "reject_if_busy": True,
        "retry_enabled": False,
        "fallback_enabled": False,
        "stop_on_first_nonvalid": True,
        "provider_calls": 0,
        "db_writes": 0,
        "enforcement_approved": False,
        "live_authorized": False,
    }


def _seal_packet(packet):
    # Never release or erase. A crashed/incomplete attempt might have billed.
    fd = os.open(packet / LOCK_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write("PERMANENT_ONE_USE_LOCK; NEVER_DELETE_OR_REPLAY\n")


def execute_accuracy_capture(corpus_path, packet_dir, *,
                             execute_live=False, confirmation=""):
    """No live inference by default; separately approved use only.

    No routine here changes any authoritative classification. A live run
    stops on first nonvalid classification or provider failure, with no retry.
    """
    packet, plan, prompt = validate_accuracy_packet(corpus_path, packet_dir)
    summary = accuracy_dry_run_summary(plan)
    if not execute_live:
        return summary
    if not (
        getattr(settings, "APP_ENV", None) == "development"
        and getattr(settings, "DEBUG", False) is True
        and os.getenv(LIVE_ENV) == "1"
        and confirmation == CONFIRMATION
    ):
        raise ClassificationAuditError(
            "Live accuracy capture denied; fresh independent approval is required."
        )
    _seal_packet(packet)
    raw = {
        "schema_version": 1, "provider": "cloudflare",
        "profile": PROFILE, "results": [],
    }
    predictions = {"schema_version": 1, "predictions": []}
    journal = {
        "schema_version": 1, "provider": "cloudflare",
        "profile": PROFILE, "model_id": DEFAULT_MODEL,
        "corpus_sha256": plan["corpus_sha256"],
        "system_prompt_sha256": EXPECTED_PROMPT_SHA256,
        "request_config": {
            "max_tokens": COMPLETION_TOKENS,
            "temperature": 0.1,
            "response_format": "json_object",
            "timeout_connect_sec": HTTP_TIMEOUT[0],
            "timeout_read_inactivity_sec": HTTP_TIMEOUT[1],
            "reject_if_busy": True, "retry": False, "fallback": False,
        },
        "attempts": [],
    }
    for name, body in (
        (RAW_FILE, raw), (PREDICTIONS_FILE, predictions),
        (JOURNAL_FILE, journal),
    ):
        _atomic_private_json(packet / name, body, exclusive=True)

    for entry in plan["requests"][:MAX_ATTEMPTS]:
        attempt = {
            "case_id": entry["case_id"],
            "claim_sha256": entry["claim_sha256"],
            "status": "STARTED", "duration_ms": None,
            "valid_contract": None, "error_code": None, "usage": {},
        }
        journal["attempts"].append(attempt)
        # Journal STARTED before *each* call; never auto-resume crashed runs.
        _atomic_private_json(packet / JOURNAL_FILE, journal)
        metadata = {}
        start = time.perf_counter()
        try:
            content = generate_evaluation_json(
                prompt, entry["claim_text"], model=DEFAULT_MODEL,
                max_completion_tokens=COMPLETION_TOKENS,
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
            raw["results"].append({
                "case_id": entry["case_id"], "raw_response": content,
            })
            _atomic_private_json(packet / RAW_FILE, raw)
            attempt["valid_contract"] = bool(
                validate_classification_response(content, entry["claim_text"])
            )
            if len(content) <= 8000:
                predictions["predictions"].append({
                    "case_id": entry["case_id"], "raw_response": content,
                })
                _atomic_private_json(packet / PREDICTIONS_FILE, predictions)
                attempt["status"] = (
                    "CAPTURED_VALID" if attempt["valid_contract"]
                    else "CAPTURED_INVALID_CONTRACT"
                )
            else:
                attempt["status"] = "CAPTURED_TOO_LARGE_TO_SCORE"
        attempt["duration_ms"] = max(
            0, round((time.perf_counter() - start) * 1000),
        )
        attempt["usage"] = metadata
        _atomic_private_json(packet / JOURNAL_FILE, journal)
        # A malformed output could produce an apparent abstention. Stop
        # immediately rather than concealing it by fallback or extra trials.
        if attempt["status"] != "CAPTURED_VALID":
            break

    return {
        "status": "ACCURACY_CAPTURE_FINISHED_NO_RETRIES",
        "profile": PROFILE,
        "attempted_requests": len(journal["attempts"]),
        "captured_predictions": len(predictions["predictions"]),
        "valid_responses": sum(
            a["status"] == "CAPTURED_VALID" for a in journal["attempts"]
        ),
        "stopped_early": len(journal["attempts"]) < MAX_ATTEMPTS,
        "raw_response_file": RAW_FILE,
        "audit_predictions_file": PREDICTIONS_FILE,
        "journal_file": JOURNAL_FILE,
        "enforcement_approved": False,
    }
