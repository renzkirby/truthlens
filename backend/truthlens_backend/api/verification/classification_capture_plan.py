"""Offline-only planning and private response templates for subject-classification audits.

Deliberately no provider SDKs, HTTP clients, ORM, Celery, or model inference.
A plan is NOT an execution authorization, spend ceiling, or accuracy result.
"""
import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path

from .classification_quality_audit import ClassificationAuditError


PROVIDERS = frozenset({"gemini", "cloudflare", "groq"})
MAX_PLANNED_REQUESTS = 32
MAX_OUTPUT_TOKENS = 1024
# Safety-focused canary rather than statistically representative sampling.
CANARY_IDS = (
    "cross_spacecraft",
    "cross_school_sport",
    "ambiguous_plan",
    "injection_civic",
)
SCHEMA_VERSION = 1


def build_capture_plan(
    cases, *, provider, limit=4, case_ids=None, model_id="NOT_SELECTED",
    input_price_per_million=None, output_price_per_million=None,
    assumed_input_tokens=None, assumed_output_tokens=None,
):
    """Return metadata and the exact claim inputs for an OFFLINE request plan.

    Excludes all reference labels from the capture inputs to prevent leakage.
    Only independently approved cases can enter an experiment plan.
    """
    if provider not in PROVIDERS:
        raise ClassificationAuditError("Choose a supported evaluation provider.")
    if type(limit) is not int or not 1 <= limit <= MAX_PLANNED_REQUESTS:
        raise ClassificationAuditError("The offline request limit must be 1 through 32.")
    if type(model_id) is not str or not 1 <= len(model_id.strip()) <= 140:
        raise ClassificationAuditError("The model identifier must be 1 to 140 characters.")
    if any(item["review"]["status"] != "APPROVED" for item in cases):
        raise ClassificationAuditError(
            "This plan requires every corpus case to have a reviewed APPROVED label."
        )

    lookup = {item["id"]: item for item in cases}
    if case_ids is not None:
        if not case_ids or len(case_ids) != len(set(case_ids)):
            raise ClassificationAuditError("Specify unique, nonempty case IDs.")
        if any(cid not in lookup for cid in case_ids):
            raise ClassificationAuditError("Unknown case ID in evaluation selection.")
        if len(case_ids) > limit:
            raise ClassificationAuditError("The selected case count exceeds --limit.")
        selected_ids = list(case_ids)
    else:
        canaries = [cid for cid in CANARY_IDS if cid in lookup]
        remaining = sorted(cid for cid in lookup if cid not in canaries)
        selected_ids = (canaries + remaining)[:limit]

    pricing_fields = (
        input_price_per_million, output_price_per_million,
        assumed_input_tokens, assumed_output_tokens,
    )
    if any(value is not None for value in pricing_fields):
        if any(value is None for value in pricing_fields):
            raise ClassificationAuditError(
                "Illustrative cost requires both provider prices and both token assumptions."
            )
        try:
            input_rate = Decimal(str(input_price_per_million))
            output_rate = Decimal(str(output_price_per_million))
        except Exception as exc:
            raise ClassificationAuditError("Invalid illustrative price inputs.") from None
        if not all(x.is_finite() and 0 <= x <= 100000 for x in (input_rate, output_rate)):
            raise ClassificationAuditError("Illustrative prices must be finite and nonnegative.")
        if (type(assumed_input_tokens) is not int
                or not 1 <= assumed_input_tokens <= 100000
                or type(assumed_output_tokens) is not int
                or not 1 <= assumed_output_tokens <= MAX_OUTPUT_TOKENS):
            raise ClassificationAuditError("Invalid token assumptions.")
        price = (
            Decimal(len(selected_ids))
            * (
                input_rate * Decimal(assumed_input_tokens)
                + output_rate * Decimal(assumed_output_tokens)
            ) / Decimal(1_000_000)
        )
        cost = {
            "status": "ILLUSTRATIVE_ONLY",
            "estimated_usd": str(price.quantize(Decimal("0.000001"))),
            "input_price_per_million": str(input_rate),
            "output_price_per_million": str(output_rate),
            "assumed_input_tokens": assumed_input_tokens,
            "assumed_output_tokens": assumed_output_tokens,
            "warning": "User-entered rates and token assumptions; NOT a spend cap or quote.",
        }
    else:
        cost = {
            "status": "UNKNOWN",
            "warning": "No provider rates or measured prompt/token counts supplied.",
        }

    requests = [{
        "case_id": cid,
        "claim_text": lookup[cid]["claim_text"],
        "claim_sha256": hashlib.sha256(
            lookup[cid]["claim_text"].encode("utf-8")
        ).hexdigest(),
    } for cid in selected_ids]
    corpus_fingerprint = hashlib.sha256(json.dumps(
        cases, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "OFFLINE_PREPARATION_ONLY",
        "provider": provider,
        "model_id": model_id.strip(),
        "classifier_operation": "investigation_classification",
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "planned_requests": len(requests),
        "limit": limit,
        "approved_references_in_source": len(cases),
        "corpus_sha256": corpus_fingerprint,
        "cost": cost,
        "requests": requests,
    }


def summarize_capture_plan(plan):
    """Safe CLI response: never print claim text, reference labels or raw results."""
    return {
        key: plan[key] for key in (
            "schema_version", "status", "provider", "model_id",
            "classifier_operation", "max_output_tokens",
            "planned_requests", "limit", "approved_references_in_source",
            "corpus_sha256", "cost",
        )
    } | {
        "case_ids": [entry["case_id"] for entry in plan["requests"]],
        "provider_calls": 0,
        "db_writes": 0,
        "enforcement_approved": False,
    }


def _private_output_directory(location):
    target = Path(location).expanduser().resolve()
    # This module is in repository/backend/truthlens_backend/api/verification/.
    # Protect the full checkout even if the .git marker is unavailable.
    # Never risk committing claim texts, model responses or reviewed inputs.
    repo_root = Path(__file__).resolve().parents[4]
    # Also check discoverable Git ancestors, including linked worktrees.
    git_roots = [parent for parent in Path(__file__).resolve().parents
                 if (parent / ".git").exists()]
    if target.is_relative_to(repo_root) or any(
        target.is_relative_to(root) for root in git_roots
    ):
        raise ClassificationAuditError(
            "Private output must be outside the application and Git checkout."
        )
    if target.exists():
        raise ClassificationAuditError(
            "Output directory already exists; refusing to replace prior captures."
        )
    return target


def write_private_capture_package(plan, location):
    """Explicit local-only export; all predictions intentionally empty."""
    target = _private_output_directory(location)
    manifest = json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
    predictions = json.dumps({
        "schema_version": SCHEMA_VERSION, "predictions": [],
    }, indent=2) + "\n"
    readme = (
        "TRUTHLENS — OFFLINE CLASSIFICATION EVALUATION PREPARATION\n"
        "This folder is PRIVATE. It contains claim texts, not reference labels.\n"
        "NO model calls were made, and this plan grants no authorization to make any.\n"
        "Obtain explicit authorization, current provider pricing, and prompt/model\n"
        "version details before any separate live execution. Each provider\n"
        "requires its own complete unaltered response capture; never fabricate\n"
        "quoted evidence or reconstruct responses from candidate_domains.\n"
        "predictions.json schema: {schema_version:1, predictions:[\n"
        "  {case_id:<listed ID>, raw_response:<complete original JSON string>}\n"
        "]}\n"
        "Do not commit/share full text or raw responses. Keep request metadata\n"
        "and any failures separately; missing responses must stay MISSING.\n"
        "The production classifier prompt/version, exact input and per-provider\n"
        "direct-vs-fallback routing must be pinned for a valid comparison.\n"
        "Later run: manage.py audit_investigation_classification\n"
        "  --corpus <PRIVATE_APPROVED_CORPUS> --predictions <PRIVATE_PREDICTIONS>\n"
        "That audit is read-only; it never authorizes partner enforcement.\n"
    )
    try:
        target.mkdir(mode=0o700)
        for name, body in (
            ("capture_inputs.json", manifest),
            ("predictions.json", predictions),
            ("README.txt", readme),
        ):
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            fd = os.open(target / name, flags, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(body)
    except OSError:
        raise ClassificationAuditError(
            "Could not create private capture package; check path and permissions."
        ) from None
    return target
