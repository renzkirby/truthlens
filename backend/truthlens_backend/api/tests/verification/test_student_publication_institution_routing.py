from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from api.models import (
    Claim,
    ClaimInstitutionAssociation,
    ClaimInvestigationClassification,
    Institution,
    Organization,
    OrganizationInstitutionAffiliation,
    OrganizationMembership,
)
from api.verification_assignment_service import (
    VerificationAssignmentAuthorizationError,
    claim_verification_assignment,
    ensure_verification_assignment,
)
from api.verification_domain_policy import (
    INSTITUTION_AFFILIATION_NOT_VERIFIED,
    NEEDS_INSTITUTION_IDENTITY,
    OUTSIDE_INSTITUTION_SCOPE,
    organization_claim_eligibility_reason,
)


class StudentPublicationInstitutionRoutingTests(TestCase):
    def setUp(self):
        self.platform_admin = User.objects.create_superuser(
            username="institution-routing-platform-admin",
            email="institution-routing-admin@example.test",
            password="test-password",
        )
        self.student_lead = User.objects.create_user(
            username="institution-routing-student-lead",
            password="test-password",
        )
        self.ordinary_lead = User.objects.create_user(
            username="institution-routing-ordinary-lead",
            password="test-password",
        )

        self.institution_a = Institution.objects.create(
            name="Routing University A",
            slug="routing-university-a",
        )
        self.institution_b = Institution.objects.create(
            name="Routing University B",
            slug="routing-university-b",
        )

        self.student_publication = Organization.objects.create(
            name="Routing Campus Chronicle",
            slug="routing-campus-chronicle",
            organization_type=Organization.OrganizationType.NEWS,
            organization_subtype=(
                Organization.OrganizationSubtype.STUDENT_PUBLICATION
            ),
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
            verification_specializations=[],
        )
        self.ordinary_partner = Organization.objects.create(
            name="Routing Fact Check Partner",
            slug="routing-fact-check-partner",
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
            verification_specializations=["SCIENCE"],
        )

        OrganizationMembership.objects.create(
            organization=self.student_publication,
            user=self.student_lead,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        OrganizationMembership.objects.create(
            organization=self.ordinary_partner,
            user=self.ordinary_lead,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )

        self._set_affiliation(
            status=OrganizationInstitutionAffiliation.VerificationStatus.VERIFIED
        )

        self.student_client = APIClient()
        self.student_client.force_authenticate(user=self.student_lead)

    def _set_affiliation(self, *, status):
        OrganizationInstitutionAffiliation.objects.filter(
            organization=self.student_publication
        ).delete()
        reviewed = (
            status
            != OrganizationInstitutionAffiliation.VerificationStatus.PENDING
        )
        return OrganizationInstitutionAffiliation.objects.create(
            organization=self.student_publication,
            institution=self.institution_a,
            coverage_scope=(
                OrganizationInstitutionAffiliation.CoverageScope.INSTITUTION_WIDE
            ),
            verification_status=status,
            rationale=(
                "Platform review confirmed the publication affiliation."
                if reviewed
                else ""
            ),
            reviewed_by=self.platform_admin if reviewed else None,
            reviewed_at=timezone.now() if reviewed else None,
        )

    def _make_claim(
        self,
        *,
        suffix,
        campus_state,
        institutions=(),
        domains=("SCIENCE",),
    ):
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=f"Routing policy claim {suffix}.",
        )
        classification = ClaimInvestigationClassification.objects.create(
            claim=claim,
            domains=list(domains),
            primary_subject=domains[0] if domains else None,
            campus_context_state=campus_state,
            campus_context_rationale=(
                "Reviewed campus context for routing policy tests."
                if campus_state is not None
                else ""
            ),
            campus_context_reviewed_by=(
                self.platform_admin if campus_state is not None else None
            ),
            campus_context_reviewed_at=(
                timezone.now() if campus_state is not None else None
            ),
            rationale="Reviewed subject classification for routing policy tests.",
        )
        for institution in institutions:
            ClaimInstitutionAssociation.objects.create(
                classification=classification,
                institution=institution,
                rationale=(
                    f"The proposition directly concerns {institution.name}."
                ),
                assigned_by=self.platform_admin,
            )
        assignment = ensure_verification_assignment(claim=claim)
        return claim, classification, assignment

    def test_verified_student_publication_matches_own_institution_without_subject_scope(self):
        _claim, classification, _assignment = self._make_claim(
            suffix="own-institution-health",
            campus_state=ClaimInvestigationClassification.CampusContextState.CONFIRMED,
            institutions=(self.institution_a,),
            domains=("HEALTH",),
        )

        self.assertEqual(self.student_publication.verification_specializations, [])
        self.assertIsNone(
            organization_claim_eligibility_reason(
                classification=classification,
                organization=self.student_publication,
            )
        )

    def test_student_publication_rejects_other_institution(self):
        _claim, classification, _assignment = self._make_claim(
            suffix="other-institution",
            campus_state=ClaimInvestigationClassification.CampusContextState.CONFIRMED,
            institutions=(self.institution_b,),
        )

        self.assertEqual(
            organization_claim_eligibility_reason(
                classification=classification,
                organization=self.student_publication,
            ),
            OUTSIDE_INSTITUTION_SCOPE,
        )

    def test_confirmed_campus_claim_without_identity_needs_institution_identity(self):
        _claim, classification, _assignment = self._make_claim(
            suffix="confirmed-without-institution",
            campus_state=ClaimInvestigationClassification.CampusContextState.CONFIRMED,
        )

        self.assertEqual(
            organization_claim_eligibility_reason(
                classification=classification,
                organization=self.student_publication,
            ),
            NEEDS_INSTITUTION_IDENTITY,
        )

    def test_uncertain_campus_claim_needs_institution_identity(self):
        _claim, classification, _assignment = self._make_claim(
            suffix="uncertain-campus",
            campus_state=ClaimInvestigationClassification.CampusContextState.UNCERTAIN,
        )

        self.assertEqual(
            organization_claim_eligibility_reason(
                classification=classification,
                organization=self.student_publication,
            ),
            NEEDS_INSTITUTION_IDENTITY,
        )

    def test_generic_claim_is_outside_student_publication_scope_even_with_specialization(self):
        self.student_publication.verification_specializations = ["SCIENCE"]
        self.student_publication.save(update_fields=["verification_specializations"])
        _claim, classification, _assignment = self._make_claim(
            suffix="national-science",
            campus_state=(
                ClaimInvestigationClassification.CampusContextState.NOT_APPLICABLE
            ),
        )

        self.assertEqual(
            organization_claim_eligibility_reason(
                classification=classification,
                organization=self.student_publication,
            ),
            OUTSIDE_INSTITUTION_SCOPE,
        )

    def test_pending_or_rejected_affiliation_never_authorizes(self):
        for affiliation_status in (
            OrganizationInstitutionAffiliation.VerificationStatus.PENDING,
            OrganizationInstitutionAffiliation.VerificationStatus.REJECTED,
        ):
            with self.subTest(affiliation_status=affiliation_status):
                self._set_affiliation(status=affiliation_status)
                _claim, classification, _assignment = self._make_claim(
                    suffix=f"affiliation-{affiliation_status.lower()}",
                    campus_state=(
                        ClaimInvestigationClassification.CampusContextState.CONFIRMED
                    ),
                    institutions=(self.institution_a,),
                )
                self.assertEqual(
                    organization_claim_eligibility_reason(
                        classification=classification,
                        organization=self.student_publication,
                    ),
                    INSTITUTION_AFFILIATION_NOT_VERIFIED,
                )

    def test_inactive_affiliated_institution_never_authorizes(self):
        self.institution_a.is_active = False
        self.institution_a.save(update_fields=["is_active"])
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Existing claim identity whose institution later became inactive.",
        )
        classification = ClaimInvestigationClassification.objects.create(
            claim=claim,
            domains=["SCIENCE"],
            primary_subject="SCIENCE",
            campus_context_state=(
                ClaimInvestigationClassification.CampusContextState.CONFIRMED
            ),
            rationale="Reviewed subject classification.",
        )

        self.assertEqual(
            organization_claim_eligibility_reason(
                classification=classification,
                organization=self.student_publication,
            ),
            INSTITUTION_AFFILIATION_NOT_VERIFIED,
        )

    def test_multi_institution_claim_matches_either_affiliated_publication(self):
        _claim, classification, _assignment = self._make_claim(
            suffix="multi-institution",
            campus_state=ClaimInvestigationClassification.CampusContextState.CONFIRMED,
            institutions=(self.institution_a, self.institution_b),
        )

        self.assertIsNone(
            organization_claim_eligibility_reason(
                classification=classification,
                organization=self.student_publication,
            )
        )

    def test_ordinary_partner_remains_subject_authorized_regardless_of_campus_identity(self):
        _claim, classification, _assignment = self._make_claim(
            suffix="ordinary-partner-campus-claim",
            campus_state=ClaimInvestigationClassification.CampusContextState.CONFIRMED,
            institutions=(self.institution_b,),
        )

        self.assertIsNone(
            organization_claim_eligibility_reason(
                classification=classification,
                organization=self.ordinary_partner,
            )
        )

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="enforce")
    def test_direct_claim_accepts_matching_student_publication(self):
        _claim, _classification, assignment = self._make_claim(
            suffix="direct-match",
            campus_state=ClaimInvestigationClassification.CampusContextState.CONFIRMED,
            institutions=(self.institution_a,),
            domains=("HEALTH",),
        )

        claimed = claim_verification_assignment(
            assignment=assignment,
            organization=self.student_publication,
            actor=self.student_lead,
        )

        self.assertEqual(claimed.organization_id, self.student_publication.id)

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="enforce")
    def test_direct_claim_rejects_manual_assignment_id_bypass(self):
        _claim, _classification, assignment = self._make_claim(
            suffix="direct-mismatch",
            campus_state=ClaimInvestigationClassification.CampusContextState.CONFIRMED,
            institutions=(self.institution_b,),
        )

        with self.assertRaises(VerificationAssignmentAuthorizationError):
            claim_verification_assignment(
                assignment=assignment,
                organization=self.student_publication,
                actor=self.student_lead,
            )

        assignment.refresh_from_db()
        self.assertIsNone(assignment.organization_id)

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="enforce")
    def test_intake_visibility_uses_same_institution_policy(self):
        own = self._make_claim(
            suffix="intake-own",
            campus_state=ClaimInvestigationClassification.CampusContextState.CONFIRMED,
            institutions=(self.institution_a,),
            domains=("HEALTH",),
        )
        other = self._make_claim(
            suffix="intake-other",
            campus_state=ClaimInvestigationClassification.CampusContextState.CONFIRMED,
            institutions=(self.institution_b,),
        )
        generic = self._make_claim(
            suffix="intake-generic",
            campus_state=(
                ClaimInvestigationClassification.CampusContextState.NOT_APPLICABLE
            ),
        )
        unresolved = self._make_claim(
            suffix="intake-unresolved",
            campus_state=ClaimInvestigationClassification.CampusContextState.CONFIRMED,
        )

        response = self.student_client.get(
            reverse("verification_intake"),
            {"organization_id": str(self.student_publication.id)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["id"],
            str(own[2].id),
        )
        returned = {item["id"] for item in response.data["results"]}
        self.assertNotIn(str(other[2].id), returned)
        self.assertNotIn(str(generic[2].id), returned)
        self.assertNotIn(str(unresolved[2].id), returned)

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="off")
    def test_off_mode_preserves_pre_routing_student_publication_access(self):
        _claim, _classification, assignment = self._make_claim(
            suffix="off-mode-generic",
            campus_state=(
                ClaimInvestigationClassification.CampusContextState.NOT_APPLICABLE
            ),
        )

        claimed = claim_verification_assignment(
            assignment=assignment,
            organization=self.student_publication,
            actor=self.student_lead,
        )

        self.assertEqual(claimed.organization_id, self.student_publication.id)

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="shadow")
    def test_shadow_mode_preserves_pre_routing_student_publication_intake(self):
        _claim, _classification, assignment = self._make_claim(
            suffix="shadow-mode-generic",
            campus_state=(
                ClaimInvestigationClassification.CampusContextState.NOT_APPLICABLE
            ),
        )

        response = self.student_client.get(
            reverse("verification_intake"),
            {"organization_id": str(self.student_publication.id)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            str(assignment.id),
            {item["id"] for item in response.data["results"]},
        )
