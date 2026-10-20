"""Development-only, source-bound explanation and efficiency audit.

No user claims or verification database access. Prompts are exactly those used
by the existing persisted-evidence evaluator. Model results are NOT judgments
of explanation quality; humans must inspect each final user-facing explanation.
"""
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from api import services
from api.verification.cloudflare_evaluation import (
    CloudflareEvaluationError, DEFAULT_MODEL, generate_evaluation_json,
)
from api.verification.mistral_evaluation import (
    DEFAULT_MISTRAL_MODEL, MistralEvaluationError,
    generate_mistral_evaluation_json,
)
from api.verification.provider_audit_metrics import (
    validate_user_facing_evaluation,
)
from api.verification.realworld_benchmark import (
    load_corpus, reviewed_gold_verdict,
)


AUDIT_DIR_NAME = ".provider_audit_reports"
MODEL_NAMES = {
    "cloudflare": DEFAULT_MODEL,
    "mistral": DEFAULT_MISTRAL_MODEL,
}


def _label(value):
    return str(value) if value is not None else "n/a"


def _new_review_template():
    # These fields are *intentionally unscored* pending human assessment.
    return {
        "evidence_grounded_0_to_2": None,
        "material_context_preserved_0_to_2": None,
        "source_independence_respected_0_to_2": None,
        "unsupported_inference_present": None,
        "confidence_calibrated_0_to_2": None,
        "reviewer_notes": "",
        "review_completed": False,
    }


def _save_report(report):
    """Create a private, untracked local JSON report; never silently overwrite."""
    directory = Path(settings.BASE_DIR) / AUDIT_DIR_NAME
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    file_path = directory / f"audit-{now}-{uuid4().hex[:10]}.json"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    descriptor = os.open(file_path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as writer:
            json.dump(report, writer, indent=2, ensure_ascii=False)
            writer.write("\n")
    except Exception:
        file_path.unlink(missing_ok=True)
        raise
    return file_path


class Command(BaseCommand):
    help = "Optional model explanation, usage and latency audit; development only."

    def add_arguments(self, parser):
        parser.add_argument("--live", action="store_true")
        parser.add_argument(
            "--provider", choices=("cloudflare", "mistral", "both"),
            default="cloudflare",
        )
        parser.add_argument("--case", action="append", default=[])
        parser.add_argument("--limit", type=int, default=4)
        parser.add_argument("--max-completion-tokens", type=int, default=2048)
        parser.add_argument(
            "--save-review", action="store_true",
            help="Save human-review worksheet under ignored .provider_audit_reports.",
        )

    def handle(self, *args, **opts):
        selection = opts["case"]
        budget = opts["max_completion_tokens"]
        limit = opts["limit"]
        if not 1 <= limit <= 10 or not 256 <= budget <= 4096:
            raise CommandError("Limit must be 1-10, completion budget 256-4096.")
        if len(selection) != len(set(selection)):
            raise CommandError("Repeated --case IDs are not allowed.")
        try:
            cases = load_corpus()
            lookup = {c["id"]: c for c in cases}
            if not set(selection).issubset(lookup):
                raise CommandError("Unknown --case ID.")
            chosen = [lookup[x] for x in selection] if selection else cases[:limit]
            approved = [(c, reviewed_gold_verdict(c)) for c in chosen]
        except (ValidationError, ValueError, TypeError, KeyError) as exc:
            raise CommandError("Invalid reviewed corpus or review metadata.") from exc
        n_approved = sum(label is not None for _, label in approved)
        providers = (
            ("cloudflare", "mistral")
            if opts["provider"] == "both" else (opts["provider"],)
        )
        self.stdout.write(
            f"Quality audit: selected={len(approved)} approved={n_approved} "
            f"providers={','.join(providers)} max_requests={min(len(approved), limit) * len(providers)}."
        )
        if not opts["live"]:
            if opts["save_review"]:
                raise CommandError("--save-review requires --live.")
            self.stdout.write(
                "DRY RUN: no external calls, no files, no database writes. "
                "Live runs require explicit approved --case IDs."
            )
            return
        if not selection:
            raise CommandError("Live audit requires explicit --case selection.")
        if len(selection) > limit:
            raise CommandError("Selected case count exceeds --limit.")
        if n_approved != len(approved):
            raise CommandError("All selected cases require human-approved labels.")
        if (
            not settings.DEBUG or getattr(settings, "APP_ENV", None) != "development"
            or os.getenv("ENABLE_PROVIDER_QUALITY_AUDIT") != "1"
        ):
            raise CommandError(
                "Live audit requires development APP_ENV, DEBUG=True and "
                "ENABLE_PROVIDER_QUALITY_AUDIT=1."
            )
        if "cloudflare" in providers and not (
            os.getenv("CLOUDFLARE_ACCOUNT_ID")
            and os.getenv("CLOUDFLARE_API_TOKEN")
        ):
            raise CommandError("Missing local Cloudflare audit credentials.")
        if "mistral" in providers and not os.getenv("MISTRAL_API_KEY"):
            raise CommandError("Missing local Mistral audit credentials.")

        stats = {
            provider: {
                "attempted": 0, "matched": 0, "valid": 0,
                "failures": 0, "durations_ms": [],
                "prompt_tokens": 0, "completion_tokens": 0,
                "complete_usage_records": 0,
            }
            for provider in providers
        }
        report = {
            "purpose": "public-source human quality audit; NOT population accuracy",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "model_prompts": "existing persisted_evidence_evaluation",
            "max_completion_tokens": budget,
            "results": [],
        }
        blocked = set()
        for case, expected in approved:
            for provider in providers:
                if provider in blocked:
                    continue
                metric = stats[provider]
                metric["attempted"] += 1
                started = time.perf_counter()
                usage = {}
                captured = {"validated": None}
                production_llm = services.call_llm_with_fallback

                def call_audit_provider(system_prompt, user_prompt, **kwargs):
                    try:
                        if provider == "cloudflare":
                            raw = generate_evaluation_json(
                                system_prompt, user_prompt,
                                max_completion_tokens=budget,
                                audit_metadata=usage,
                            )
                        else:
                            raw = generate_mistral_evaluation_json(
                                system_prompt, user_prompt,
                                max_completion_tokens=budget,
                                audit_metadata=usage,
                            )
                    except (CloudflareEvaluationError, MistralEvaluationError) as exc:
                        captured["error"] = str(exc)
                        raise services.LLMProviderUnavailableError(
                            "Audit provider unavailable."
                        ) from None
                    captured["validated"] = validate_user_facing_evaluation(raw)
                    return raw

                prediction = None
                user_explanation = None
                error = None
                try:
                    with patch(
                        "api.services.call_llm_with_fallback",
                        side_effect=call_audit_provider,
                    ):
                        result = services.evaluate_claim_with_persisted_evidence(
                            case["claim"], case["evidence_snapshot"],
                        )
                    prediction = result.get("verdict")
                    valid = captured["validated"] is not None
                    metric["valid"] += int(valid)
                    metric["matched"] += int(valid and prediction == expected)
                    if valid:
                        user_explanation = captured["validated"]
                    else:
                        metric["failures"] += 1
                        error = "INVALID_JSON_CONTRACT"
                        prediction = None
                except services.LLMProviderUnavailableError:
                    metric["failures"] += 1
                    error = captured.get("error", "LLM_UNAVAILABLE")
                    if error.startswith(("HTTP_402", "HTTP_403", "HTTP_429")):
                        blocked.add(provider)
                latency_ms = int((time.perf_counter() - started) * 1000)
                metric["durations_ms"].append(latency_ms)
                prompt_tokens = usage.get("prompt_tokens")
                completion_tokens = usage.get("completion_tokens")
                if prompt_tokens is not None and completion_tokens is not None:
                    metric["prompt_tokens"] += prompt_tokens
                    metric["completion_tokens"] += completion_tokens
                    metric["complete_usage_records"] += 1
                correct = user_explanation is not None and prediction == expected
                self.stdout.write(
                    f"{case['id']} provider={provider} "
                    f"verdict={prediction if error is None else 'n/a'} "
                    f"expected={expected} match={correct} "
                    f"error={_label(error)} ms={latency_ms} "
                    f"prompt_tokens={_label(prompt_tokens)} "
                    f"completion_tokens={_label(completion_tokens)} "
                    f"reasoning_tokens={_label(usage.get('reasoning_tokens'))} "
                    f"finish={_label(usage.get('finish_reason'))}"
                )
                report["results"].append({
                    "case_id": case["id"],
                    "domain": case["domain"],
                    "language": case["language"],
                    "claim": case["claim"],
                    "evidence_snapshot": case["evidence_snapshot"],
                    "source_urls": [x["url"] for x in case["sources"]],
                    "approved_reference_verdict": expected,
                    "provider": provider,
                    "model": MODEL_NAMES[provider],
                    "model_final_evaluation": user_explanation,
                    "model_verdict": prediction if user_explanation else None,
                    "verdict_match": correct,
                    "provider_error": error,
                    "duration_ms": latency_ms,
                    "provider_reported_usage": usage,
                    "human_review_worksheet": _new_review_template(),
                })
        for provider, item in stats.items():
            median = (
                int(statistics.median(item["durations_ms"]))
                if item["durations_ms"] else "n/a"
            )
            self.stdout.write(
                f"SUMMARY provider={provider} matched={item['matched']}/{item['attempted']} "
                f"valid={item['valid']} failures={item['failures']} "
                f"median_ms={median} "
                f"token_records={item['complete_usage_records']}/{item['attempted']} "
                f"input_tokens_known={item['prompt_tokens']} "
                f"output_tokens_known={item['completion_tokens']}"
            )
        if opts["save_review"]:
            try:
                saved = _save_report(report)
            except OSError as exc:
                raise CommandError(
                    f"Could not save local report ({type(exc).__name__})."
                ) from None
            self.stdout.write(f"REVIEW_REPORT: {saved}")
        self.stdout.write(
            "HUMAN REVIEW REQUIRED: verdict agreement does not measure reasoning "
            "quality. Vendor token counts can omit internal reasoning; actual "
            "billing and free-tier Neurons require provider dashboard checks. "
            "No production routing or database writes."
        )
