from copy import deepcopy
import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from api.models import (
    AdjudicationDecision,
    AdjudicationDecisionEvidenceSnapshot,
    Claim,
    FactualCorrectionProposal,
    FactualCorrectionRequest,
    ModerationCase,
    OfficialFactCheck,
    OfficialFactCheckPublicationSnapshot,
    OfficialFactCheckSource,
    OfficialFactCheckSourceEvidenceLink,
)
from api.publication_snapshot_schema import (
    EDITORIAL_REVISION_SCHEMA_VERSION,
    FACTUAL_CORRECTION_SCHEMA_VERSION,
    FIRST_PUBLICATION_SCHEMA_VERSION,
    PublicationSnapshotSchemaError,
    validate_publication_snapshot,
)
from api.publishing_service import (
    PublishingConflict,
    _validate_editorial_revision_chain,
)
from api.tests.workspace.test_factual_correction_proposal import (
    FactualCorrectionProposalFixtures,
)


class FactualCorrectionPublicationHistoryFixtures(
    FactualCorrectionProposalFixtures
):
    def make_prepared_context(self, *, suffix="v3", editorial_first=False):
        if not editorial_first:
            context = self.make_proposal_context(suffix=suffix)
        else:
            context = self.make_published_context(suffix=f"{suffix}-initial")
            revision = self.make_submitted_revision(
                context,
                reason="Clarify the article before factual correction.",
            )
            self.replace(context, revision)
            context["published"] = revision
            context["seal"] = revision.publication_snapshot
            evidence = context["evidence"][0]
            context["evidence_case"] = ModerationCase.objects.create(
                case_type=ModerationCase.CaseType.EVIDENCE,
                evidence_submission=evidence,
                organization=self.organization,
                source=ModerationCase.Source.EVIDENCE_SUBMISSION,
                status=ModerationCase.Status.RESOLVED,
                resolution_code=evidence.evidence_status,
                resolution_summary="Original evidence review.",
                resolved_by=self.moderator,
                resolved_at=timezone.now(),
            )
            reservation = self.request_correction(context)
            context.update(
                correction_request=reservation["request"],
                correction_case=reservation["case"],
            )
            context["correction_review"] = self.review_correction(context)

        proposal = self.save_proposal(context)
        context["prepared_proposal"] = self.prepare_proposal(
            context,
            proposal,
        )["proposal"]
        return context

    def finalize_prepared_correction(self, context):
        """Test-only synthesis of the B3B3B objects; no production handoff."""

        predecessor = context["published"]
        predecessor_decision = context["decision"]
        predecessor_seal = context["seal"]
        request = context["correction_request"]
        proposal = context["prepared_proposal"]
        prepared_payload = proposal.prepared_payload

        predecessor_decision.is_current = False
        predecessor_decision.save(update_fields=["is_current"])
        decision = AdjudicationDecision.objects.create(
            claim=context["claim"],
            moderation_case=context["correction_case"],
            verdict=proposal.verdict,
            canonical_claim=proposal.canonical_claim,
            rationale=proposal.rationale,
            decided_by=self.lead,
            organization=self.organization,
            decision_source=AdjudicationDecision.DecisionSource.HUMAN_REVIEW,
            revision_number=predecessor_decision.revision_number + 1,
            supersedes=predecessor_decision,
            is_current=True,
        )
        decision_snapshot = AdjudicationDecisionEvidenceSnapshot.objects.create(
            decision=decision,
            claim_id=context["claim"].id,
            evidence_records=[
                item["record"]
                for item in prepared_payload["evidence_basis"]["items"]
            ],
        )
        published_at = timezone.now()
        OfficialFactCheck.objects.filter(pk=predecessor.pk).update(
            publication_status=OfficialFactCheck.PublicationStatus.ARCHIVED,
            archived_at=published_at,
        )
        successor = OfficialFactCheck.objects.create(
            claim=context["claim"],
            adjudication_decision=decision,
            organization=self.organization,
            canonical_claim=decision.canonical_claim,
            verdict=decision.verdict,
            headline=proposal.headline,
            summary=proposal.summary,
            article_body=proposal.article_body,
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            version=predecessor.version + 1,
            drafted_by=self.researcher,
            submitted_for_review_at=published_at,
            reviewed_by=self.lead,
            reviewed_at=published_at,
            published_by=self.lead,
            published_at=published_at,
            supersedes=predecessor,
            revision_kind=OfficialFactCheck.RevisionKind.FACTUAL_CORRECTION,
            revision_reason=request.correction_reason,
            revision_requested_by=request.requested_by,
            revision_requested_at=request.requested_at,
        )
        for prepared_source in prepared_payload["sources"]:
            source = OfficialFactCheckSource.objects.create(
                fact_check=successor,
                url=prepared_source["url"],
                source_type=(
                    OfficialFactCheckSource.SourceType.VERIFIED_EVIDENCE
                    if prepared_source["evidence"]
                    else OfficialFactCheckSource.SourceType.MODERATOR_ADDED
                ),
                is_editorially_selected=True,
                added_by=self.lead,
            )
            for link in prepared_source["evidence"]:
                OfficialFactCheckSourceEvidenceLink.objects.create(
                    source=source,
                    snapshot=decision_snapshot,
                    captured_evidence_id=link["evidence_id"],
                )

        payload = OfficialFactCheckPublicationSnapshot.build_payload(
            fact_check=successor,
            decision_snapshot=decision_snapshot,
            schema_version=FACTUAL_CORRECTION_SCHEMA_VERSION,
            predecessor_snapshot=predecessor_seal,
            correction_request=request,
            prepared_proposal=proposal,
        )
        seal = OfficialFactCheckPublicationSnapshot.objects.create(
            fact_check=successor,
            decision_snapshot=decision_snapshot,
            schema_version=FACTUAL_CORRECTION_SCHEMA_VERSION,
            captured_at=published_at,
            payload=payload,
        )
        FactualCorrectionRequest.objects.filter(pk=request.pk).update(
            status=FactualCorrectionRequest.Status.COMPLETED
        )
        ModerationCase.objects.filter(pk=context["correction_case"].pk).update(
            status=ModerationCase.Status.RESOLVED,
            resolution_code=decision.verdict,
            resolution_summary=decision.rationale,
            resolved_by=self.lead,
            resolved_at=published_at,
        )
        Claim.objects.filter(pk=context["claim"].pk).update(
            final_verdict=decision.verdict
        )
        predecessor.refresh_from_db()
        context.update(
            decision=decision,
            decision_snapshot=decision_snapshot,
            published=successor,
            seal=seal,
        )
        return successor

    def validate_history(self, context, *, predecessor=None):
        predecessor = predecessor or context["published"]
        return _validate_editorial_revision_chain(
            predecessor=predecessor,
            fact_checks=list(
                OfficialFactCheck.objects.filter(claim=context["claim"]).order_by(
                    "version", "created_at", "id"
                )
            ),
            publication_snapshots=list(
                OfficialFactCheckPublicationSnapshot.objects.filter(
                    fact_check__claim=context["claim"]
                ).order_by("fact_check_id", "id")
            ),
            decision=predecessor.adjudication_decision,
            decision_snapshot=predecessor.publication_snapshot.decision_snapshot,
            organization=self.organization,
        )


class FactualCorrectionPublicationSchemaTests(
    FactualCorrectionPublicationHistoryFixtures,
    TestCase,
):
    def test_valid_v3_payload_and_v1_v2_compatibility(self):
        context = self.make_prepared_context(suffix="schema-compatible")
        self.assertEqual(
            context["seal"].schema_version,
            FIRST_PUBLICATION_SCHEMA_VERSION,
        )
        validate_publication_snapshot(
            schema_version=FIRST_PUBLICATION_SCHEMA_VERSION,
            payload=context["seal"].payload,
        )
        corrected = self.finalize_prepared_correction(context)
        correction_payload = corrected.publication_snapshot.payload
        validate_publication_snapshot(
            schema_version=FACTUAL_CORRECTION_SCHEMA_VERSION,
            payload=correction_payload,
        )
        self.assertNotIn("revision", correction_payload)
        self.assertEqual(
            correction_payload["correction"]["prepared_proposal_id"],
            str(context["prepared_proposal"].id),
        )

        revision = self.make_submitted_revision(context)
        self.replace(context, revision)
        validate_publication_snapshot(
            schema_version=EDITORIAL_REVISION_SCHEMA_VERSION,
            payload=revision.publication_snapshot.payload,
        )

    def test_v3_schema_rejects_missing_unknown_malformed_or_inconsistent_fields(self):
        context = self.make_prepared_context(suffix="schema-strict")
        corrected = self.finalize_prepared_correction(context)
        payload = corrected.publication_snapshot.payload
        malformed = []

        missing = deepcopy(payload)
        missing["correction"].pop("prepared_proposal_id")
        malformed.append(missing)
        unknown = deepcopy(payload)
        unknown["correction"]["editorial_revision"] = True
        malformed.append(unknown)
        wrong_kind = deepcopy(payload)
        wrong_kind["correction"]["revision_kind"] = "EDITORIAL_REVISION"
        malformed.append(wrong_kind)
        wrong_decision = deepcopy(payload)
        wrong_decision["correction"]["new_decision_id"] = str(uuid.uuid4())
        malformed.append(wrong_decision)
        malformed_version = deepcopy(payload)
        malformed_version["correction"]["prepared_proposal_version"] = True
        malformed.append(malformed_version)
        wrong_proposal_schema = deepcopy(payload)
        wrong_proposal_schema["correction"]["prepared_payload_schema_version"] = 99
        malformed.append(wrong_proposal_schema)
        boolean_proposal_schema = deepcopy(payload)
        boolean_proposal_schema["correction"][
            "prepared_payload_schema_version"
        ] = True
        malformed.append(boolean_proposal_schema)
        malformed_actor = deepcopy(payload)
        malformed_actor["correction"]["approved_by"] = {"id": "1"}
        malformed.append(malformed_actor)
        untrimmed_reason = deepcopy(payload)
        untrimmed_reason["correction"]["correction_reason"] = " reason "
        malformed.append(untrimmed_reason)

        for candidate in malformed:
            with self.subTest(candidate=candidate["correction"]), self.assertRaises(
                PublicationSnapshotSchemaError
            ):
                validate_publication_snapshot(
                    schema_version=FACTUAL_CORRECTION_SCHEMA_VERSION,
                    payload=candidate,
                )

        with self.assertRaises(PublicationSnapshotSchemaError):
            validate_publication_snapshot(
                schema_version=EDITORIAL_REVISION_SCHEMA_VERSION,
                payload=payload,
            )

    def test_v3_builder_requires_exact_durable_inputs_and_new_decision_snapshot(self):
        context = self.make_prepared_context(suffix="builder-inputs")
        corrected = self.finalize_prepared_correction(context)
        values = {
            "fact_check": corrected,
            "decision_snapshot": context["decision_snapshot"],
            "schema_version": FACTUAL_CORRECTION_SCHEMA_VERSION,
            "predecessor_snapshot": corrected.supersedes.publication_snapshot,
            "correction_request": context["correction_request"],
            "prepared_proposal": context["prepared_proposal"],
        }
        for missing in (
            "predecessor_snapshot",
            "correction_request",
            "prepared_proposal",
        ):
            candidate = dict(values)
            candidate[missing] = None
            with self.subTest(missing=missing), self.assertRaises(ValidationError):
                OfficialFactCheckPublicationSnapshot.build_payload(**candidate)

        with self.assertRaises(ValidationError):
            OfficialFactCheckPublicationSnapshot.build_payload(
                **{
                    **values,
                    "decision_snapshot": (
                        corrected.supersedes.publication_snapshot.decision_snapshot
                    ),
                }
            )
        with self.assertRaises(ValidationError):
            OfficialFactCheckPublicationSnapshot.build_payload(
                **{**values, "schema_version": FIRST_PUBLICATION_SCHEMA_VERSION}
            )


    def test_v3_builder_requires_the_actual_preparing_adjudicator_and_active_case(self):
        context = self.make_prepared_context(suffix="builder-approval-identity")
        corrected = self.finalize_prepared_correction(context)
        decision = context["decision"]
        request = context["correction_request"]
        correction_case = context["correction_case"]

        # Test-only reconstruction of the pre-commit state. This is not a
        # production cancellation, reopening, or authority-handoff service.
        FactualCorrectionRequest.objects.filter(pk=request.pk).update(
            status=FactualCorrectionRequest.Status.ACTIVE
        )
        ModerationCase.objects.filter(pk=correction_case.pk).update(
            status=ModerationCase.Status.OPEN,
            resolved_at=None,
        )
        request.refresh_from_db()
        correction_case.refresh_from_db()

        values = {
            "fact_check": corrected,
            "decision_snapshot": context["decision_snapshot"],
            "schema_version": FACTUAL_CORRECTION_SCHEMA_VERSION,
            "predecessor_snapshot": corrected.supersedes.publication_snapshot,
            "correction_request": request,
            "prepared_proposal": context["prepared_proposal"],
        }

        for invalid_actor in (self.moderator, None):
            with self.subTest(invalid_actor=invalid_actor):
                AdjudicationDecision.objects.filter(pk=decision.pk).update(
                    decided_by=invalid_actor
                )
                decision.refresh_from_db()
                with self.assertRaises(ValidationError):
                    OfficialFactCheckPublicationSnapshot.build_payload(**values)

        AdjudicationDecision.objects.filter(pk=decision.pk).update(
            decided_by=self.lead
        )
        decision.refresh_from_db()
        self.assertEqual(
            OfficialFactCheckPublicationSnapshot.build_payload(**values),
            corrected.publication_snapshot.payload,
        )

        for invalid_status in (
            ModerationCase.Status.RESOLVED,
            ModerationCase.Status.CANCELLED,
        ):
            with self.subTest(invalid_status=invalid_status):
                ModerationCase.objects.filter(pk=correction_case.pk).update(
                    status=invalid_status
                )
                correction_case.refresh_from_db()
                with self.assertRaises(ValidationError):
                    OfficialFactCheckPublicationSnapshot.build_payload(**values)


class MixedDecisionPublicationHistoryTests(
    FactualCorrectionPublicationHistoryFixtures,
    TestCase,
):
    def test_editorial_v2_can_surround_a_valid_factual_correction_v3(self):
        context = self.make_prepared_context(
            suffix="mixed-chain",
            editorial_first=True,
        )
        corrected = self.finalize_prepared_correction(context)
        self.assertEqual(self.validate_history(context), corrected.publication_snapshot)

        editorial = self.make_submitted_revision(context)
        self.replace(context, editorial)
        context["published"] = editorial
        context["seal"] = editorial.publication_snapshot
        self.assertEqual(self.validate_history(context), editorial.publication_snapshot)

    def test_repeated_factual_corrections_form_one_verifiable_history(self):
        context = self.make_prepared_context(suffix="repeated-first")
        first = self.finalize_prepared_correction(context)

        reservation = self.request_correction(context)
        context.update(
            correction_request=reservation["request"],
            correction_case=reservation["case"],
        )
        context["correction_review"] = self.review_correction(context)
        proposal = self.save_proposal(context)
        context["prepared_proposal"] = self.prepare_proposal(
            context,
            proposal,
        )["proposal"]
        second = self.finalize_prepared_correction(context)

        self.assertEqual(second.adjudication_decision.revision_number, 3)
        self.assertEqual(second.supersedes, first)
        self.assertEqual(self.validate_history(context), second.publication_snapshot)

    def test_history_rejects_wrong_predecessor_snapshot_article_seal_or_proposal(self):
        mutations = (
            ("predecessor decision", "predecessor_decision_id", str(uuid.uuid4())),
            (
                "predecessor snapshot",
                "predecessor_decision_evidence_snapshot_id",
                str(uuid.uuid4()),
            ),
            (
                "predecessor fact-check",
                "predecessor_fact_check_id",
                str(uuid.uuid4()),
            ),
            ("predecessor article", "predecessor_fact_check_version", 99),
            (
                "predecessor seal",
                "predecessor_publication_snapshot_id",
                str(uuid.uuid4()),
            ),
            ("prepared proposal", "prepared_proposal_id", str(uuid.uuid4())),
        )
        for suffix, field, value in mutations:
            with self.subTest(field=field):
                context = self.make_prepared_context(suffix=f"wrong-{suffix}")
                corrected = self.finalize_prepared_correction(context)
                payload = deepcopy(corrected.publication_snapshot.payload)
                payload["correction"][field] = value
                OfficialFactCheckPublicationSnapshot.objects.filter(
                    pk=corrected.publication_snapshot.pk
                ).update(payload=payload)
                with self.assertRaises(PublishingConflict):
                    self.validate_history(context)

    def test_history_rejects_missing_or_malformed_prepared_proposal_provenance(self):
        context = self.make_prepared_context(suffix="malformed-proposal")
        self.finalize_prepared_correction(context)
        malformed = deepcopy(context["prepared_proposal"].prepared_payload)
        malformed["approval"]["unexpected"] = True
        FactualCorrectionProposal.objects.filter(
            pk=context["prepared_proposal"].pk
        ).update(prepared_payload=malformed)
        with self.assertRaises(PublishingConflict):
            self.validate_history(context)

    def test_history_rejects_article_state_that_no_longer_matches_its_seal(self):
        context = self.make_prepared_context(suffix="article-state")
        corrected = self.finalize_prepared_correction(context)
        OfficialFactCheck.objects.filter(pk=corrected.supersedes_id).update(
            headline="A fabricated predecessor headline"
        )
        with self.assertRaises(PublishingConflict):
            self.validate_history(context)

    def test_history_rejects_fabricated_or_cross_tenant_decision_transition(self):
        context = self.make_prepared_context(suffix="fabricated-transition")
        corrected = self.finalize_prepared_correction(context)
        AdjudicationDecision.objects.filter(pk=context["decision"].pk).update(
            supersedes=None
        )
        with self.assertRaises(PublishingConflict):
            self.validate_history(context)

        cross_claim = self.make_prepared_context(suffix="cross-claim")
        cross_claim_successor = self.finalize_prepared_correction(cross_claim)
        other_claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="A different claim must not enter this history.",
        )
        AdjudicationDecision.objects.filter(pk=cross_claim["decision"].pk).update(
            claim=other_claim
        )
        with self.assertRaises(PublishingConflict):
            self.validate_history(cross_claim)
        self.assertIsNotNone(cross_claim_successor.pk)

        AdjudicationDecision.objects.filter(pk=context["decision"].pk).update(
            supersedes=corrected.supersedes.adjudication_decision
        )
        OfficialFactCheck.objects.filter(pk=corrected.pk).update(
            organization=self.other_organization
        )
        with self.assertRaises(PublishingConflict):
            self.validate_history(context)

    def test_history_rejects_wrong_source_lineage_decision_snapshot(self):
        context = self.make_prepared_context(suffix="wrong-lineage")
        corrected = self.finalize_prepared_correction(context)
        payload = deepcopy(corrected.publication_snapshot.payload)
        source = next(item for item in payload["sources"] if item["lineage"])
        source["lineage"][0]["decision_evidence_snapshot_id"] = str(uuid.uuid4())
        OfficialFactCheckPublicationSnapshot.objects.filter(
            pk=corrected.publication_snapshot.pk
        ).update(payload=payload)
        with self.assertRaises(PublishingConflict):
            self.validate_history(context)

    def test_legacy_null_root_and_deleted_historical_approver_remain_verifiable(self):
        context = self.make_prepared_context(suffix="stable-approver")
        OfficialFactCheck.objects.filter(pk=context["published"].pk).update(
            revision_kind=None
        )
        corrected = self.finalize_prepared_correction(context)
        approver_snapshot = deepcopy(
            corrected.publication_snapshot.payload["correction"]["approved_by"]
        )
        approver_id = self.lead.id
        User.objects.filter(pk=approver_id).delete()
        corrected.refresh_from_db()
        context["decision"].refresh_from_db()
        self.assertIsNone(context["decision"].decided_by_id)
        self.assertEqual(
            corrected.publication_snapshot.payload["correction"]["approved_by"],
            approver_snapshot,
        )
        self.assertEqual(self.validate_history(context), corrected.publication_snapshot)


    def test_published_correction_requires_completed_request_and_resolved_case(self):
        context = self.make_prepared_context(suffix="completed-history")
        corrected = self.finalize_prepared_correction(context)
        request = context["correction_request"]
        correction_case = context["correction_case"]
        resolved_at = correction_case.resolved_at

        FactualCorrectionRequest.objects.filter(pk=request.pk).update(
            status=FactualCorrectionRequest.Status.ACTIVE
        )
        with self.assertRaises(PublishingConflict):
            self.validate_history(context)

        FactualCorrectionRequest.objects.filter(pk=request.pk).update(
            status=FactualCorrectionRequest.Status.COMPLETED
        )
        for invalid_status in (
            ModerationCase.Status.OPEN,
            ModerationCase.Status.CANCELLED,
        ):
            with self.subTest(invalid_status=invalid_status):
                ModerationCase.objects.filter(pk=correction_case.pk).update(
                    status=invalid_status
                )
                with self.assertRaises(PublishingConflict):
                    self.validate_history(context)

        ModerationCase.objects.filter(pk=correction_case.pk).update(
            status=ModerationCase.Status.RESOLVED,
            resolved_at=None,
        )
        with self.assertRaises(PublishingConflict):
            self.validate_history(context)

        ModerationCase.objects.filter(pk=correction_case.pk).update(
            resolved_at=resolved_at
        )
        self.assertEqual(self.validate_history(context), corrected.publication_snapshot)

    def test_stale_tip_is_rejected_and_never_published_draft_is_excluded(self):
        context = self.make_prepared_context(suffix="tip")
        corrected = self.finalize_prepared_correction(context)
        abandoned = OfficialFactCheck.objects.create(
            claim=context["claim"],
            adjudication_decision=context["decision"],
            organization=self.organization,
            canonical_claim=context["decision"].canonical_claim,
            verdict=context["decision"].verdict,
            headline="Abandoned correction-era draft",
            summary="Never published.",
            article_body="Not part of durable history.",
            publication_status=OfficialFactCheck.PublicationStatus.ARCHIVED,
            version=corrected.version + 1,
            supersedes=corrected,
            revision_kind=OfficialFactCheck.RevisionKind.EDITORIAL_REVISION,
            revision_reason="Abandoned editorial work.",
            revision_requested_by=self.lead,
            revision_requested_at=timezone.now(),
        )
        self.assertEqual(self.validate_history(context), corrected.publication_snapshot)
        self.assertIsNotNone(abandoned.pk)
        with self.assertRaises(PublishingConflict):
            self.validate_history(context, predecessor=corrected.supersedes)

    def test_ordinary_publication_cannot_masquerade_as_decision_change(self):
        context = self.make_prepared_context(suffix="ordinary-guard")
        corrected = self.finalize_prepared_correction(context)
        with self.assertRaises(ValidationError):
            OfficialFactCheckPublicationSnapshot.build_payload(
                fact_check=corrected,
                decision_snapshot=context["decision_snapshot"],
                schema_version=FIRST_PUBLICATION_SCHEMA_VERSION,
            )
        with self.assertRaises(ValidationError):
            OfficialFactCheckPublicationSnapshot.build_payload(
                fact_check=corrected,
                decision_snapshot=context["decision_snapshot"],
                schema_version=EDITORIAL_REVISION_SCHEMA_VERSION,
            )
