from copy import deepcopy

from django.contrib.auth.models import User
from django.test import TestCase

from api.factual_correction_service import (
    FactualCorrectionAuthorizationError,
    FactualCorrectionConflict,
    cancel_factual_correction_for_partner_retirement,
)
from api.management_governance_service import MANAGE_PARTNER_ORGANIZATION
from api.models import (
    AccountabilityEvent,
    AdjudicationDecision,
    FactualCorrectionRequest,
    ModerationCase,
    ModerationEvent,
    OfficialFactCheck,
    OfficialFactCheckPublicationSnapshot,
)
from api.tests.workspace.test_factual_correction_proposal import (
    FactualCorrectionProposalFixtures,
)


class PlatformFactualCorrectionRetirementCancellationTests(
    FactualCorrectionProposalFixtures,
    TestCase,
):
    def setUp(self):
        super().setUp()
        self.platform_admin = User.objects.create_superuser(
            username="retirement-platform-admin",
            email="retirement-platform-admin@example.com",
            password="test-password",
        )

    def correction_context(self, *, suffix, prepared=False):
        context = self.make_proposal_context(
            suffix=suffix,
            review=prepared,
        )
        context["proposal"] = self.save_proposal(context)
        if prepared:
            self.prepare_proposal(context, context["proposal"])
            context["proposal"].refresh_from_db()
        return context

    def cancel_for_retirement(self, context, **overrides):
        values = {
            "correction_request_id": context["correction_request"].pk,
            "actor": self.platform_admin,
            "organization_id": self.organization.pk,
        }
        values.update(overrides)
        return cancel_factual_correction_for_partner_retirement(**values)

    def test_platform_retirement_cancellation_preserves_published_authority_and_provenance(
        self,
    ):
        context = self.correction_context(
            suffix="platform-retirement-preserves-authority",
            prepared=True,
        )
        decision_snapshot = context["decision"].evidence_snapshot
        original_decision_records = deepcopy(decision_snapshot.evidence_records)
        original_publication_payload = deepcopy(context["seal"].payload)
        decision_count = AdjudicationDecision.objects.filter(
            claim=context["claim"]
        ).count()
        fact_check_count = OfficialFactCheck.objects.filter(
            claim=context["claim"]
        ).count()
        publication_snapshot_count = (
            OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check__claim=context["claim"]
            ).count()
        )

        result = self.cancel_for_retirement(context)

        context["decision"].refresh_from_db()
        context["published"].refresh_from_db()
        context["correction_request"].refresh_from_db()
        context["correction_case"].refresh_from_db()
        decision_snapshot.refresh_from_db()
        context["seal"].refresh_from_db()

        self.assertEqual(
            context["correction_request"].status,
            FactualCorrectionRequest.Status.CANCELLED,
        )
        self.assertEqual(
            context["correction_case"].status,
            ModerationCase.Status.CANCELLED,
        )
        self.assertTrue(context["decision"].is_current)
        self.assertEqual(
            context["published"].publication_status,
            OfficialFactCheck.PublicationStatus.PUBLISHED,
        )
        self.assertEqual(decision_snapshot.evidence_records, original_decision_records)
        self.assertEqual(context["seal"].payload, original_publication_payload)
        self.assertEqual(
            AdjudicationDecision.objects.filter(claim=context["claim"]).count(),
            decision_count,
        )
        self.assertEqual(
            OfficialFactCheck.objects.filter(claim=context["claim"]).count(),
            fact_check_count,
        )
        self.assertEqual(
            OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check__claim=context["claim"]
            ).count(),
            publication_snapshot_count,
        )
        self.assertEqual(result["proposal"].pk, context["proposal"].pk)

        moderation_event = ModerationEvent.objects.get(
            case=context["correction_case"],
            event_type=ModerationEvent.EventType.CASE_CANCELLED,
        )
        self.assertEqual(moderation_event.actor, self.platform_admin)
        self.assertEqual(moderation_event.reason_code, "PARTNERSHIP_ENDED")
        self.assertIn("Partner Organization", moderation_event.notes)
        self.assertEqual(
            moderation_event.metadata["predecessor_fact_check_id"],
            str(context["published"].pk),
        )

        accountability_event = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.FACTUAL_CORRECTION_CANCELLED,
            resource_id=str(context["correction_request"].pk),
        )
        self.assertEqual(
            accountability_event.authority_scope,
            AccountabilityEvent.AuthorityScope.PLATFORM,
        )
        self.assertIsNone(accountability_event.authority_organization)
        self.assertEqual(accountability_event.subject_organization, self.organization)
        self.assertEqual(
            accountability_event.capability,
            MANAGE_PARTNER_ORGANIZATION,
        )
        self.assertEqual(accountability_event.reason_code, "PARTNERSHIP_ENDED")
        self.assertTrue(accountability_event.context["platform_governance"])

    def test_platform_retirement_cancellation_works_without_a_proposal(self):
        context = self.make_proposal_context(
            suffix="platform-retirement-no-proposal",
        )

        result = self.cancel_for_retirement(context)

        self.assertIsNone(result["proposal"])
        result["request"].refresh_from_db()
        result["case"].refresh_from_db()
        self.assertEqual(
            result["request"].status,
            FactualCorrectionRequest.Status.CANCELLED,
        )
        self.assertEqual(result["case"].status, ModerationCase.Status.CANCELLED)

    def test_non_platform_actor_cannot_use_retirement_cancellation(self):
        context = self.correction_context(
            suffix="platform-retirement-denied",
        )

        with self.assertRaises(FactualCorrectionAuthorizationError):
            self.cancel_for_retirement(
                context,
                actor=self.lead,
            )

        context["correction_request"].refresh_from_db()
        self.assertEqual(
            context["correction_request"].status,
            FactualCorrectionRequest.Status.ACTIVE,
        )

    def test_wrong_organization_or_terminal_request_fails_closed(self):
        wrong_organization = self.other_organization
        wrong = self.correction_context(
            suffix="platform-retirement-wrong-organization",
        )
        with self.assertRaises(FactualCorrectionConflict):
            self.cancel_for_retirement(
                wrong,
                organization_id=wrong_organization.pk,
            )

        terminal = self.correction_context(
            suffix="platform-retirement-terminal",
        )
        self.cancel_for_retirement(terminal)

        with self.assertRaises(FactualCorrectionConflict):
            self.cancel_for_retirement(terminal)
