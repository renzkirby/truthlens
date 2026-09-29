"""Explicitly enrich historical URL claims without re-running verification."""

import hashlib
import hmac
import json
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import Claim
from api.services import (
    ClaimGateError,
    extract_search_query,
    validate_claim_gate_cleaned_claim,
)


def _source_digest(source_text):
    return hashlib.sha256(source_text.encode("utf-8")).hexdigest()


def _approval_token(claim_id, source_digest, analyzed_claim):
    payload = f"{claim_id}\n{source_digest}\n{analyzed_claim}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _source_for(claim, *, allow_legacy_context):
    source_context = (claim.source_context or "").strip()
    if source_context:
        return "source_context", source_context

    legacy_context = (claim.context_text or "").strip()
    if allow_legacy_context and legacy_context:
        return "context_text", legacy_context

    return None, None


class Command(BaseCommand):
    help = "Backfill missing analyzed claims for URL records with stored source text."

    def add_arguments(self, parser):
        parser.add_argument(
            "--claim-id",
            type=UUID,
            help="Process one claim UUID instead of all historical URL claims.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Generate review candidates without writing database fields.",
        )
        parser.add_argument(
            "--reviewed-analyzed-claim",
            help=(
                "Generate a non-mutating approval token for an operator-reviewed "
                "proposition without invoking ClaimGate."
            ),
        )
        parser.add_argument(
            "--approved-analyzed-claim",
            help="Exact normalized proposition printed by the targeted dry-run.",
        )
        parser.add_argument(
            "--approval-token",
            help="Token printed by the targeted dry-run for the reviewed proposition.",
        )

    def handle(self, *args, **options):
        claim_id = options["claim_id"]
        dry_run = options["dry_run"]
        reviewed_claim = options["reviewed_analyzed_claim"]
        approved_claim = options["approved_analyzed_claim"]
        approval_token = options["approval_token"]

        if dry_run:
            if reviewed_claim is not None or approved_claim or approval_token:
                raise CommandError(
                    "Reviewed or approval arguments cannot be supplied during a dry-run."
                )
            self._dry_run(claim_id=claim_id)
            return

        if reviewed_claim is not None:
            if claim_id is None:
                raise CommandError(
                    "--reviewed-analyzed-claim requires a targeted --claim-id."
                )
            if approved_claim is not None or approval_token is not None:
                raise CommandError(
                    "Reviewed-candidate mode cannot be combined with approval arguments."
                )
            self._review_targeted(
                claim_id=claim_id,
                reviewed_claim=reviewed_claim,
            )
            return

        if claim_id is None:
            raise CommandError(
                "Bulk mode is dry-run only. Apply reviewed candidates one claim at a time."
            )
        if approved_claim is None or approval_token is None:
            raise CommandError(
                "A targeted write requires --approved-analyzed-claim and "
                "--approval-token from its dry-run."
            )

        self._apply_targeted(
            claim_id=claim_id,
            approved_claim=approved_claim,
            approval_token=approval_token,
        )

    def _claim_queryset(self):
        return Claim.objects.only(
            "id",
            "claim_type",
            "url_link",
            "context_text",
            "source_context",
            "analyzed_claim",
        )

    def _dry_run(self, *, claim_id):
        claims = self._claim_queryset()
        if claim_id:
            claims = claims.filter(pk=claim_id)
        else:
            claims = claims.filter(claim_type=Claim.ClaimType.URL)

        candidates = skipped = 0
        found = False
        for claim in claims.iterator():
            found = True
            if claim.claim_type != Claim.ClaimType.URL:
                self.stdout.write(f"[SKIP] {claim.pk}: only URL claims are eligible")
                skipped += 1
                continue
            if isinstance(claim.analyzed_claim, str) and claim.analyzed_claim.strip():
                self.stdout.write(f"[SKIP] {claim.pk}: analyzed claim already exists")
                skipped += 1
                continue

            source_field, source_text = _source_for(
                claim,
                allow_legacy_context=claim_id is not None,
            )
            if source_text is None:
                reason = (
                    "stored URL source text is missing"
                    if claim_id
                    else "bulk mode requires source_context"
                )
                self.stdout.write(f"[SKIP] {claim.pk}: {reason}")
                skipped += 1
                continue
            if not claim.url_link:
                self.stdout.write(f"[SKIP] {claim.pk}: stored URL is missing")
                skipped += 1
                continue

            try:
                result = extract_search_query(source_text, claim.url_link)
                cleaned_claim = validate_claim_gate_cleaned_claim(
                    result.get("cleaned_claim")
                )
            except (ClaimGateError, ValueError, AttributeError):
                self.stdout.write(
                    f"[SKIP] {claim.pk}: ClaimGate returned no usable proposition"
                )
                skipped += 1
                continue

            if cleaned_claim == "OUT_OF_SCOPE":
                self.stdout.write(f"[SKIP] {claim.pk}: source is out of scope")
                skipped += 1
                continue

            digest = _source_digest(source_text)
            token = _approval_token(claim.pk, digest, cleaned_claim)
            self.stdout.write(
                "\n".join(
                    (
                        "[CANDIDATE]",
                        f"claim_id={claim.pk}",
                        f"claim_type={claim.claim_type}",
                        f"url={claim.url_link}",
                        f"source_field={source_field}",
                        f"source_length={len(source_text)}",
                        f"source_sha256={digest}",
                        "proposed_analyzed_claim="
                        f"{json.dumps(cleaned_claim, ensure_ascii=True)}",
                        f"proposition_length={len(cleaned_claim)}",
                        f"approval_token={token}",
                    )
                )
            )
            candidates += 1

        if not found:
            self.stdout.write("No matching claims found.")
        self.stdout.write(
            f"Dry-run complete: {candidates} candidates, {skipped} skipped"
        )

    def _review_targeted(self, *, claim_id, reviewed_claim):
        try:
            claim = self._claim_queryset().get(pk=claim_id)
        except Claim.DoesNotExist as exc:
            raise CommandError(f"Claim {claim_id} does not exist.") from exc

        if claim.claim_type != Claim.ClaimType.URL:
            raise CommandError("Only URL claims are eligible for this backfill.")
        if isinstance(claim.analyzed_claim, str) and claim.analyzed_claim.strip():
            raise CommandError("The claim already has an analyzed claim.")
        if not claim.url_link:
            raise CommandError("The URL claim has no stored URL.")

        source_field, source_text = _source_for(
            claim,
            allow_legacy_context=True,
        )
        if source_text is None:
            raise CommandError("The URL claim has no stored source text.")

        try:
            normalized_claim = validate_claim_gate_cleaned_claim(reviewed_claim)
        except ValueError as exc:
            raise CommandError("The reviewed analyzed claim is invalid.") from exc
        if normalized_claim == "OUT_OF_SCOPE":
            raise CommandError("OUT_OF_SCOPE cannot be stored as an analyzed claim.")

        digest = _source_digest(source_text)
        token = _approval_token(claim.pk, digest, normalized_claim)
        self.stdout.write(
            "\n".join(
                (
                    "[REVIEWED CANDIDATE]",
                    f"claim_id={claim.pk}",
                    f"claim_type={claim.claim_type}",
                    f"url={claim.url_link}",
                    f"source_field={source_field}",
                    f"source_length={len(source_text)}",
                    f"source_sha256={digest}",
                    "reviewed_analyzed_claim="
                    f"{json.dumps(normalized_claim, ensure_ascii=True)}",
                    f"proposition_length={len(normalized_claim)}",
                    f"approval_token={token}",
                )
            )
        )

    def _apply_targeted(self, *, claim_id, approved_claim, approval_token):
        try:
            normalized_claim = validate_claim_gate_cleaned_claim(approved_claim)
        except ValueError as exc:
            raise CommandError("The approved analyzed claim is invalid.") from exc
        if approved_claim != normalized_claim:
            raise CommandError(
                "--approved-analyzed-claim must exactly match the normalized "
                "proposition printed by the dry-run."
            )
        if normalized_claim == "OUT_OF_SCOPE":
            raise CommandError("OUT_OF_SCOPE cannot be stored as an analyzed claim.")

        with transaction.atomic():
            try:
                claim = self._claim_queryset().select_for_update().get(pk=claim_id)
            except Claim.DoesNotExist as exc:
                raise CommandError(f"Claim {claim_id} does not exist.") from exc

            if claim.claim_type != Claim.ClaimType.URL:
                raise CommandError("Only URL claims are eligible for this backfill.")
            if not claim.url_link:
                raise CommandError("The URL claim has no stored URL.")

            source_field, source_text = _source_for(
                claim,
                allow_legacy_context=True,
            )
            if source_text is None:
                raise CommandError("The URL claim has no stored source text.")

            digest = _source_digest(source_text)
            expected_token = _approval_token(claim.pk, digest, normalized_claim)
            if not hmac.compare_digest(approval_token, expected_token):
                raise CommandError(
                    "Approval token mismatch: the source or reviewed proposition changed."
                )

            existing_claim = (claim.analyzed_claim or "").strip()
            if existing_claim:
                if existing_claim == normalized_claim:
                    self.stdout.write(
                        f"[SKIP] {claim.pk}: reviewed analyzed claim is already applied"
                    )
                    return
                raise CommandError(
                    "The claim already has a different analyzed claim; no fields were changed."
                )

            Claim.objects.filter(pk=claim.pk).update(
                analyzed_claim=normalized_claim,
                source_context=source_text,
            )
            self.stdout.write(
                f"[UPDATED] {claim.pk}: analyzed claim "
                f"{json.dumps(normalized_claim, ensure_ascii=True)} "
                f"from {source_field}"
            )
