from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from api.factual_correction_service import request_factual_correction
from api.models import (
    AccountabilityEvent,
    AdjudicationDecision,
    Claim,
    FactualCorrectionProposal,
    FactualCorrectionRequest,
    KnowledgeReuseEvent,
    OfficialFactCheck,
    OrganizationMembership,
    PublicReachEvent,
    VerificationAssignment,
)
from api.tests.workspace.test_publication_workflow_api import (
    PublicationWorkflowFixtures,
)
from api.verification_current_state_metrics_service import (
    get_organization_verification_current_state,
)


class VerificationCurrentStateMetricsTests(PublicationWorkflowFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.other_actor = User.objects.create_user(username="current-state-other")
        OrganizationMembership.objects.create(
            organization=self.other_organization,
            user=self.other_actor,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )

    def project(self, organization=None):
        return get_organization_verification_current_state(
            organization=organization or self.organization
        )

    def make_decision(self, *, organization=None, suffix="state"):
        organization = organization or self.organization
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=f"Current state claim {suffix}.",
        )
        decision = AdjudicationDecision.objects.create(
            claim=claim,
            verdict=AdjudicationDecision.Verdict.FACT,
            canonical_claim=f"Canonical current state claim {suffix}.",
            rationale="Persisted human decision for aggregate-state testing.",
            decided_by=(
                self.lead
                if organization == self.organization
                else self.other_actor
            ),
            organization=organization,
        )
        return claim, decision

    def make_fact_check(
        self,
        *,
        status,
        suffix,
        organization=None,
        claim=None,
        decision=None,
        revision_kind=OfficialFactCheck.RevisionKind.INITIAL,
        supersedes=None,
        version=1,
    ):
        organization = organization or self.organization
        if claim is None or decision is None:
            claim, decision = self.make_decision(
                organization=organization,
                suffix=suffix,
            )
        workflow_actor = (
            self.lead
            if organization == self.organization
            else self.other_actor
        )
        is_revision = revision_kind in {
            OfficialFactCheck.RevisionKind.EDITORIAL_REVISION,
            OfficialFactCheck.RevisionKind.FACTUAL_CORRECTION,
        }
        return OfficialFactCheck.objects.create(
            claim=claim,
            adjudication_decision=decision,
            organization=organization,
            canonical_claim=decision.canonical_claim,
            verdict=decision.verdict,
            headline=f"Current state headline {suffix}",
            summary=f"Current state summary {suffix}.",
            article_body=f"Private current state article {suffix}.",
            publication_status=status,
            version=version,
            drafted_by=workflow_actor,
            supersedes=supersedes,
            revision_kind=revision_kind,
            revision_reason=(
                "Clarify the current publication."
                if is_revision else None
            ),
            revision_requested_by=(
                workflow_actor if is_revision else None
            ),
            revision_requested_at=(
                decision.decided_at if is_revision else None
            ),
        )

    def make_published_workflow(self, *, suffix):
        context = self.decided_context(suffix=suffix)
        draft = self.create_draft(context, suffix=suffix)
        context["published"] = self.publish(context, self.submit(context, draft))
        return context

    def make_active_correction(self, *, suffix):
        context = self.make_published_workflow(suffix=suffix)
        result = request_factual_correction(
            predecessor_id=context["published"].id,
            actor=self.lead,
            organization_id=self.organization.id,
            expected_predecessor_version=context["published"].version,
            expected_decision_revision=context["decision"].revision_number,
            correction_reason=f"Correct a material fact for {suffix}.",
        )
        context["correction_request"] = result["request"]
        return context

    def test_empty_organization_returns_exact_zero_schema(self):
        self.assertEqual(
            self.project(),
            {
                "organization_id": str(self.organization.pk),
                "measurement_basis": {
                    "source": "PERSISTED_OPERATIONAL_RECORDS",
                    "coverage": "CURRENT_STATE",
                },
                "published_fact_checks": {"distinct_claims": 0},
                "factual_corrections": {"active_requests": 0},
                "investigations": {"active_assignments": 0},
                "publication_work": {"distinct_claims": 0},
            },
        )

    def test_published_count_is_current_distinct_claim_state(self):
        first = self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            suffix="published-first",
        )
        second = self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            suffix="published-second",
        )
        predecessor = self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.ARCHIVED,
            suffix="published-predecessor",
        )
        self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            suffix="published-successor",
            claim=predecessor.claim,
            decision=predecessor.adjudication_decision,
            revision_kind=OfficialFactCheck.RevisionKind.EDITORIAL_REVISION,
            supersedes=predecessor,
            version=2,
        )
        self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.DRAFT,
            suffix="published-draft",
        )
        self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.IN_REVIEW,
            suffix="published-review",
        )
        missing_claim = OfficialFactCheck.objects.create(
            claim=None,
            adjudication_decision=first.adjudication_decision,
            organization=self.organization,
            canonical_claim="Missing claim identity.",
            verdict=AdjudicationDecision.Verdict.FACT,
            summary="Must not count without a claim.",
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            version=50,
        )
        missing_decision_claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Missing adjudication decision.",
        )
        missing_decision = OfficialFactCheck.objects.create(
            claim=missing_decision_claim,
            adjudication_decision=None,
            organization=self.organization,
            canonical_claim="Missing decision authority.",
            verdict=AdjudicationDecision.Verdict.FACT,
            summary="Must not count without a decision.",
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            version=1,
        )

        result = self.project()

        self.assertEqual(result["published_fact_checks"], {"distinct_claims": 3})
        self.assertNotIn(str(first.id), str(result))
        self.assertNotIn(str(second.id), str(result))
        self.assertNotIn(str(missing_claim.id), str(result))
        self.assertNotIn(str(missing_decision.id), str(result))

    def test_published_predecessor_remains_counted_during_active_correction(self):
        context = self.make_active_correction(suffix="published-during-correction")

        result = self.project()

        self.assertEqual(result["published_fact_checks"], {"distinct_claims": 1})
        self.assertEqual(result["factual_corrections"], {"active_requests": 1})
        context["published"].refresh_from_db()
        self.assertEqual(
            context["published"].publication_status,
            OfficialFactCheck.PublicationStatus.PUBLISHED,
        )

    def test_only_active_factual_correction_requests_are_counted(self):
        active = self.make_active_correction(suffix="correction-active")
        completed = self.make_active_correction(suffix="correction-completed")
        cancelled = self.make_active_correction(suffix="correction-cancelled")
        FactualCorrectionRequest.objects.filter(
            pk=completed["correction_request"].pk
        ).update(status=FactualCorrectionRequest.Status.COMPLETED)
        FactualCorrectionRequest.objects.filter(
            pk=cancelled["correction_request"].pk
        ).update(status=FactualCorrectionRequest.Status.CANCELLED)

        result = self.project()

        self.assertEqual(result["factual_corrections"], {"active_requests": 1})
        self.assertEqual(
            active["correction_request"].organization_id,
            self.organization.id,
        )

    def test_only_active_organization_assignments_are_counted(self):
        for status in VerificationAssignment.Status.values:
            claim = Claim.objects.create(
                claim_type=Claim.ClaimType.TEXT,
                context_text=f"Assignment state {status}.",
            )
            VerificationAssignment.objects.create(
                claim=claim,
                organization=(
                    self.organization
                    if status != VerificationAssignment.Status.AVAILABLE
                    else None
                ),
                claimed_by=(
                    self.lead
                    if status != VerificationAssignment.Status.AVAILABLE
                    else None
                ),
                status=status,
            )
        other_claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Other organization active assignment.",
        )
        VerificationAssignment.objects.create(
            claim=other_claim,
            organization=self.other_organization,
            claimed_by=self.other_actor,
            status=VerificationAssignment.Status.ACTIVE,
        )

        self.assertEqual(
            self.project()["investigations"],
            {"active_assignments": 1},
        )

    def test_open_publication_work_supports_initial_editorial_and_legacy_rows(self):
        self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.DRAFT,
            suffix="open-initial-draft",
        )
        self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.IN_REVIEW,
            suffix="open-initial-review",
        )
        predecessor = self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            suffix="open-editorial-predecessor",
        )
        self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.DRAFT,
            suffix="open-editorial-draft",
            claim=predecessor.claim,
            decision=predecessor.adjudication_decision,
            revision_kind=OfficialFactCheck.RevisionKind.EDITORIAL_REVISION,
            supersedes=predecessor,
            version=2,
        )
        self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.DRAFT,
            suffix="open-legacy-initial",
            revision_kind=None,
        )
        self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.ARCHIVED,
            suffix="open-archived",
        )
        self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            suffix="open-published",
        )

        self.assertEqual(
            self.project()["publication_work"],
            {"distinct_claims": 4},
        )

    def test_open_publication_work_deduplicates_claims_and_excludes_other_workflows(self):
        claim, decision = self.make_decision(suffix="open-deduplicated")
        self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.DRAFT,
            suffix="open-deduplicated-one",
            claim=claim,
            decision=decision,
            version=1,
        )
        self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.IN_REVIEW,
            suffix="open-deduplicated-two",
            claim=claim,
            decision=decision,
            version=2,
        )
        correction_predecessor = self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            suffix="open-factual-correction-predecessor",
        )
        self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.DRAFT,
            suffix="open-factual-correction-row",
            claim=correction_predecessor.claim,
            decision=correction_predecessor.adjudication_decision,
            revision_kind=OfficialFactCheck.RevisionKind.FACTUAL_CORRECTION,
            supersedes=correction_predecessor,
            version=2,
        )
        other_work = self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.DRAFT,
            suffix="open-other-organization",
            organization=self.other_organization,
        )

        result = self.project()

        self.assertEqual(result["publication_work"], {"distinct_claims": 1})
        self.assertNotIn(str(other_work.id), str(result))

    def test_factual_correction_proposal_is_not_open_publication_work(self):
        context = self.make_active_correction(suffix="proposal-not-publication-work")
        proposal = FactualCorrectionProposal.objects.create(
            correction_request=context["correction_request"],
            status=FactualCorrectionProposal.Status.DRAFT,
            verdict=context["decision"].verdict,
            canonical_claim=context["decision"].canonical_claim,
            rationale="Proposed corrected rationale.",
            headline="Proposed corrected headline",
            summary="Proposed corrected summary.",
            article_body="Private proposed corrected article body.",
            source_urls=["https://example.com/correction-source"],
        )

        result = self.project()

        self.assertEqual(result["factual_corrections"], {"active_requests": 1})
        self.assertEqual(result["publication_work"], {"distinct_claims": 0})
        self.assertNotIn(str(proposal.id), str(result))
        self.assertNotIn(proposal.article_body, str(result))

    def test_categories_overlap_without_a_combined_total(self):
        correction = self.make_active_correction(suffix="overlap-correction")
        predecessor = self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            suffix="overlap-editorial",
        )
        self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.DRAFT,
            suffix="overlap-editorial-draft",
            claim=predecessor.claim,
            decision=predecessor.adjudication_decision,
            revision_kind=OfficialFactCheck.RevisionKind.EDITORIAL_REVISION,
            supersedes=predecessor,
            version=2,
        )

        result = self.project()

        self.assertEqual(result["published_fact_checks"], {"distinct_claims": 2})
        self.assertEqual(result["factual_corrections"], {"active_requests": 1})
        self.assertEqual(result["publication_work"], {"distinct_claims": 1})
        self.assertNotIn("total", result)
        self.assertEqual(
            correction["published"].claim_id,
            correction["correction_request"].claim_id,
        )

    def test_organization_scope_and_aggregate_only_schema(self):
        local = self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            suffix="scope-local",
        )
        foreign = self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            suffix="scope-foreign",
            organization=self.other_organization,
        )

        result = self.project()

        self.assertEqual(set(result), {
            "organization_id",
            "measurement_basis",
            "published_fact_checks",
            "factual_corrections",
            "investigations",
            "publication_work",
        })
        self.assertEqual(result["published_fact_checks"], {"distinct_claims": 1})
        serialized = str(result)
        for private_value in (
            local.id,
            local.claim_id,
            local.headline,
            local.article_body,
            foreign.id,
            foreign.claim_id,
            self.lead.username,
        ):
            self.assertNotIn(str(private_value), serialized)

    def test_repeated_reads_are_deterministic_and_create_no_writes(self):
        self.make_fact_check(
            status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            suffix="read-only-published",
        )
        tracked_models = (
            AccountabilityEvent,
            KnowledgeReuseEvent,
            PublicReachEvent,
            VerificationAssignment,
            OfficialFactCheck,
            FactualCorrectionRequest,
        )
        before = {model: model.objects.count() for model in tracked_models}

        with CaptureQueriesContext(connection) as queries:
            first = self.project()
            second = self.project()

        self.assertEqual(first, second)
        self.assertTrue(queries.captured_queries)
        for query in queries.captured_queries:
            sql = query["sql"].lstrip().upper()
            self.assertFalse(sql.startswith(("INSERT", "UPDATE", "DELETE")))
        self.assertEqual(
            {model: model.objects.count() for model in tracked_models},
            before,
        )
