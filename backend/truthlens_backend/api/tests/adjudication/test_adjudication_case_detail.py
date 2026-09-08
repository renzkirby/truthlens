from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from api.adjudication_provenance import AdjudicationProvenance
from api.models import (
    AdjudicationDecision,
    Claim,
    EvidenceSubmission,
    ModerationCase,
    ModerationEvent,
    Organization,
    OrganizationMembership,
    Thread,
    VerificationAssignment,
)


class AdjudicationCaseDetailApiTests(APITestCase):
    def setUp(self):
        self.lead = self._create_user("detail-lead")
        self.partner_moderator = self._create_user("detail-moderator")
        self.owner = self._create_user("detail-owner")
        self.ordinary_user = self._create_user("detail-ordinary")
        self.author = self._create_user("detail-author")
        self.contributor = self._create_user("detail-contributor")
        self.reviewer = self._create_user("detail-evidence-reviewer")

        self.organization = self._create_organization("primary")
        self.other_organization = self._create_organization("other")
        self._add_member(
            self.lead,
            self.organization,
            OrganizationMembership.Role.LEAD_VERIFIER,
        )
        self._add_member(
            self.partner_moderator,
            self.organization,
            OrganizationMembership.Role.MODERATOR,
        )
        self._add_member(
            self.owner,
            self.organization,
            OrganizationMembership.Role.OWNER,
        )

        self.context = self._create_context()

    @staticmethod
    def _create_user(username):
        return User.objects.create_user(
            username=username,
            password="test-password",
        )

    @staticmethod
    def _create_organization(suffix):
        return Organization.objects.create(
            name=f"Adjudication Detail Partner {suffix}",
            slug=f"adjudication-detail-partner-{suffix}",
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )

    @staticmethod
    def _add_member(user, organization, role, *, membership_status=None):
        return OrganizationMembership.objects.create(
            organization=organization,
            user=user,
            role=role,
            status=membership_status or OrganizationMembership.Status.ACTIVE,
        )

    def _create_context(
        self,
        *,
        organization=None,
        case_status=ModerationCase.Status.OPEN,
        evidence_statuses=(EvidenceSubmission.EvidenceStatus.VERIFIED,),
        assigned=True,
        author=None,
        contributor=None,
    ):
        organization = organization or self.organization
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.URL,
            context_text="A claim awaiting an accountable human decision.",
            url_link="https://example.com/original-claim",
            source_link="https://example.com/source",
            media_url="https://example.com/media.jpg",
            ai_verdict="FAKE",
            ai_summary="Private automated analysis.",
            consensus_score=96.0,
        )
        thread = Thread.objects.create(
            claim=claim,
            author=author or self.author,
            caption="Community thread context for the claim.",
        )
        evidence = []
        for index, evidence_status in enumerate(evidence_statuses):
            evidence.append(
                EvidenceSubmission.objects.create(
                    thread=thread,
                    contributor=contributor or self.contributor,
                    evidence_caption=f"Operational evidence {index}.",
                    evidence_url=f"https://example.com/evidence-{index}",
                    evidence_type=(
                        EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION
                    ),
                    evidence_status=evidence_status,
                    verified_by=(
                        self.reviewer
                        if evidence_status
                        != EvidenceSubmission.EvidenceStatus.UNVERIFIED
                        else None
                    ),
                    verified_at=(
                        timezone.now()
                        if evidence_status
                        != EvidenceSubmission.EvidenceStatus.UNVERIFIED
                        else None
                    ),
                    moderator_notes=(
                        "Evidence review notes."
                        if evidence_status
                        != EvidenceSubmission.EvidenceStatus.UNVERIFIED
                        else None
                    ),
                    rejection_reason=(
                        EvidenceSubmission.RejectionReason.IRRELEVANT
                        if evidence_status
                        == EvidenceSubmission.EvidenceStatus.REJECTED
                        else None
                    ),
                    contributor_trust_snapshot=99.0,
                )
            )
        assignment = None
        if assigned:
            assignment = VerificationAssignment.objects.create(
                claim=claim,
                organization=organization,
                claimed_by=self.lead,
                status=VerificationAssignment.Status.ACTIVE,
            )
        case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.ADJUDICATION,
            claim=claim,
            organization=organization,
            status=case_status,
            priority=ModerationCase.Priority.HIGH,
            source=ModerationCase.Source.COMMUNITY_ESCALATION,
        )
        return {
            "claim": claim,
            "thread": thread,
            "evidence": evidence,
            "assignment": assignment,
            "case": case,
        }

    def _detail_url(self, context=None, organization=None, suffix=""):
        context = context or self.context
        organization = organization or self.organization
        return (
            reverse(
                "adjudication_case_detail",
                kwargs={"case_id": context["case"].id},
            )
            + f"?organization_id={organization.id}{suffix}"
        )

    def _authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.lead)

    @staticmethod
    def _all_mapping_keys(value):
        keys = set()
        if isinstance(value, dict):
            keys.update(value)
            for nested in value.values():
                keys.update(
                    AdjudicationCaseDetailApiTests._all_mapping_keys(nested)
                )
        elif isinstance(value, list):
            for nested in value:
                keys.update(
                    AdjudicationCaseDetailApiTests._all_mapping_keys(nested)
                )
        return keys

    def _create_decision(
        self,
        context,
        *,
        organization=None,
        moderation_case=None,
        verdict=AdjudicationDecision.Verdict.FACT,
        revision_number=1,
        is_current=True,
        source=AdjudicationDecision.DecisionSource.HUMAN_REVIEW,
        decided_by=None,
        supersedes=None,
        canonical_claim="Historical canonical wording.",
        rationale="Historical human rationale.",
    ):
        return AdjudicationDecision.objects.create(
            claim=context["claim"],
            moderation_case=moderation_case,
            verdict=verdict,
            canonical_claim=canonical_claim,
            rationale=rationale,
            decided_by=decided_by or self.lead,
            organization=(
                organization
                if organization is not None
                else self.organization
            ),
            decision_source=source,
            revision_number=revision_number,
            is_current=is_current,
            supersedes=supersedes,
        )

    def test_authorization_strict_query_and_case_identity_are_scoped(self):
        self.assertEqual(
            self.client.get(self._detail_url()).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

        denied_partner_users = [self.owner]
        for index, role in enumerate(
            (
                OrganizationMembership.Role.ADMIN,
                OrganizationMembership.Role.RESEARCHER,
                OrganizationMembership.Role.CONTRIBUTOR,
            )
        ):
            denied_user = self._create_user(f"detail-denied-role-{index}")
            self._add_member(denied_user, self.organization, role)
            denied_partner_users.append(denied_user)

        for denied_user in (self.ordinary_user, *denied_partner_users):
            self._authenticate(denied_user)
            with self.subTest(user=denied_user.username):
                self.assertEqual(
                    self.client.get(self._detail_url()).status_code,
                    status.HTTP_403_FORBIDDEN,
                )

        other_lead = self._create_user("detail-other-lead")
        self._add_member(
            other_lead,
            self.other_organization,
            OrganizationMembership.Role.LEAD_VERIFIER,
        )
        self._authenticate(other_lead)
        self.assertEqual(
            self.client.get(self._detail_url()).status_code,
            status.HTTP_403_FORBIDDEN,
        )

        for allowed_user in (self.lead, self.partner_moderator):
            self._authenticate(allowed_user)
            with self.subTest(user=allowed_user.username):
                self.assertEqual(
                    self.client.get(self._detail_url()).status_code,
                    status.HTTP_200_OK,
                )

        self._authenticate()
        unknown_organization_url = self._detail_url().replace(
            str(self.organization.id),
            "00000000-0000-0000-0000-000000000001",
        )
        self.assertEqual(
            self.client.get(unknown_organization_url).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.get(self._detail_url(suffix="&extra=true")).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        missing_query_url = reverse(
            "adjudication_case_detail",
            kwargs={"case_id": self.context["case"].id},
        )
        self.assertEqual(
            self.client.get(missing_query_url).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        duplicate = self._detail_url(
            suffix=f"&organization_id={self.organization.id}"
        )
        self.assertEqual(
            self.client.get(duplicate).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        other_context = self._create_context(
            organization=self.other_organization,
        )
        cross_organization_url = self._detail_url(other_context)
        unknown_case_url = (
            reverse(
                "adjudication_case_detail",
                kwargs={
                    "case_id": "00000000-0000-0000-0000-000000000002"
                },
            )
            + f"?organization_id={self.organization.id}"
        )
        safety_case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.SAFETY,
            thread=self.context["thread"],
            organization=self.organization,
        )
        wrong_type_url = (
            reverse(
                "adjudication_case_detail",
                kwargs={"case_id": safety_case.id},
            )
            + f"?organization_id={self.organization.id}"
        )
        not_found_responses = [
            self.client.get(url)
            for url in (
                cross_organization_url,
                unknown_case_url,
                wrong_type_url,
            )
        ]
        self.assertTrue(
            all(
                response.status_code == status.HTTP_404_NOT_FOUND
                for response in not_found_responses
            )
        )
        self.assertEqual(
            {response.data["detail"] for response in not_found_responses},
            {"Adjudication case not found."},
        )

    def test_inactive_membership_and_ineligible_organization_are_denied(self):
        for index, membership_status in enumerate(
            (
                OrganizationMembership.Status.SUSPENDED,
                OrganizationMembership.Status.LEFT,
            )
        ):
            inactive_lead = self._create_user(f"detail-inactive-lead-{index}")
            self._add_member(
                inactive_lead,
                self.organization,
                OrganizationMembership.Role.LEAD_VERIFIER,
                membership_status=membership_status,
            )
            self._authenticate(inactive_lead)
            with self.subTest(membership_status=membership_status):
                self.assertEqual(
                    self.client.get(self._detail_url()).status_code,
                    status.HTTP_403_FORBIDDEN,
                )

        self._authenticate()
        for field, value in (
            (
                "verification_status",
                Organization.VerificationStatus.UNVERIFIED,
            ),
            ("partner_status", Organization.PartnerStatus.SUSPENDED),
        ):
            original = getattr(self.organization, field)
            setattr(self.organization, field, value)
            self.organization.save(update_fields=[field])
            with self.subTest(field=field):
                self.assertEqual(
                    self.client.get(self._detail_url()).status_code,
                    status.HTTP_403_FORBIDDEN,
                )
            setattr(self.organization, field, original)
            self.organization.save(update_fields=[field])

    def test_response_is_minimal_and_uses_current_evidence_records(self):
        context = self._create_context(
            evidence_statuses=(
                EvidenceSubmission.EvidenceStatus.REJECTED,
                EvidenceSubmission.EvidenceStatus.REJECTED,
            )
        )
        self._authenticate()
        response = self.client.get(self._detail_url(context))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data),
            {
                "id",
                "status",
                "status_label",
                "workflow_state",
                "priority",
                "priority_label",
                "source",
                "source_label",
                "created_at",
                "updated_at",
                "resolved_at",
                "organization",
                "claim",
                "evidence_review",
                "assignment",
                "resolution",
                "current_decision",
                "decision_history",
                "events",
                "action_state",
            },
        )
        self.assertEqual(
            set(response.data["claim"]),
            {
                "id",
                "claim_type",
                "context_text",
                "url_link",
                "source_link",
                "media_url",
                "threads",
            },
        )
        review = response.data["evidence_review"]
        self.assertEqual(review["basis"], "CURRENT_EVIDENCE_RECORDS")
        self.assertEqual(
            (review["total"], review["verified"], review["rejected"]),
            (2, 0, 2),
        )
        self.assertEqual(review["unreviewed"], 0)
        self.assertTrue(review["all_reviewed"])
        self.assertTrue(response.data["action_state"]["can_issue_first_decision"])
        evidence_item = review["items"][0]
        self.assertEqual(evidence_item["reviewed_by"]["id"], self.reviewer.id)
        self.assertEqual(evidence_item["rejection_reason"], "IRRELEVANT")
        self.assertFalse(evidence_item["is_current_user_contributor"])

        forbidden = {
            "email",
            "profile",
            "trust_score",
            "contributor_trust_snapshot",
            "ai_verdict",
            "ai_summary",
            "consensus_score",
            "publication_status",
            "metadata",
        }
        self.assertFalse(forbidden & self._all_mapping_keys(response.data))

    def test_action_state_tracks_lifecycle_readiness_assignment_and_conflicts(self):
        lifecycle_expectations = {
            ModerationCase.Status.OPEN: None,
            ModerationCase.Status.IN_REVIEW: None,
            ModerationCase.Status.ESCALATED: None,
            ModerationCase.Status.REOPENED: "CORRECTION_WORKFLOW_REQUIRED",
            ModerationCase.Status.RESOLVED: "CASE_RESOLVED",
            ModerationCase.Status.CANCELLED: "CASE_CANCELLED",
        }
        self._authenticate()
        for case_status, blocker in lifecycle_expectations.items():
            context = self._create_context(case_status=case_status)
            response = self.client.get(self._detail_url(context))
            codes = {
                item["code"] for item in response.data["action_state"]["blockers"]
            }
            with self.subTest(case_status=case_status):
                if blocker is None:
                    self.assertTrue(
                        response.data["action_state"]["can_issue_first_decision"]
                    )
                else:
                    self.assertIn(blocker, codes)
                    self.assertFalse(
                        response.data["action_state"]["can_issue_first_decision"]
                    )

        no_evidence = self._create_context(evidence_statuses=())
        unreviewed = self._create_context(
            evidence_statuses=(EvidenceSubmission.EvidenceStatus.UNVERIFIED,)
        )
        ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=unreviewed["evidence"][0],
            organization=self.organization,
        )
        no_assignment = self._create_context(assigned=False)
        changed_assignment = self._create_context(assigned=False)
        VerificationAssignment.objects.create(
            claim=changed_assignment["claim"],
            organization=self.other_organization,
            claimed_by=self.lead,
            status=VerificationAssignment.Status.ACTIVE,
        )
        direct_conflict = self._create_context(contributor=self.lead)
        direct_author_conflict = self._create_context(author=self.lead)

        expected_codes = (
            (no_evidence, {"NO_EVIDENCE"}),
            (
                unreviewed,
                {"UNREVIEWED_EVIDENCE", "ACTIVE_EVIDENCE_CASE"},
            ),
            (no_assignment, {"NO_ACTIVE_ASSIGNMENT"}),
            (
                changed_assignment,
                {"ASSIGNMENT_ORGANIZATION_CHANGED"},
            ),
            (direct_conflict, {"DIRECT_CONTRIBUTION_CONFLICT"}),
            (direct_author_conflict, {"DIRECT_CONTRIBUTION_CONFLICT"}),
        )
        for context, expected in expected_codes:
            response = self.client.get(self._detail_url(context))
            actual = {
                item["code"] for item in response.data["action_state"]["blockers"]
            }
            self.assertTrue(expected.issubset(actual))

    def test_decision_history_uses_each_records_own_outcome_and_provenance(self):
        context = self.context
        case_a = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.ADJUDICATION,
            claim=context["claim"],
            organization=self.organization,
            status=ModerationCase.Status.RESOLVED,
            resolution_code=AdjudicationDecision.Verdict.FACT,
            resolved_by=self.lead,
            resolved_at=timezone.now() - timedelta(days=2),
        )
        first = self._create_decision(
            context,
            moderation_case=case_a,
            verdict=AdjudicationDecision.Verdict.FACT,
            revision_number=1,
            is_current=False,
            canonical_claim="Case A wording.",
            rationale="Case A rationale.",
        )
        case_b = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.ADJUDICATION,
            claim=context["claim"],
            organization=self.organization,
            status=ModerationCase.Status.RESOLVED,
            resolution_code=AdjudicationDecision.Verdict.FAKE,
            resolved_by=self.partner_moderator,
            resolved_at=timezone.now() - timedelta(days=1),
        )
        second = self._create_decision(
            context,
            moderation_case=case_b,
            verdict=AdjudicationDecision.Verdict.FAKE,
            revision_number=2,
            supersedes=first,
            decided_by=self.partner_moderator,
            canonical_claim="Case B wording.",
            rationale="Case B rationale.",
        )
        context["claim"].final_verdict = AdjudicationDecision.Verdict.FACT
        context["claim"].save(update_fields=["final_verdict"])

        self._authenticate()
        response = self.client.get(self._detail_url())

        current = response.data["current_decision"]
        history = response.data["decision_history"]["results"]
        self.assertEqual(current["id"], str(second.id))
        self.assertEqual(current["verdict"], AdjudicationDecision.Verdict.FAKE)
        self.assertEqual(current["canonical_claim"], "Case B wording.")
        self.assertEqual(
            current["provenance"]["status"],
            AdjudicationProvenance.HUMAN_ADJUDICATION,
        )
        self.assertEqual([item["id"] for item in history], [str(first.id)])
        self.assertEqual(response.data["decision_history"]["count"], 1)
        self.assertFalse(response.data["decision_history"]["truncated"])
        self.assertEqual(history[0]["verdict"], AdjudicationDecision.Verdict.FACT)
        self.assertEqual(history[0]["canonical_claim"], "Case A wording.")
        self.assertEqual(history[0]["supersedes_id"], None)
        self.assertEqual(current["supersedes_id"], str(first.id))
        self.assertEqual(
            response.data["action_state"]["expected_revision"],
            2,
        )
        self.assertIn(
            "CURRENT_DECISION_EXISTS",
            {
                item["code"]
                for item in response.data["action_state"]["blockers"]
            },
        )

    def test_historical_only_decision_state_is_read_only(self):
        historical_case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.ADJUDICATION,
            claim=self.context["claim"],
            organization=self.organization,
            status=ModerationCase.Status.RESOLVED,
            resolution_code=AdjudicationDecision.Verdict.UNVERIFIED,
            resolved_by=self.lead,
            resolved_at=timezone.now(),
        )
        historical = self._create_decision(
            self.context,
            moderation_case=historical_case,
            verdict=AdjudicationDecision.Verdict.UNVERIFIED,
            is_current=False,
        )
        self._authenticate()

        response = self.client.get(self._detail_url())

        self.assertIsNone(response.data["current_decision"])
        self.assertEqual(
            response.data["decision_history"]["results"][0]["id"],
            str(historical.id),
        )
        self.assertEqual(response.data["action_state"]["expected_revision"], 0)
        self.assertIn(
            "HISTORICAL_DECISION_STATE",
            {
                item["code"]
                for item in response.data["action_state"]["blockers"]
            },
        )

    def test_legacy_uncertain_and_restricted_history_do_not_fabricate_attribution(self):
        genuine = self._create_context()
        genuine_decision = self._create_decision(
            genuine,
            source=AdjudicationDecision.DecisionSource.LEGACY_MIGRATION,
        )
        Thread.objects.filter(pk=genuine["thread"].pk).update(
            moderated_by=self.lead,
            moderator_verdict=genuine_decision.verdict,
        )

        uncertain = self._create_context()
        self._create_decision(
            uncertain,
            source=AdjudicationDecision.DecisionSource.LEGACY_MIGRATION,
        )

        missing_canonical = self._create_context()
        self._create_decision(missing_canonical)

        restricted = self._create_context()
        self._create_decision(
            restricted,
            organization=self.other_organization,
        )

        organizationless = self._create_context()
        decision = self._create_decision(
            organizationless,
            source=AdjudicationDecision.DecisionSource.LEGACY_MIGRATION,
        )
        AdjudicationDecision.objects.filter(pk=decision.pk).update(
            organization=None
        )

        self._authenticate()
        genuine_data = self.client.get(self._detail_url(genuine)).data
        uncertain_data = self.client.get(self._detail_url(uncertain)).data
        missing_canonical_data = self.client.get(
            self._detail_url(missing_canonical)
        ).data
        restricted_data = self.client.get(self._detail_url(restricted)).data
        organizationless_data = self.client.get(
            self._detail_url(organizationless)
        ).data

        self.assertEqual(
            genuine_data["current_decision"]["provenance"]["status"],
            AdjudicationProvenance.LEGACY_HUMAN_REVIEW,
        )
        self.assertEqual(
            genuine_data["current_decision"]["decided_by"]["id"],
            self.lead.id,
        )
        self.assertEqual(
            uncertain_data["current_decision"]["provenance"]["status"],
            AdjudicationProvenance.LEGACY_PROVENANCE_UNAVAILABLE,
        )
        self.assertIsNone(uncertain_data["current_decision"]["decided_by"])
        self.assertEqual(
            missing_canonical_data["current_decision"]["provenance"]["status"],
            AdjudicationProvenance.PROVENANCE_UNAVAILABLE,
        )
        self.assertIsNone(
            missing_canonical_data["current_decision"]["decided_by"]
        )

        for data in (restricted_data, organizationless_data):
            self.assertIsNone(data["current_decision"])
            self.assertEqual(data["decision_history"]["results"], [])
            self.assertTrue(
                data["decision_history"]["has_restricted_records"]
            )
            self.assertIn(
                "EXISTING_ADJUDICATION_HISTORY",
                {item["code"] for item in data["action_state"]["blockers"]},
            )

    def test_cache_only_verdict_is_not_a_decision_or_action_blocker(self):
        self.context["claim"].final_verdict = AdjudicationDecision.Verdict.FACT
        self.context["claim"].save(update_fields=["final_verdict"])
        self._authenticate()

        response = self.client.get(self._detail_url())

        self.assertIsNone(response.data["current_decision"])
        self.assertEqual(response.data["decision_history"]["results"], [])
        self.assertFalse(
            response.data["decision_history"]["has_restricted_records"]
        )
        self.assertEqual(
            response.data["action_state"]["expected_revision"],
            0,
        )
        self.assertTrue(response.data["action_state"]["can_issue_first_decision"])

    def test_decision_history_is_bounded_and_stably_ordered(self):
        AdjudicationDecision.objects.bulk_create(
            [
                AdjudicationDecision(
                    claim=self.context["claim"],
                    verdict=AdjudicationDecision.Verdict.UNVERIFIED,
                    canonical_claim=f"Historical wording {revision}.",
                    rationale=f"Historical rationale {revision}.",
                    decided_by=self.lead,
                    organization=self.organization,
                    revision_number=revision,
                    is_current=False,
                )
                for revision in range(1, 53)
            ]
        )
        self._authenticate()

        response = self.client.get(self._detail_url())
        history = response.data["decision_history"]

        self.assertEqual(history["count"], 52)
        self.assertTrue(history["truncated"])
        self.assertEqual(len(history["results"]), 50)
        self.assertEqual(
            [item["revision_number"] for item in history["results"]],
            list(range(52, 2, -1)),
        )

    def test_events_are_case_specific_bounded_and_oldest_first_in_window(self):
        base_time = timezone.now() - timedelta(hours=2)
        events = []
        for index in range(52):
            event = ModerationEvent.objects.create(
                case=self.context["case"],
                actor=None if index == 51 else self.lead,
                event_type=ModerationEvent.EventType.REVIEW_STARTED,
                notes=f"event-{index}",
                metadata={"private": f"metadata-{index}"},
            )
            ModerationEvent.objects.filter(pk=event.pk).update(
                created_at=base_time + timedelta(minutes=index)
            )
            events.append(event)
        other_case = self._create_context()["case"]
        ModerationEvent.objects.create(
            case=other_case,
            event_type=ModerationEvent.EventType.CASE_CREATED,
            notes="other-case-event",
        )

        self._authenticate()
        response = self.client.get(self._detail_url())
        event_data = response.data["events"]

        self.assertEqual(event_data["count"], 52)
        self.assertTrue(event_data["truncated"])
        self.assertEqual(len(event_data["results"]), 50)
        self.assertEqual(event_data["results"][0]["notes"], "event-2")
        self.assertEqual(event_data["results"][-1]["notes"], "event-51")
        self.assertIsNone(event_data["results"][-1]["actor"])
        self.assertNotIn("metadata", self._all_mapping_keys(event_data))
        self.assertNotIn(
            "other-case-event",
            {item["notes"] for item in event_data["results"]},
        )

    def test_detail_query_count_is_bounded_as_related_records_grow(self):
        for index in range(8):
            EvidenceSubmission.objects.create(
                thread=self.context["thread"],
                contributor=self.contributor,
                evidence_caption=f"Additional evidence {index}",
                evidence_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
                verified_by=self.reviewer,
            )
            ModerationEvent.objects.create(
                case=self.context["case"],
                event_type=ModerationEvent.EventType.REVIEW_STARTED,
                actor=self.lead,
            )
        self._authenticate()

        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(self._detail_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(captured), 15)

    @patch("api.views.schedule_adjudication_trust_updates")
    def test_success_and_conflict_are_followed_by_fresh_action_state(
        self,
        schedule_trust_updates,
    ):
        self._authenticate()
        action_url = (
            reverse(
                "adjudication_case_action",
                kwargs={"case_id": self.context["case"].id},
            )
            + f"?organization_id={self.organization.id}"
        )
        stale_response = self.client.post(
            action_url,
            {
                "moderator_verdict": AdjudicationDecision.Verdict.FAKE,
                "canonical_claim": "The reviewed claim is false.",
                "moderator_notes": "Human-reviewed rationale.",
                "expected_revision": 1,
            },
            format="json",
        )
        self.assertEqual(stale_response.status_code, status.HTTP_409_CONFLICT)
        fresh = self.client.get(self._detail_url()).data
        self.assertEqual(fresh["action_state"]["expected_revision"], 0)
        self.assertTrue(fresh["action_state"]["can_issue_first_decision"])

        success_response = self.client.post(
            action_url,
            {
                "moderator_verdict": AdjudicationDecision.Verdict.FAKE,
                "canonical_claim": "The reviewed claim is false.",
                "moderator_notes": "Human-reviewed rationale.",
                "expected_revision": 0,
            },
            format="json",
        )
        self.assertEqual(success_response.status_code, status.HTTP_200_OK)
        schedule_trust_updates.assert_called_once()

        resolved = self.client.get(self._detail_url()).data
        self.assertEqual(resolved["status"], ModerationCase.Status.RESOLVED)
        self.assertEqual(resolved["workflow_state"], "RESOLVED")
        self.assertEqual(
            resolved["resolution"]["code"],
            AdjudicationDecision.Verdict.FAKE,
        )
        self.assertEqual(
            resolved["resolution"]["resolved_by"]["id"],
            self.lead.id,
        )
        self.assertEqual(
            resolved["current_decision"]["provenance"]["status"],
            AdjudicationProvenance.HUMAN_ADJUDICATION,
        )
        self.assertEqual(resolved["action_state"]["expected_revision"], 1)
        self.assertIn(
            "CASE_RESOLVED",
            {
                blocker["code"]
                for blocker in resolved["action_state"]["blockers"]
            },
        )

        queue_response = self.client.get(
            reverse("adjudication_case_queue")
            + f"?organization_id={self.organization.id}"
        )
        self.assertEqual(queue_response.status_code, status.HTTP_200_OK)
        self.assertNotIn(
            str(self.context["case"].id),
            {item["id"] for item in queue_response.data["results"]},
        )
        legacy_response = self.client.get(
            reverse("moderation_verdict_queue")
            + f"?organization_id={self.organization.id}&reviewed=resolved"
        )
        self.assertEqual(legacy_response.status_code, status.HTTP_200_OK)
        self.assertIn(
            str(self.context["case"].id),
            {item["id"] for item in legacy_response.data["results"]},
        )
