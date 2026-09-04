from django.contrib.auth.models import User
from django.urls import reverse

from rest_framework import status
from rest_framework.test import (
    APIClient,
    APITestCase,
)

from .models import (
    Claim,
    EvidenceSubmission,
    Organization,
    OrganizationMembership,
    Thread,
    UserProfile,
    VerificationAssignment,
)

from .verification_assignment_service import (
    claim_verification_assignment,
    ensure_verification_assignment,
)


class VerificationAssignmentApiTests(APITestCase):
    def setUp(self):
        # ---------------------------------
        # Community user
        # ---------------------------------
        self.community_user = User.objects.create_user(
            username="intake-community-user",
            password="test-password",
        )

        # ---------------------------------
        # Partner personnel
        # ---------------------------------
        self.lead_a = User.objects.create_user(
            username="intake-lead-a",
            password="test-password",
        )

        self.lead_b = User.objects.create_user(
            username="intake-lead-b",
            password="test-password",
        )

        self.reviewer_a = User.objects.create_user(
            username="intake-reviewer-a",
            password="test-password",
        )

        self.contributor_a = User.objects.create_user(
            username="intake-contributor-a",
            password="test-password",
        )

        # ---------------------------------
        # Platform Safety Moderator
        # ---------------------------------
        self.safety_moderator = User.objects.create_user(
            username="intake-safety-moderator",
            password="test-password",
        )

        self.safety_moderator.profile.role = UserProfile.Role.MOD

        self.safety_moderator.profile.save(update_fields=["role"])

        # ---------------------------------
        # Organizations
        # ---------------------------------
        self.organization_a = Organization.objects.create(
            name="Verification API Partner A",
            slug="verification-api-partner-a",
            organization_type=(Organization.OrganizationType.FACT_CHECKING),
            verification_status=(Organization.VerificationStatus.VERIFIED),
            partner_status=(Organization.PartnerStatus.ACTIVE),
        )

        self.organization_b = Organization.objects.create(
            name="Verification API Partner B",
            slug="verification-api-partner-b",
            organization_type=(Organization.OrganizationType.FACT_CHECKING),
            verification_status=(Organization.VerificationStatus.VERIFIED),
            partner_status=(Organization.PartnerStatus.ACTIVE),
        )

        # ---------------------------------
        # Memberships
        # ---------------------------------
        OrganizationMembership.objects.create(
            organization=self.organization_a,
            user=self.lead_a,
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        OrganizationMembership.objects.create(
            organization=self.organization_b,
            user=self.lead_b,
            role=(OrganizationMembership.Role.LEAD_VERIFIER),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        OrganizationMembership.objects.create(
            organization=self.organization_a,
            user=self.reviewer_a,
            role=(OrganizationMembership.Role.MODERATOR),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        OrganizationMembership.objects.create(
            organization=self.organization_a,
            user=self.contributor_a,
            role=(OrganizationMembership.Role.CONTRIBUTOR),
            status=(OrganizationMembership.Status.ACTIVE),
        )

        # ---------------------------------
        # API clients
        # ---------------------------------
        self.lead_a_client = APIClient()
        self.lead_a_client.force_authenticate(user=self.lead_a)

        self.lead_b_client = APIClient()
        self.lead_b_client.force_authenticate(user=self.lead_b)

        self.reviewer_a_client = APIClient()
        self.reviewer_a_client.force_authenticate(user=self.reviewer_a)

        self.contributor_a_client = APIClient()
        self.contributor_a_client.force_authenticate(user=self.contributor_a)

        self.safety_client = APIClient()
        self.safety_client.force_authenticate(user=self.safety_moderator)

        self.unauthenticated_client = APIClient()

    # =====================================
    # Helpers
    # =====================================

    def _create_available_assignment(
        self,
        *,
        suffix="default",
    ):
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=(f"Verification intake API claim " f"{suffix}."),
            ai_verdict="UNVERIFIED",
            ai_summary=("This claim requires professional " "verification."),
            consensus_score=55.0,
        )

        thread = Thread.objects.create(
            claim=claim,
            author=self.community_user,
            caption=(f"Community investigation {suffix}."),
            status=Thread.Status.OPEN,
        )

        assignment = ensure_verification_assignment(claim=claim)

        return {
            "claim": claim,
            "thread": thread,
            "assignment": assignment,
        }

    def _claim_for_a(
        self,
        *,
        suffix="active-a",
    ):
        fixture = self._create_available_assignment(suffix=suffix)

        assignment = claim_verification_assignment(
            assignment=fixture["assignment"],
            organization=self.organization_a,
            actor=self.lead_a,
        )

        fixture["assignment"] = assignment

        return fixture

    def _claim_for_b(
        self,
        *,
        suffix="active-b",
    ):
        fixture = self._create_available_assignment(suffix=suffix)

        assignment = claim_verification_assignment(
            assignment=fixture["assignment"],
            organization=self.organization_b,
            actor=self.lead_b,
        )

        fixture["assignment"] = assignment

        return fixture

    # =====================================
    # Authentication / scope
    # =====================================

    def test_intake_requires_authentication(self):
        response = self.unauthenticated_client.get(
            reverse("verification_intake"),
            {
                "organization_id": str(self.organization_a.id),
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_intake_requires_organization_scope(
        self,
    ):
        response = self.lead_a_client.get(reverse("verification_intake"))

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertIn(
            "organization_id",
            response.data["detail"],
        )

    def test_platform_safety_moderator_cannot_access_intake(
        self,
    ):
        response = self.safety_client.get(
            reverse("verification_intake"),
            {
                "organization_id": str(self.organization_a.id),
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_partner_contributor_cannot_access_intake(
        self,
    ):
        response = self.contributor_a_client.get(
            reverse("verification_intake"),
            {
                "organization_id": str(self.organization_a.id),
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    # =====================================
    # Available intake
    # =====================================

    def test_lead_verifier_can_view_available_intake(
        self,
    ):
        first = self._create_available_assignment(suffix="first")

        second = self._create_available_assignment(suffix="second")

        response = self.lead_a_client.get(
            reverse("verification_intake"),
            {
                "organization_id": str(self.organization_a.id),
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["count"],
            2,
        )

        returned_ids = {item["id"] for item in response.data["results"]}

        self.assertEqual(
            returned_ids,
            {
                str(first["assignment"].id),
                str(second["assignment"].id),
            },
        )

        for item in response.data["results"]:
            self.assertEqual(
                item["status"],
                VerificationAssignment.Status.AVAILABLE,
            )

            self.assertIsNone(item["organization"])

            self.assertIsNone(item["claimed_by"])

    def test_active_assignment_is_not_returned_in_available_intake(
        self,
    ):
        available = self._create_available_assignment(suffix="available")

        active = self._claim_for_a(suffix="already-active")

        response = self.lead_a_client.get(
            reverse("verification_intake"),
            {
                "organization_id": str(self.organization_a.id),
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        returned_ids = {item["id"] for item in response.data["results"]}

        self.assertIn(
            str(available["assignment"].id),
            returned_ids,
        )

        self.assertNotIn(
            str(active["assignment"].id),
            returned_ids,
        )

    def test_intake_pagination_returns_total_count(
        self,
    ):
        self._create_available_assignment(suffix="pagination-1")

        self._create_available_assignment(suffix="pagination-2")

        self._create_available_assignment(suffix="pagination-3")

        response = self.lead_a_client.get(
            reverse("verification_intake"),
            {
                "organization_id": str(self.organization_a.id),
                "limit": 1,
                "offset": 1,
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["count"],
            3,
        )

        self.assertEqual(
            response.data["limit"],
            1,
        )

        self.assertEqual(
            response.data["offset"],
            1,
        )

        self.assertEqual(
            len(response.data["results"]),
            1,
        )

    def test_intake_includes_community_thread_context(
        self,
    ):
        fixture = self._create_available_assignment(
            suffix="community-context",
        )

        second_thread = Thread.objects.create(
            claim=fixture["claim"],
            author=self.community_user,
            caption=("Second community discussion."),
            status=Thread.Status.OPEN,
        )

        response = self.lead_a_client.get(
            reverse("verification_intake"),
            {
                "organization_id": str(self.organization_a.id),
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        assignment = next(
            item
            for item in response.data["results"]
            if item["id"] == str(fixture["assignment"].id)
        )

        threads = assignment["claim"]["community_threads"]

        returned_thread_ids = {str(thread["id"]) for thread in threads}

        self.assertEqual(
            returned_thread_ids,
            {
                str(fixture["thread"].id),
                str(second_thread.id),
            },
        )

        for thread in threads:
            self.assertEqual(
                str(thread["claim_id"]),
                str(fixture["claim"].id),
            )

    # =====================================
    # Claim
    # =====================================

    def test_lead_verifier_can_claim_available_investigation(
        self,
    ):
        fixture = self._create_available_assignment(suffix="claim")

        response = self.lead_a_client.post(
            reverse(
                "verification_assignment_claim",
                kwargs={
                    "assignment_id": fixture["assignment"].id,
                },
            ),
            {
                "organization_id": str(self.organization_a.id),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["status"],
            VerificationAssignment.Status.ACTIVE,
        )

        self.assertEqual(
            str(response.data["organization"]["id"]),
            str(self.organization_a.id),
        )

        self.assertEqual(
            response.data["claimed_by"]["username"],
            self.lead_a.username,
        )

        self.assertIsNotNone(response.data["claimed_at"])

        fixture["assignment"].refresh_from_db()

        self.assertEqual(
            fixture["assignment"].status,
            VerificationAssignment.Status.ACTIVE,
        )

        self.assertEqual(
            fixture["assignment"].organization_id,
            self.organization_a.id,
        )

    def test_same_organization_claim_is_idempotent(
        self,
    ):
        fixture = self._claim_for_a(suffix="idempotent")

        response = self.lead_a_client.post(
            reverse(
                "verification_assignment_claim",
                kwargs={
                    "assignment_id": fixture["assignment"].id,
                },
            ),
            {
                "organization_id": str(self.organization_a.id),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["status"],
            VerificationAssignment.Status.ACTIVE,
        )

        self.assertEqual(
            str(response.data["organization"]["id"]),
            str(self.organization_a.id),
        )

    def test_second_organization_cannot_claim_active_investigation(
        self,
    ):
        fixture = self._claim_for_a(suffix="conflict")

        response = self.lead_b_client.post(
            reverse(
                "verification_assignment_claim",
                kwargs={
                    "assignment_id": fixture["assignment"].id,
                },
            ),
            {
                "organization_id": str(self.organization_b.id),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_409_CONFLICT,
        )

        fixture["assignment"].refresh_from_db()

        self.assertEqual(
            fixture["assignment"].organization_id,
            self.organization_a.id,
        )

    def test_non_lead_partner_cannot_claim_investigation(
        self,
    ):
        fixture = self._create_available_assignment(suffix="reviewer-claim")

        response = self.reviewer_a_client.post(
            reverse(
                "verification_assignment_claim",
                kwargs={
                    "assignment_id": fixture["assignment"].id,
                },
            ),
            {
                "organization_id": str(self.organization_a.id),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        fixture["assignment"].refresh_from_db()

        self.assertEqual(
            fixture["assignment"].status,
            VerificationAssignment.Status.AVAILABLE,
        )

    # =====================================
    # Release
    # =====================================

    def test_owner_organization_can_release_untouched_work(
        self,
    ):
        fixture = self._claim_for_a(suffix="release")

        old_assignment_id = fixture["assignment"].id

        response = self.lead_a_client.post(
            reverse(
                "verification_assignment_release",
                kwargs={
                    "assignment_id": old_assignment_id,
                },
            ),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        released = response.data["released_assignment"]

        available = response.data["available_assignment"]

        self.assertEqual(
            released["status"],
            VerificationAssignment.Status.RELEASED,
        )

        self.assertEqual(
            str(released["organization"]["id"]),
            str(self.organization_a.id),
        )

        self.assertIsNotNone(released["released_at"])

        self.assertEqual(
            available["status"],
            VerificationAssignment.Status.AVAILABLE,
        )

        self.assertIsNone(available["organization"])

        self.assertNotEqual(
            released["id"],
            available["id"],
        )

    def test_other_organization_cannot_release_assignment(
        self,
    ):
        fixture = self._claim_for_a(suffix="unauthorized-release")

        response = self.lead_b_client.post(
            reverse(
                "verification_assignment_release",
                kwargs={
                    "assignment_id": fixture["assignment"].id,
                },
            ),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        fixture["assignment"].refresh_from_db()

        self.assertEqual(
            fixture["assignment"].status,
            VerificationAssignment.Status.ACTIVE,
        )

        self.assertEqual(
            fixture["assignment"].organization_id,
            self.organization_a.id,
        )

    def test_release_after_authoritative_review_returns_conflict(
        self,
    ):
        fixture = self._claim_for_a(suffix="review-started")

        EvidenceSubmission.objects.create(
            thread=fixture["thread"],
            contributor=self.community_user,
            evidence_caption=("Evidence already reviewed."),
            evidence_url=("https://example.com/" "reviewed-evidence"),
            evidence_type=(EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION),
            evidence_status=(EvidenceSubmission.EvidenceStatus.VERIFIED),
            contributor_trust_snapshot=50.0,
            verified_by=self.lead_a,
        )

        response = self.lead_a_client.post(
            reverse(
                "verification_assignment_release",
                kwargs={
                    "assignment_id": fixture["assignment"].id,
                },
            ),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_409_CONFLICT,
        )

        fixture["assignment"].refresh_from_db()

        self.assertEqual(
            fixture["assignment"].status,
            VerificationAssignment.Status.ACTIVE,
        )

    # =====================================
    # Organization workload
    # =====================================

    def test_partner_can_view_only_own_organization_workload(
        self,
    ):
        active_a = self._claim_for_a(suffix="workload-a")

        active_b = self._claim_for_b(suffix="workload-b")

        response = self.lead_a_client.get(
            reverse("verification_workload"),
            {
                "organization_id": str(self.organization_a.id),
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["count"],
            1,
        )

        self.assertEqual(
            str(response.data["organization"]["id"]),
            str(self.organization_a.id),
        )

        returned_ids = {item["id"] for item in response.data["results"]}

        self.assertEqual(
            returned_ids,
            {
                str(active_a["assignment"].id),
            },
        )

        self.assertNotIn(
            str(active_b["assignment"].id),
            returned_ids,
        )

    def test_partner_reviewer_can_view_organization_workload(
        self,
    ):
        active = self._claim_for_a(suffix="reviewer-workload")

        response = self.reviewer_a_client.get(
            reverse("verification_workload"),
            {
                "organization_id": str(self.organization_a.id),
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["count"],
            1,
        )

        self.assertEqual(
            response.data["results"][0]["id"],
            str(active["assignment"].id),
        )

    def test_partner_cannot_view_other_organization_workload(
        self,
    ):
        self._claim_for_b(suffix="cross-org-workload")

        response = self.lead_a_client.get(
            reverse("verification_workload"),
            {
                "organization_id": str(self.organization_b.id),
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_platform_safety_moderator_cannot_view_partner_workload(
        self,
    ):
        self._claim_for_a(suffix="safety-workload")

        response = self.safety_client.get(
            reverse("verification_workload"),
            {
                "organization_id": str(self.organization_a.id),
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_partner_contributor_cannot_view_workload(
        self,
    ):
        self._claim_for_a(suffix="contributor-workload")

        response = self.contributor_a_client.get(
            reverse("verification_workload"),
            {
                "organization_id": str(self.organization_a.id),
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    # =====================================
    # Invalid pagination
    # =====================================

    def test_invalid_intake_pagination_returns_400(
        self,
    ):
        response = self.lead_a_client.get(
            reverse("verification_intake"),
            {
                "organization_id": str(self.organization_a.id),
                "limit": "not-a-number",
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_workload_limit_above_maximum_returns_400(
        self,
    ):
        response = self.lead_a_client.get(
            reverse("verification_workload"),
            {
                "organization_id": str(self.organization_a.id),
                "limit": 101,
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
