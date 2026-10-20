"""Evaluate the existing persisted-evidence prompt against synthetic gold cases.

Requires an explicit live flag and DEBUG. No database writes or change to
production routing. This is NOT a factual verification of the sample claims.
"""
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from api import services
from api.verification.cloudflare_evaluation import (
    CloudflareEvaluationError,
    DEFAULT_MODEL,
    generate_evaluation_json,
)


CASES_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "verification_provider_cases.json"
)
REQUIRED_FIELDS = {
    "reasoning", "verdict", "summary", "confidence_score", "score_context",
}
VERDICTS = {"FACT", "FAKE", "MISLEADING", "UNVERIFIED", "SATIRE"}


class Command(BaseCommand):
    help = (
        "Development-only opt-in model comparison using synthetic evidence "
        "and TruthLens's existing persisted-evidence evaluator. No DB writes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--live", action="store_true",
            help="Explicitly authorize bounded external inference calls.",
        )
        parser.add_argument(
            "--provider", choices=("cloudflare", "current", "both"),
            default="cloudflare",
            help="Current = existing Gemini/Groq fallback, only when explicitly selected.",
        )
        parser.add_argument(
            "--limit", type=int, default=4,
            help="Number of fixture cases per provider (1-8, default 4).",
        )

    def handle(self, *args, **options):
        count = options["limit"]
        if not 1 <= count <= 8:
            raise CommandError("--limit must be 1-8.")
        cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
        if not isinstance(cases, list) or len(cases) != 8:
            raise CommandError("Synthetic fixture set is missing or invalid.")
        providers = (
            ("cloudflare", "current")
            if options["provider"] == "both"
            else (options["provider"],)
        )
        planned_calls = len(providers) * count

        if not options["live"]:
            self.stdout.write(
                "DRY RUN: development-only persisted-evidence benchmark; "
                f"{count} synthetic cases, providers={','.join(providers)}, "
                f"up to {planned_calls} provider calls. No network or DB writes. "
                "Add --live to execute explicitly."
            )
            return

        if not settings.DEBUG or os.getenv("ENABLE_CLOUDFLARE_EVALUATION") != "1":
            raise CommandError(
                "Live evaluation requires DEBUG=True and "
                "ENABLE_CLOUDFLARE_EVALUATION=1 in this development process."
            )

        if "cloudflare" in providers and not (
            os.getenv("CLOUDFLARE_ACCOUNT_ID")
            and os.getenv("CLOUDFLARE_API_TOKEN")
        ):
            raise CommandError(
                "Set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN "
                "locally before running the live Cloudflare evaluation."
            )

        self.stdout.write(
            f"Live synthetic evaluation: {planned_calls} max calls; "
            "no live claims, no DB writes, no model promotion. "
            f"Cloudflare model={DEFAULT_MODEL}."
        )

        scores = {name: {"matched": 0, "completed": 0, "failed": 0} for name in providers}
        for case in cases[:count]:
            if not isinstance(case, dict) or not {
                "id", "claim", "evidence", "expected_verdict"
            }.issubset(case):
                raise CommandError("Invalid synthetic case schema.")
            if case["expected_verdict"] not in VERDICTS:
                raise CommandError("Unsupported expected verdict in fixture.")
            for provider in providers:
                started = time.perf_counter()
                raw_contract = {"valid": False}

                def invoke_existing_prompt(system_instructions, user_prompt, **kwargs):
                    if provider == "cloudflare":
                        try:
                            raw = generate_evaluation_json(
                                system_instructions, user_prompt
                            )
                        except CloudflareEvaluationError as exc:
                            raw_contract["provider_error"] = str(exc)
                            # The production evaluator propagates this typed
                            # exception instead of converting it to UNVERIFIED.
                            raise services.LLMProviderUnavailableError(
                                "Evaluation provider is unavailable."
                            ) from None
                    else:
                        raw = services_original_call(
                            system_instructions, user_prompt, **kwargs
                        )

                    # Count a JSON contract failure separately from a
                    # legitimate evidence-based UNVERIFIED verdict.
                    try:
                        obj = json.loads(raw)
                        raw_contract["valid"] = (
                            isinstance(obj, dict)
                            and REQUIRED_FIELDS.issubset(obj)
                            and obj.get("verdict") in VERDICTS
                            and isinstance(obj.get("reasoning"), str)
                            and isinstance(obj.get("summary"), str)
                            and isinstance(obj.get("score_context"), str)
                            and isinstance(obj.get("confidence_score"), (int, float))
                            and not isinstance(obj.get("confidence_score"), bool)
                        )
                    except (TypeError, ValueError):
                        raw_contract["valid"] = False
                    return raw

                # Inject only during this offline assessment, retaining the
                # exact production evidence-bound prompt and result validator.
                services_original_call = services.call_llm_with_fallback
                try:
                    with patch(
                        "api.services.call_llm_with_fallback",
                        side_effect=invoke_existing_prompt,
                    ):
                        result = services.evaluate_claim_with_persisted_evidence(
                            case["claim"], case["evidence"], "NEUTRAL"
                        )
                    verdict = result.get("verdict")
                    contract_ok = raw_contract["valid"]
                    good = contract_ok and verdict == case["expected_verdict"]
                    scores[provider]["completed"] += 1
                    scores[provider]["matched"] += int(good)
                    outcome = (
                        f"verdict={verdict} expected={case['expected_verdict']} "
                        f"contract_ok={contract_ok} match={good}"
                    )
                except services.LLMProviderUnavailableError:
                    scores[provider]["failed"] += 1
                    verdict = None
                    error_label = raw_contract.get("provider_error", "LLM_UNAVAILABLE")
                    outcome = f"error={error_label}"
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                self.stdout.write(
                    f"{case['id']} provider={provider} {outcome} "
                    f"elapsed_ms={elapsed_ms}"
                )

                # No automatic repeated requests after a provider quota failure.
                if provider == "cloudflare" and verdict is None and (
                    "HTTP_429" in outcome or "HTTP_403" in outcome
                ):
                    self.stdout.write("Cloudflare capacity/authorization barrier: stopping.")
                    return

        for provider, metrics in scores.items():
            self.stdout.write(
                f"SUMMARY provider={provider} "
                f"matching={metrics['matched']}/{metrics['completed']} "
                f"failed={metrics['failed']}; synthetic cases only."
            )
        self.stdout.write(
            "NOT A PRODUCTION ACCURACY SCORE: human-labeled real claims, "
            "citation audits, and provider availability must be tested separately."
        )
