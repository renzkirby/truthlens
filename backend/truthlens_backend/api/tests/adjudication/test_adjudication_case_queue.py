from datetime import timedelta
from uuid import UUID

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import (
    AdjudicationDecision,
    Claim,
    EvidenceSubmission,
    ModerationCase,
    Organization,
    OrganizationMembership,
    Thread,
    UserProfile,
)


class AdjudicationCaseQueueApiTests(APITestCase):
    def setUp(self):
        self.lead = User.objects.create_user(
            username="adjudication-queue-lead",
            password="test-password",
        )
        self.partner_moderator = User.objects.create_user(
            username="adjudication-queue-moderator",
            password="test-password",
        )
        self.ordinary_user = User.objects.create_user(
            username="adjudication-queue-ordinary",
            password="test-password",
        )
        self.author = User.objects.create_user(
            username="adjudication-queue-author",
            password="test-password",
        )
        self.contributor = User.objects.create_user(
            username="adjudication-queue-contributor",
            password="test-password",
        )
        self.safety_moderator = User.objects.create_user(
            username="adjudication-queue-safety",
            password="test-password",
        )
        self.safety_moderator.profile.role = UserProfile.Role.MOD
        self.safety_moderator.profile.save(update_fields=["role"])

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

        self.case = self._create_adjudication_case(
            organization=self.organization,
            context_text="Primary claim awaiting adjudication.",
            evidence_statuses=(
                EvidenceSubmission.EvidenceStatus.VERIFIED,
                EvidenceSubmission.EvidenceStatus.REJECTED,
                EvidenceSubmission.EvidenceStatus.UNVERIFIED,
            ),
        )

    @staticmethod
    def _create_organization(suffix):
        return Organization.objects.create(
            name=f"Adjudication Queue Partner {suffix}",
            slug=f"adjudication-queue-partner-{suffix}",
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

    def _create_adjudication_case(
        self,
        *,
        organization,
        context_text,
        case_status=ModerationCase.Status.OPEN,
        priority=ModerationCase.Priority.NORMAL,
        evidence_statuses=(),
        case_id=None,
        resolved_at=None,
    ):
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=context_text,
            ai_verdict="FAKE",
            ai_summary="Private automated analysis.",
            consensus_score=92.5,
        )
        thread = Thread.objects.create(
            claim=claim,
            author=self.author,
            caption=f"Thread for {context_text}",
        )
        for index, evidence_status in enumerate(evidence_statuses):
            EvidenceSubmission.objects.create(
                thread=thread,
                contributor=self.contributor,
                evidence_caption=f"Evidence {index} for {context_text}",
                evidence_url=f"https://example.com/evidence-{claim.id}-{index}",
                evidence_type=EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION,
                evidence_status=evidence_status,
                contributor_trust_snapshot=88.0,
            )

        values = {
            "case_type": ModerationCase.CaseType.ADJUDICATION,
            "claim": claim,
            "organization": organization,
            "status": case_status,
            "priority": priority,
            "source": ModerationCase.Source.COMMUNITY_ESCALATION,
            "resolved_at": resolved_at,
        }
        if case_id is not None:
            values["id"] = case_id
        return ModerationCase.objects.create(**values)

    def _queue_url(self, organization=None, **params):
        organization = organization or self.organization
        values = {"organization_id": organization.id, **params}
        query = "&".join(f"{key}={value}" for key, value in values.items())
        return f"{reverse('adjudication_case_queue')}?{query}"

    def _authenticate(self, user):
        self.client.force_authenticate(user=user)

    @staticmethod
    def _all_mapping_keys(value):
        keys = set()
        if isinstance(value, dict):
            keys.update(value)
            for nested in value.values():
                keys.update(
                    AdjudicationCaseQueueApiTests._all_mapping_keys(nested)
                )
        elif isinstance(value, list):
            for nested in value:
                keys.update(
                    AdjudicationCaseQueueApiTests._all_mapping_keys(nested)
                )
        return keys

    def test_authentication_and_exact_organization_capability_are_required(self):
        self.assertEqual(
            self.client.get(self._queue_url()).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

        for denied_user in (self.ordinary_user, self.safety_moderator):
            with self.subTest(user=denied_user.username):
                self._authenticate(denied_user)
                self.assertEqual(
                    self.client.get(self._queue_url()).status_code,
                    status.HTTP_403_FORBIDDEN,
                )

        other_lead = User.objects.create_user(
            username="adjudication-queue-other-lead",
            password="test-password",
        )
        self._add_member(
            other_lead,
            self.other_organization,
            OrganizationMembership.Role.LEAD_VERIFIER,
        )
        self._authenticate(other_lead)
        self.assertEqual(
            self.client.get(self._queue_url()).status_code,
            status.HTTP_403_FORBIDDEN,
        )

        for allowed_user in (self.lead, self.partner_moderator):
            with self.subTest(user=allowed_user.username):
                self._authenticate(allowed_user)
                self.assertEqual(
                    self.client.get(self._queue_url()).status_code,
                    status.HTTP_200_OK,
                )

    def test_management_and_non_adjudication_partner_roles_are_denied(self):
        for index, role in enumerate(
            (
                OrganizationMembership.Role.OWNER,
                OrganizationMembership.Role.ADMIN,
                OrganizationMembership.Role.RESEARCHER,
                OrganizationMembership.Role.CONTRIBUTOR,
            )
        ):
            user = User.objects.create_user(
                username=f"adjudication-queue-denied-{index}",
                password="test-password",
            )
            self._add_member(user, self.organization, role)
            self._authenticate(user)
            with self.subTest(role=role):
                self.assertEqual(
                    self.client.get(self._queue_url()).status_code,
                    status.HTTP_403_FORBIDDEN,
                )

    def test_inactive_membership_and_ineligible_organizations_are_denied(self):
        for index, membership_status in enumerate(
            (
                OrganizationMembership.Status.SUSPENDED,
                OrganizationMembership.Status.LEFT,
            )
        ):
            user = User.objects.create_user(
                username=f"adjudication-queue-inactive-{index}",
                password="test-password",
            )
            self._add_member(
                user,
                self.organization,
                OrganizationMembership.Role.LEAD_VERIFIER,
                membership_status=membership_status,
            )
            self._authenticate(user)
            with self.subTest(membership_status=membership_status):
                self.assertEqual(
                    self.client.get(self._queue_url()).status_code,
                    status.HTTP_403_FORBIDDEN,
                )

        self._authenticate(self.lead)
        for field, value in (
            ("verification_status", Organization.VerificationStatus.UNVERIFIED),
            ("partner_status", Organization.PartnerStatus.SUSPENDED),
        ):
            original = getattr(self.organization, field)
            setattr(self.organization, field, value)
            self.organization.save(update_fields=[field])
            with self.subTest(field=field):
                self.assertEqual(
                    self.client.get(self._queue_url()).status_code,
                    status.HTTP_403_FORBIDDEN,
                )
            setattr(self.organization, field, original)
            self.organization.save(update_fields=[field])

    def test_unknown_organization_is_not_found(self):
        self._authenticate(self.lead)
        url = (
            f"{reverse('adjudication_case_queue')}?organization_id="
            "00000000-0000-0000-0000-000000000001"
        )
        self.assertEqual(
            self.client.get(url).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_default_queue_returns_only_active_adjudication_cases_for_organization(
        self,
    ):
        active_cases = {self.case.id}
        for case_status in (
            ModerationCase.Status.IN_REVIEW,
            ModerationCase.Status.ESCALATED,
            ModerationCase.Status.REOPENED,
        ):
            active_cases.add(
                self._create_adjudication_case(
                    organization=self.organization,
                    context_text=f"Active {case_status} claim.",
                    case_status=case_status,
                ).id
            )

        self._create_adjudication_case(
            organization=self.organization,
            context_text="Resolved claim.",
            case_status=ModerationCase.Status.RESOLVED,
            resolved_at=timezone.now(),
        )
        self._create_adjudication_case(
            organization=self.organization,
            context_text="Cancelled claim.",
            case_status=ModerationCase.Status.CANCELLED,
        )
        self._create_adjudication_case(
            organization=self.other_organization,
            context_text="Other organization claim.",
        )
        ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.SAFETY,
            thread=self.case.claim.threads.first(),
            organization=self.organization,
        )
        evidence = self.case.claim.threads.first().evidence_submissions.first()
        ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=evidence,
            organization=self.organization,
        )

        self._authenticate(self.lead)
        response = self.client.get(self._queue_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], len(active_cases))
        self.assertEqual(
            {UUID(item["id"]) for item in response.data["results"]},
            active_cases,
        )
        self.assertTrue(
            all(
                item["workflow_state"] == "ACTIVE"
                for item in response.data["results"]
            )
        )

    def test_status_and_priority_filters_are_server_backed(self):
        resolved_high = self._create_adjudication_case(
            organization=self.organization,
            context_text="Resolved high-priority claim.",
            case_status=ModerationCase.Status.RESOLVED,
            priority=ModerationCase.Priority.HIGH,
            resolved_at=timezone.now(),
        )
        self._create_adjudication_case(
            organization=self.organization,
            context_text="Resolved low-priority claim.",
            case_status=ModerationCase.Status.RESOLVED,
            priority=ModerationCase.Priority.LOW,
            resolved_at=timezone.now(),
        )

        self._authenticate(self.lead)
        response = self.client.get(
            self._queue_url(
                status=ModerationCase.Status.RESOLVED,
                priority=ModerationCase.Priority.HIGH,
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(resolved_high.id))
        self.assertEqual(response.data["results"][0]["workflow_state"], "RESOLVED")

        cancelled = self._create_adjudication_case(
            organization=self.organization,
            context_text="Cancelled filtered claim.",
            case_status=ModerationCase.Status.CANCELLED,
        )
        cancelled_response = self.client.get(
            self._queue_url(status=ModerationCase.Status.CANCELLED)
        )
        self.assertEqual(cancelled_response.data["count"], 1)
        self.assertEqual(
            cancelled_response.data["results"][0]["id"],
            str(cancelled.id),
        )
        self.assertEqual(
            cancelled_response.data["results"][0]["workflow_state"],
            "CANCELLED",
        )

    def test_active_order_uses_semantic_priority_age_and_case_id(self):
        ModerationCase.objects.filter(pk=self.case.pk).delete()
        shared_time = timezone.now() - timedelta(hours=2)
        identifiers = {
            "urgent_first": "00000000-0000-0000-0000-000000000001",
            "urgent_second": "00000000-0000-0000-0000-000000000002",
            "high_old": "00000000-0000-0000-0000-000000000003",
            "high_new": "00000000-0000-0000-0000-000000000004",
            "normal": "00000000-0000-0000-0000-000000000005",
            "low": "00000000-0000-0000-0000-000000000006",
        }
        cases = {}
        for label, priority in (
            ("urgent_second", ModerationCase.Priority.URGENT),
            ("low", ModerationCase.Priority.LOW),
            ("normal", ModerationCase.Priority.NORMAL),
            ("urgent_first", ModerationCase.Priority.URGENT),
            ("high_new", ModerationCase.Priority.HIGH),
            ("high_old", ModerationCase.Priority.HIGH),
        ):
            cases[label] = self._create_adjudication_case(
                organization=self.organization,
                context_text=f"Ordered {label} claim.",
                priority=priority,
                case_id=identifiers[label],
            )
        ModerationCase.objects.filter(
            pk__in=[case.id for case in cases.values()]
        ).update(created_at=shared_time)
        ModerationCase.objects.filter(pk=cases["high_new"].pk).update(
            created_at=shared_time + timedelta(hours=1)
        )

        self._authenticate(self.lead)
        response = self.client.get(self._queue_url())

        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [
                identifiers["urgent_first"],
                identifiers["urgent_second"],
                identifiers["high_old"],
                identifiers["high_new"],
                identifiers["normal"],
                identifiers["low"],
            ],
        )

    def test_terminal_order_is_null_safe_and_uses_updated_at_tie_breaker(self):
        ModerationCase.objects.filter(pk=self.case.pk).delete()
        now = timezone.now()
        older = self._create_adjudication_case(
            organization=self.organization,
            context_text="Older resolved claim.",
            case_status=ModerationCase.Status.RESOLVED,
            resolved_at=now - timedelta(days=2),
        )
        newest = self._create_adjudication_case(
            organization=self.organization,
            context_text="Newest resolved claim.",
            case_status=ModerationCase.Status.RESOLVED,
            resolved_at=now - timedelta(days=1),
        )
        null_older = self._create_adjudication_case(
            organization=self.organization,
            context_text="Older null-resolution claim.",
            case_status=ModerationCase.Status.RESOLVED,
        )
        null_newer = self._create_adjudication_case(
            organization=self.organization,
            context_text="Newer null-resolution claim.",
            case_status=ModerationCase.Status.RESOLVED,
            case_id="00000000-0000-0000-0000-000000000002",
        )
        null_newer_first = self._create_adjudication_case(
            organization=self.organization,
            context_text="First tied null-resolution claim.",
            case_status=ModerationCase.Status.RESOLVED,
            case_id="00000000-0000-0000-0000-000000000001",
        )
        ModerationCase.objects.filter(pk=null_older.pk).update(
            updated_at=now - timedelta(hours=2)
        )
        ModerationCase.objects.filter(pk=null_newer.pk).update(
            updated_at=now - timedelta(hours=1)
        )
        ModerationCase.objects.filter(pk=null_newer_first.pk).update(
            updated_at=now - timedelta(hours=1)
        )

        self._authenticate(self.lead)
        response = self.client.get(
            self._queue_url(status=ModerationCase.Status.RESOLVED)
        )

        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [
                str(newest.id),
                str(older.id),
                str(null_newer_first.id),
                str(null_newer.id),
                str(null_older.id),
            ],
        )

    def test_query_contract_rejects_invalid_unsupported_and_duplicate_values(self):
        self._authenticate(self.lead)
        base_url = reverse("adjudication_case_queue")
        organization_id = self.organization.id
        invalid_urls = (
            base_url,
            f"{base_url}?organization_id=not-a-uuid",
            self._queue_url(status="UNKNOWN"),
            self._queue_url(priority="UNKNOWN"),
            self._queue_url(limit=0),
            self._queue_url(limit=101),
            self._queue_url(offset=-1),
            self._queue_url(search="unsupported"),
            (
                f"{base_url}?organization_id={organization_id}"
                f"&organization_id={organization_id}"
            ),
            (
                f"{base_url}?organization_id={organization_id}"
                "&status=OPEN&status=OPEN"
            ),
            (
                f"{base_url}?organization_id={organization_id}"
                "&limit=20&limit=20"
            ),
        )

        for url in invalid_urls:
            with self.subTest(url=url):
                self.assertEqual(
                    self.client.get(url).status_code,
                    status.HTTP_400_BAD_REQUEST,
                )

    def test_count_pagination_and_join_aggregates_are_authoritative(self):
        second_thread = Thread.objects.create(
            claim=self.case.claim,
            author=self.author,
            caption="Second thread for aggregate checks.",
        )
        second_verified = EvidenceSubmission.objects.create(
            thread=second_thread,
            contributor=self.contributor,
            evidence_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
        )
        second_unreviewed = EvidenceSubmission.objects.create(
            thread=second_thread,
            contributor=self.contributor,
            evidence_status=EvidenceSubmission.EvidenceStatus.UNVERIFIED,
        )
        for evidence in (second_verified, second_unreviewed):
            ModerationCase.objects.create(
                case_type=ModerationCase.CaseType.EVIDENCE,
                evidence_submission=evidence,
                organization=self.organization,
            )

        second_case = self._create_adjudication_case(
            organization=self.organization,
            context_text="Second paginated claim.",
        )

        self._authenticate(self.lead)
        full_response = self.client.get(self._queue_url())
        paginated_response = self.client.get(self._queue_url(limit=1, offset=1))

        self.assertEqual(full_response.data["count"], 2)
        self.assertEqual(len(full_response.data["results"]), 2)
        self.assertEqual(paginated_response.data["count"], 2)
        self.assertEqual(paginated_response.data["limit"], 1)
        self.assertEqual(paginated_response.data["offset"], 1)
        self.assertEqual(len(paginated_response.data["results"]), 1)
        self.assertIn(
            paginated_response.data["results"][0]["id"],
            {str(self.case.id), str(second_case.id)},
        )

        first_item = next(
            item
            for item in full_response.data["results"]
            if item["id"] == str(self.case.id)
        )
        self.assertEqual(
            first_item["evidence_review"],
            {
                "total": 5,
                "verified": 2,
                "rejected": 1,
                "unreviewed": 2,
                "active_evidence_cases": 2,
                "all_reviewed": False,
            },
        )

    def test_response_is_explicitly_allowlisted_and_omits_private_fields(self):
        self._authenticate(self.lead)
        response = self.client.get(self._queue_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data),
            {"count", "limit", "offset", "organization", "results"},
        )
        self.assertEqual(set(response.data["organization"]), {"id", "name"})

        item = response.data["results"][0]
        self.assertEqual(
            set(item),
            {
                "id",
                "status",
                "status_label",
                "workflow_state",
                "priority",
                "priority_label",
                "source",
                "created_at",
                "updated_at",
                "resolved_at",
                "claim",
                "evidence_review",
                "current_decision",
                "adjudication_blocked",
            },
        )
        self.assertEqual(
            set(item["claim"]),
            {"id", "claim_type", "context_text"},
        )
        self.assertEqual(
            set(item["evidence_review"]),
            {
                "total",
                "verified",
                "rejected",
                "unreviewed",
                "active_evidence_cases",
                "all_reviewed",
            },
        )
        self.assertIsNone(item["current_decision"])
        self.assertFalse(item["adjudication_blocked"])
        self.assertTrue(
            self._all_mapping_keys(response.data).isdisjoint(
                {
                    "email",
                    "trust_score",
                    "contributor_trust_snapshot",
                    "profile",
                    "ai_verdict",
                    "ai_summary",
                    "consensus_score",
                    "publication_status",
                    "decided_by",
                    "rationale",
                }
            )
        )

    def test_current_decision_is_visible_only_with_attributable_selected_org_context(
        self,
    ):
        self.case.status = ModerationCase.Status.RESOLVED
        self.case.resolution_code = AdjudicationDecision.Verdict.FACT
        self.case.resolved_at = timezone.now()
        self.case.save(
            update_fields=["status", "resolution_code", "resolved_at"]
        )
        decision = AdjudicationDecision.objects.create(
            claim=self.case.claim,
            moderation_case=self.case,
            verdict=AdjudicationDecision.Verdict.FACT,
            canonical_claim="The canonical reviewed claim.",
            rationale="The reviewed sources support the claim.",
            decided_by=self.lead,
            organization=self.organization,
            decision_source=AdjudicationDecision.DecisionSource.HUMAN_REVIEW,
            revision_number=1,
            is_current=True,
        )

        external_case = self._create_adjudication_case(
            organization=self.organization,
            context_text="Claim with an external current decision.",
        )
        external_resolution_case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.ADJUDICATION,
            claim=external_case.claim,
            organization=self.other_organization,
            status=ModerationCase.Status.RESOLVED,
            resolution_code=AdjudicationDecision.Verdict.SATIRE,
            resolved_at=timezone.now(),
        )
        AdjudicationDecision.objects.create(
            claim=external_case.claim,
            moderation_case=external_resolution_case,
            verdict=AdjudicationDecision.Verdict.SATIRE,
            canonical_claim="Private external canonical claim.",
            rationale="Private external rationale.",
            decided_by=self.ordinary_user,
            organization=self.other_organization,
            revision_number=1,
            is_current=True,
        )

        uncertain_case = self._create_adjudication_case(
            organization=self.organization,
            context_text="Claim with uncertain imported provenance.",
        )
        AdjudicationDecision.objects.create(
            claim=uncertain_case.claim,
            verdict=AdjudicationDecision.Verdict.MISLEADING,
            canonical_claim="Imported canonical claim.",
            rationale="Imported rationale without sufficient provenance.",
            organization=self.organization,
            decision_source=AdjudicationDecision.DecisionSource.LEGACY_MIGRATION,
            revision_number=1,
            is_current=True,
        )

        mismatched_case = self._create_adjudication_case(
            organization=self.organization,
            context_text="Claim with mismatched organization provenance.",
        )
        mismatched_resolution_case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.ADJUDICATION,
            claim=mismatched_case.claim,
            organization=self.other_organization,
            status=ModerationCase.Status.RESOLVED,
            resolution_code=AdjudicationDecision.Verdict.UNVERIFIED,
            resolved_at=timezone.now(),
        )
        AdjudicationDecision.objects.create(
            claim=mismatched_case.claim,
            moderation_case=mismatched_resolution_case,
            verdict=AdjudicationDecision.Verdict.UNVERIFIED,
            canonical_claim="Mismatched canonical claim.",
            rationale="Mismatched organization rationale.",
            decided_by=self.lead,
            organization=self.organization,
            revision_number=1,
            is_current=True,
        )

        self._authenticate(self.lead)
        resolved_response = self.client.get(
            self._queue_url(status=ModerationCase.Status.RESOLVED)
        )
        active_response = self.client.get(self._queue_url())

        visible = resolved_response.data["results"][0]
        self.assertEqual(
            set(visible["current_decision"]),
            {
                "id",
                "verdict",
                "verdict_label",
                "revision_number",
                "decided_at",
            },
        )
        self.assertEqual(visible["current_decision"]["id"], str(decision.id))
        self.assertEqual(
            visible["current_decision"]["verdict"],
            AdjudicationDecision.Verdict.FACT,
        )
        self.assertEqual(visible["current_decision"]["verdict_label"], "Fact")
        self.assertEqual(visible["current_decision"]["revision_number"], 1)
        self.assertIsNotNone(visible["current_decision"]["decided_at"])
        self.assertTrue(visible["adjudication_blocked"])

        active_by_id = {
            item["id"]: item for item in active_response.data["results"]
        }
        for restricted_case in (
            external_case,
            uncertain_case,
            mismatched_case,
        ):
            item = active_by_id[str(restricted_case.id)]
            self.assertIsNone(item["current_decision"])
            self.assertTrue(item["adjudication_blocked"])

        rendered = str(active_response.data)
        self.assertNotIn(AdjudicationDecision.Verdict.SATIRE, rendered)
        self.assertNotIn(AdjudicationDecision.Verdict.MISLEADING, rendered)
        self.assertNotIn(AdjudicationDecision.Verdict.UNVERIFIED, rendered)
        self.assertNotIn("Private external canonical claim", rendered)
        self.assertNotIn("Private external rationale", rendered)
        self.assertNotIn(self.ordinary_user.username, rendered)
        self.assertNotIn("Imported canonical claim", rendered)
        self.assertNotIn("Imported rationale", rendered)
        self.assertNotIn("Mismatched canonical claim", rendered)
        self.assertNotIn("Mismatched organization rationale", rendered)

    def test_unattributed_verdict_cache_does_not_become_decision_or_blocker(self):
        self.case.claim.final_verdict = AdjudicationDecision.Verdict.FAKE
        self.case.claim.save(update_fields=["final_verdict"])

        self._authenticate(self.lead)
        response = self.client.get(self._queue_url())

        item = response.data["results"][0]
        self.assertIsNone(item["current_decision"])
        self.assertFalse(item["adjudication_blocked"])
        self.assertNotIn(AdjudicationDecision.Verdict.FAKE, str(item))

    def test_query_count_is_bounded_as_queue_rows_grow(self):
        for index in range(8):
            self._create_adjudication_case(
                organization=self.organization,
                context_text=f"Additional query-bound claim {index}.",
                evidence_statuses=(
                    EvidenceSubmission.EvidenceStatus.VERIFIED,
                    EvidenceSubmission.EvidenceStatus.REJECTED,
                ),
            )

        self._authenticate(self.lead)
        with CaptureQueriesContext(connection) as captured_queries:
            response = self.client.get(self._queue_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 9)
        self.assertLessEqual(len(captured_queries), 7)

    def test_only_get_is_allowed(self):
        self._authenticate(self.lead)
        self.assertEqual(
            self.client.post(self._queue_url(), {}).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
