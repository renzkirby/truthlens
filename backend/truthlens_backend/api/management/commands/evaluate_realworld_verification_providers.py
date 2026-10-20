"""Compare models on independent, human-reviewed, public-source dossiers only.

Does not load Claim records, crawl URLs, or write databases. Inference and
provider quota consumption are gated behind explicit development flags.
"""
import json
import os
import statistics
import time
from collections import Counter
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from api import services
from api.verification.cloudflare_evaluation import (
    CloudflareEvaluationError,
    generate_evaluation_json,
)
from api.verification.realworld_benchmark import (
    load_corpus,
    reviewed_gold_verdict,
    VERDICTS,
)


REQUIRED_JSON_KEYS = frozenset({
    "reasoning", "verdict", "summary", "confidence_score", "score_context",
})


def _valid_raw_contract(raw):
    try:
        result = json.loads(raw)
    except (TypeError, ValueError):
        return False
    return (
        isinstance(result, dict)
        and REQUIRED_JSON_KEYS.issubset(result)
        and result.get("verdict") in VERDICTS
        and all(isinstance(result.get(field), str)
                for field in ("reasoning", "summary", "score_context"))
        and isinstance(result.get("confidence_score"), (int, float))
        and not isinstance(result.get("confidence_score"), bool)
        and 0 <= result["confidence_score"] <= 100
    )


class Command(BaseCommand):
    help = "Human-reviewed source-linked claim benchmark (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--live", action="store_true")
        parser.add_argument(
            "--provider", choices=("cloudflare", "current", "both"),
            default="cloudflare",
        )
        parser.add_argument("--limit", type=int, default=4)
        parser.add_argument("--case", action="append", default=[])
        parser.add_argument("--max-completion-tokens", type=int, default=2048)

    def handle(self, *args, **options):
        limit = options["limit"]
        budget = options["max_completion_tokens"]
        if not 1 <= limit <= 30 or not 256 <= budget <= 4096:
            raise CommandError("Limit must be 1-30; budget must be 256-4096.")
        try:
            corpus = load_corpus()
            selected_ids = options["case"]
            if len(selected_ids) != len(set(selected_ids)):
                raise CommandError("Duplicate --case selections.")
            if not set(selected_ids).issubset({c["id"] for c in corpus}):
                raise CommandError("Unknown --case ID.")
            candidates = (
                [c for c in corpus if c["id"] in selected_ids]
                if selected_ids else corpus
            )
            reviewed = [
                (case, reviewed_gold_verdict(case))
                for case in candidates
            ]
        except (ValidationError, ValueError, TypeError, KeyError) as exc:
            raise CommandError(
                "Corpus validation failed; review source and label metadata."
            ) from exc
        approved = [(case, label) for case, label in reviewed if label is not None]
        pending = sum(case["review"]["status"] == "PENDING" for case, _ in reviewed)
        rejected = sum(case["review"]["status"] == "REJECTED" for case, _ in reviewed)
        self.stdout.write(
            f"Real-world source corpus: {len(corpus)} candidates; "
            f"selected={len(reviewed)} approved={len(approved)} "
            f"pending={pending} rejected={rejected}."
        )
        if not options["live"]:
            self.stdout.write(
                "DRY RUN ONLY. Proposed verdicts are NOT gold labels. "
                "No inference, no network calls, no database writes. "
                "Review provenance and independently approve labels first."
            )
            return

        if not settings.DEBUG or os.getenv("ENABLE_CLOUDFLARE_EVALUATION") != "1":
            raise CommandError(
                "Live comparison requires DEBUG=True and "
                "ENABLE_CLOUDFLARE_EVALUATION=1."
            )
        if not approved:
            raise CommandError(
                "No independently APPROVED cases. Do not evaluate proposed labels."
            )
        if len(approved) != len(reviewed):
            raise CommandError(
                "All selected cases must be independently approved for a "
                "scored live evaluation. Choose reviewed --case IDs."
            )
        if "cloudflare" in (options["provider"], "both") and not (
            os.getenv("CLOUDFLARE_ACCOUNT_ID")
            and os.getenv("CLOUDFLARE_API_TOKEN")
        ):
            raise CommandError("Cloudflare evaluation credentials not configured.")
        target_cases = approved[:limit]
        providers = (
            ("cloudflare", "current")
            if options["provider"] == "both"
            else (options["provider"],)
        )
        self.stdout.write(
            f"Live comparison: {len(target_cases)} reviewed cases, "
            f"{len(providers) * len(target_cases)} maximum LLM calls; "
            "no database writes; no production provider promotion."
        )
        stats = {
            p: {
                "matched": 0, "attempted": 0, "valid": 0, "errors": 0,
                "confusion": Counter(), "latency_ms": [],
            }
            for p in providers
        }
        blocked = set()
        for case, expected in target_cases:
            for provider in providers:
                if provider in blocked:
                    continue
                measure = stats[provider]
                measure["attempted"] += 1
                started = time.perf_counter()
                details = {"contract_ok": False, "provider_error": ""}
                original_llm = services.call_llm_with_fallback

                def call_test_provider(system, prompt, **kwargs):
                    try:
                        if provider == "cloudflare":
                            raw = generate_evaluation_json(
                                system, prompt, max_completion_tokens=budget
                            )
                        else:
                            raw = original_llm(system, prompt, **kwargs)
                    except CloudflareEvaluationError as exc:
                        details["provider_error"] = str(exc)
                        raise services.LLMProviderUnavailableError(
                            "Comparison provider unavailable."
                        ) from None
                    details["contract_ok"] = _valid_raw_contract(raw)
                    return raw

                try:
                    # Identical production prompt and JSON verdict validator.
                    # Only LLM transport is replaced for this local call.
                    with patch(
                        "api.services.call_llm_with_fallback",
                        side_effect=call_test_provider,
                    ):
                        result = services.evaluate_claim_with_persisted_evidence(
                            case["claim"], case["evidence_snapshot"]
                        )
                    actual = result.get("verdict")
                    valid = details["contract_ok"]
                    match = valid and actual == expected
                    measure["valid"] += int(valid)
                    measure["matched"] += int(match)
                    if valid:
                        measure["confusion"][(expected, actual)] += 1
                    outcome = (
                        f"verdict={actual} expected={expected} "
                        f"contract_ok={valid} match={match}"
                    )
                except services.LLMProviderUnavailableError:
                    measure["errors"] += 1
                    reason = details["provider_error"] or "LLM_UNAVAILABLE"
                    outcome = f"error={reason}"
                    if reason.startswith(("HTTP_429", "HTTP_403", "HTTP_402")) or (
                        provider == "current" and reason == "LLM_UNAVAILABLE"
                    ):
                        blocked.add(provider)
                        self.stdout.write(
                            f"Quota/auth or provider outage for {provider}; "
                            "no further requests to that provider in this run."
                        )
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                measure["latency_ms"].append(elapsed_ms)
                self.stdout.write(
                    f"{case['id']} provider={provider} {outcome} "
                    f"elapsed_ms={elapsed_ms}"
                )

        for provider, measure in stats.items():
            latencies = measure["latency_ms"]
            median = (
                int(statistics.median(latencies)) if latencies else "n/a"
            )
            self.stdout.write(
                f"SUMMARY provider={provider} "
                f"matched={measure['matched']}/{measure['attempted']} "
                f"valid={measure['valid']} errors={measure['errors']} "
                f"median_ms={median}"
            )
            for (expected, predicted), count in sorted(
                measure["confusion"].items()
            ):
                self.stdout.write(
                    f"CONFUSION provider={provider} expected={expected} "
                    f"actual={predicted} count={count}"
                )
        self.stdout.write(
            "LIMITATION: this is a reviewed, deliberately constructed "
            "source-dossier benchmark, not a population accuracy estimate. "
            "It does not test live search, citation retrieval, or full pipeline."
        )
