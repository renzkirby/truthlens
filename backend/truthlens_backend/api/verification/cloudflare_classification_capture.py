"""Direct Cloudflare classification capture with a sealed four-call ceiling.

NO fallback to Gemini/Groq, no ORM or Celery; never applies classifications.
Dry-run is the default. A live run requires an explicit local development gate
and a one-time, non-resumable packet. Do not use this without user approval.
"""
import hashlib
import json
import os
import time
from pathlib import Path

from django.conf import settings

from ..investigation_classifier import classification_system_prompt
from .classification_capture_plan import CANARY_IDS, build_capture_plan
from .classification_contract import validate_classification_response
from .classification_quality_audit import (
    ClassificationAuditError, load_classification_corpus,
)
from .cloudflare_evaluation import (
    CloudflareEvaluationError, DEFAULT_MODEL, generate_evaluation_json,
    sanitized_cloudflare_error_code,
)


MAX_LIVE_CALLS = 4
CONFIRMATION = "I_APPROVE_FOUR_CLOUDFLARE_CLASSIFICATION_CALLS"
LIVE_ENV = "TRUTHLENS_LIVE_CLOUDFLARE_CLASSIFICATION_CAPTURE"
CONNECT_AND_READ_TIMEOUT = (3, 30)
MAX_CAPTURE_MANIFEST_BYTES = 128_000
RAW_OUTPUT_NAME = "cloudflare_raw_responses.json"
SCORE_OUTPUT_NAME = "cloudflare_captured_predictions.json"
JOURNAL_NAME = "cloudflare_capture_attempts.json"
LOCK_NAME = "cloudflare_capture.lock"


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_json(path, limit):
    try:
        if not path.is_file() or path.stat().st_size > limit:
            raise ClassificationAuditError("Missing or oversized private capture input.")
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise ClassificationAuditError("Invalid private capture input.") from None


def validate_cloudflare_packet(corpus_path, packet_dir):
    """Validate exact approved inputs, model, fingerprint and private path.

    No requests or writes. Reject manipulated manifests and relabeled cases
    before allowing even one provider invocation.
    """
    packet = Path(packet_dir).expanduser().resolve()
    repo_root = Path(__file__).resolve().parents[4]
    if packet.is_relative_to(repo_root) or not packet.is_dir():
        raise ClassificationAuditError("Capture folder must exist outside Git checkout.")
    cases = load_classification_corpus(corpus_path)
    expected = build_capture_plan(
        cases, provider="cloudflare", model_id=DEFAULT_MODEL,
        limit=MAX_LIVE_CALLS, case_ids=list(CANARY_IDS),
    )
    manifest = _file_json(packet / "capture_inputs.json", MAX_CAPTURE_MANIFEST_BYTES)
    if (type(manifest) is not dict
            or set(manifest) != set(expected)
            or any(manifest[key] != expected[key] for key in expected
                   if key != "cost")
            or type(manifest.get("cost")) is not dict):
        raise ClassificationAuditError("Capture manifest does not match approved four-case plan.")
    # Preserve optional plan-only operator cost estimates; never use these to
    # authorize requests or imply a concrete billed price.
    if _file_json(packet / "predictions.json", 512_000) != {
        "schema_version": 1, "predictions": [],
    }:
        raise ClassificationAuditError("Private packet must have an empty predictions template.")
    prompt = classification_system_prompt()
    if not 1 <= len(prompt) <= 10_000:
        raise ClassificationAuditError("Unusable production classification prompt.")
    for filename in (RAW_OUTPUT_NAME, SCORE_OUTPUT_NAME, JOURNAL_NAME, LOCK_NAME):
        if (packet / filename).exists():
            raise ClassificationAuditError(
                "This packet is already used or was interrupted; never replay it."
            )
    return packet, manifest, prompt


def safe_capture_summary(manifest, prompt):
    return {
        "status": "DRY_RUN_READY_NO_PROVIDER_CALLS",
        "provider": "cloudflare",
        "model_id": DEFAULT_MODEL,
        "planned_requests": MAX_LIVE_CALLS,
        "case_ids": list(CANARY_IDS),
        "corpus_sha256": manifest["corpus_sha256"],
        "system_prompt_sha256": _sha(prompt),
        "temperature": 0.1,
        "response_format": "json_object",
        "max_output_tokens": 1024,
        "http_timeout_connect_sec": 3,
        "http_timeout_read_inactivity_sec": 30,
        "reject_if_busy": True,
        "fallback_enabled": False,
        "retry_enabled": False,
        "db_writes": 0,
        "enforcement_approved": False,
    }


def _atomic_private_json(path, data, *, exclusive=False):
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_name(path.name + ".writing")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        if exclusive and path.exists():
            raise ClassificationAuditError("Existing capture result cannot be replaced.")
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _create_lock(packet):
    # Exclusive packet lock is retained even on failure/crash. An interrupted
    # request may have cost tokens; fail closed rather than silently retrying.
    fd = os.open(packet / LOCK_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write("CAPTURE_ATTEMPTED_OR_INTERRUPTED; NEVER REPLAY THIS PACKET\n")


def execute_direct_cloudflare_capture(corpus_path, packet_dir, *,
                                      execute_live=False, confirmation=""):
    """Only execute in an explicitly approved, development-only local session."""
    packet, manifest, prompt = validate_cloudflare_packet(corpus_path, packet_dir)
    summary = safe_capture_summary(manifest, prompt)
    if not execute_live:
        return summary
    if not (
        getattr(settings, "APP_ENV", None) == "development"
        and getattr(settings, "DEBUG", False) is True
        and os.getenv(LIVE_ENV) == "1"
        and confirmation == CONFIRMATION
    ):
        raise ClassificationAuditError(
            "Live evaluation denied: development, environment opt-in and exact confirmation required."
        )
    _create_lock(packet)  # This packet can never be executed a second time.

    raw = {"schema_version": 1, "provider": "cloudflare", "results": []}
    predictions = {"schema_version": 1, "predictions": []}
    journal = {
        "schema_version": 1, "provider": "cloudflare",
        "model_id": DEFAULT_MODEL,
        "corpus_sha256": manifest["corpus_sha256"],
        "prompt_sha256": _sha(prompt),
        "request_config": {
            "max_tokens": 1024, "temperature": 0.1,
            "timeout_connect_sec": 3, "timeout_read_inactivity_sec": 30,
            "reject_if_busy": True, "fallback": False, "retry": False,
        },
        "attempts": [],
    }
    # Exclusive initial creation before any billable work.
    for name, body in (
        (RAW_OUTPUT_NAME, raw), (SCORE_OUTPUT_NAME, predictions),
        (JOURNAL_NAME, journal),
    ):
        _atomic_private_json(packet / name, body, exclusive=True)
    for entry in manifest["requests"]:
        cid = entry["case_id"]
        attempt = {
            "case_id": cid, "claim_sha256": entry["claim_sha256"],
            "status": "STARTED", "duration_ms": None,
            "valid_contract": None, "error_code": None, "usage": {},
        }
        journal["attempts"].append(attempt)
        # Journal STARTED *before* the request. No automatic resume after
        # network, serialization or process failure.
        _atomic_private_json(packet / JOURNAL_NAME, journal)
        metadata = {}
        started = time.perf_counter()
        try:
            response = generate_evaluation_json(
                prompt, entry["claim_text"],
                model=DEFAULT_MODEL, max_completion_tokens=1024,
                http_timeout=CONNECT_AND_READ_TIMEOUT,
                reject_if_busy=True, audit_metadata=metadata,
            )
        except CloudflareEvaluationError as exc:
            attempt["status"] = "PROVIDER_FAILED"
            attempt["error_code"] = sanitized_cloudflare_error_code(exc)
        except Exception:
            # Do not leak vendor bodies, credentials, prompts, exception text.
            attempt["status"] = "PROVIDER_FAILED"
            attempt["error_code"] = "UNEXPECTED_PROVIDER_FAILURE"
        else:
            # Preserve *complete, unmodified* model response, including
            # malformed JSON; never synthesize a classification or ABSTAIN.
            raw["results"].append({"case_id": cid, "raw_response": response})
            _atomic_private_json(packet / RAW_OUTPUT_NAME, raw)
            if len(response) <= 8000:
                predictions["predictions"].append({
                    "case_id": cid, "raw_response": response,
                })
                _atomic_private_json(packet / SCORE_OUTPUT_NAME, predictions)
            valid = validate_classification_response(response, entry["claim_text"])
            attempt["valid_contract"] = bool(valid)
            attempt["status"] = (
                "CAPTURED_VALID" if valid
                else "CAPTURED_INVALID_CONTRACT"
            )
            if len(response) > 8000:
                attempt["status"] = "CAPTURED_TOO_LARGE_TO_SCORE"
        attempt["duration_ms"] = max(0, round(
            (time.perf_counter() - started) * 1000,
        ))
        # Provider metadata sanitized by the existing Cloudflare adapter.
        attempt["usage"] = metadata
        _atomic_private_json(packet / JOURNAL_NAME, journal)
        if attempt["status"] != "CAPTURED_VALID":
            break
    return {
        "status": "CAPTURE_FINISHED_NO_RETRIES",
        "provider": "cloudflare", "model_id": DEFAULT_MODEL,
        "attempted_requests": len(journal["attempts"]),
        "captured_predictions": len(predictions["predictions"]),
        "valid_responses": sum(
            a["status"] == "CAPTURED_VALID" for a in journal["attempts"]
        ),
        "stopped_early": len(journal["attempts"]) < MAX_LIVE_CALLS,
        "raw_response_file": RAW_OUTPUT_NAME,
        "audit_predictions_file": SCORE_OUTPUT_NAME,
        "journal_file": JOURNAL_NAME,
        "enforcement_approved": False,
    }
