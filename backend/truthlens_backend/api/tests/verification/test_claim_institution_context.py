from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.models import (
    AccountabilityEvent,
    Claim,
    ClaimInstitutionAssociation,
    ClaimInvestigationClassification,
    Institution,
)


class ClaimInstitutionContextTests(TestCase):
    def setUp(self):
        self.platform_admin = User.objects.create_superuser(
            username="claim-campus-platform-admin",
            email="claim-campus-admin@example.test",
            password="test-password",
        )
        self.ordinary_user = User.objects.create_user(
            username="claim-campus-user",
            password="test-password",
        )
        self.claim = Claim.objects.create(
            context_text="Example University announced a campus policy change."
        )
        self.classification = ClaimInvestigationClassification.objects.create(
            claim=self.claim,
            domains=["EDUCATION"],
            primary_subject="EDUCATION",
            rationale="Reviewed education subject classification.",
        )
        self.first_institution = Institution.objects.create(
            name="Example University",
            slug="example-university-campus-context",
            website="https://example-university.test",
        )
        self.second_institution = Institution.objects.create(
            name="Second University",
            slug="second-university-campus-context",
            website="https://second-university.test",
        )
        self.inactive_institution = Institution.objects.create(
            name="Inactive University",
            slug="inactive-university-campus-context",
            is_active=False,
        )
        self.url = reverse(
            "management_claim_institution_context",
            kwargs={"claim_id": self.claim.id},
        )

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def confirmed_payload(self, institutions=None):
        if institutions is None:
            institutions = [
                {
                    "institution_id": str(self.first_institution.id),
                    "rationale": "The factual proposition explicitly concerns Example University.",
                }
            ]
        return {
            "campus_context_state": (
                ClaimInvestigationClassification.CampusContextState.CONFIRMED
            ),
            "campus_context_rationale": (
                "The factual proposition directly concerns identified universities."
            ),
            "institutions": institutions,
        }

    def test_platform_admin_can_assign_multiple_canonical_institutions(self):
        response = self.client_for(self.platform_admin).put(
            self.url,
            self.confirmed_payload(
                [
                    {
                        "institution_id": str(self.first_institution.id),
                        "rationale": "The claim explicitly names Example University.",
                    },
                    {
                        "institution_id": str(self.second_institution.id),
                        "rationale": "The claim also explicitly names Second University.",
                    },
                ]
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.classification.refresh_from_db()
        self.assertEqual(
            self.classification.campus_context_state,
            ClaimInvestigationClassification.CampusContextState.CONFIRMED,
        )
        self.assertEqual(
            self.classification.campus_context_reviewed_by,
            self.platform_admin,
        )
        self.assertIsNotNone(self.classification.campus_context_reviewed_at)
        self.assertEqual(
            self.classification.institution_associations.count(),
            2,
        )
        self.assertEqual(
            {row["institution"]["id"] for row in response.data["institutions"]},
            {
                str(self.first_institution.id),
                str(self.second_institution.id),
            },
        )

        event = AccountabilityEvent.objects.get(
            action_type=(
                AccountabilityEvent.ActionType.CLAIM_INSTITUTION_CONTEXT_UPDATED
            ),
            resource_id=str(self.claim.id),
        )
        self.assertEqual(
            event.resource_type,
            AccountabilityEvent.ResourceType.CLAIM,
        )
        self.assertEqual(event.actor, self.platform_admin)
        self.assertEqual(
            event.new_state["campus_context_state"],
            ClaimInvestigationClassification.CampusContextState.CONFIRMED,
        )

    def test_confirmed_campus_context_may_have_no_specific_institution(self):
        response = self.client_for(self.platform_admin).put(
            self.url,
            self.confirmed_payload([]),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["institutions"], [])
        self.classification.refresh_from_db()
        self.assertEqual(
            self.classification.campus_context_state,
            ClaimInvestigationClassification.CampusContextState.CONFIRMED,
        )

    def test_non_confirmed_campus_context_rejects_institution_links(self):
        response = self.client_for(self.platform_admin).put(
            self.url,
            {
                "campus_context_state": (
                    ClaimInvestigationClassification.CampusContextState.NOT_APPLICABLE
                ),
                "campus_context_rationale": (
                    "The proposition is city-wide rather than institution-specific."
                ),
                "institutions": [
                    {
                        "institution_id": str(self.first_institution.id),
                        "rationale": "This must not be accepted.",
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.classification.refresh_from_db()
        self.assertIsNone(self.classification.campus_context_state)
        self.assertFalse(
            ClaimInstitutionAssociation.objects.filter(
                classification=self.classification
            ).exists()
        )

    def test_not_applicable_context_without_institutions_is_valid(self):
        response = self.client_for(self.platform_admin).put(
            self.url,
            {
                "campus_context_state": (
                    ClaimInvestigationClassification.CampusContextState.NOT_APPLICABLE
                ),
                "campus_context_rationale": (
                    "The claim concerns a city-wide suspension, not one university."
                ),
                "institutions": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["institutions"], [])
        self.assertEqual(
            response.data["campus_context_state"],
            ClaimInvestigationClassification.CampusContextState.NOT_APPLICABLE,
        )

    def test_replace_operation_removes_stale_institution_links(self):
        client = self.client_for(self.platform_admin)
        first_response = client.put(
            self.url,
            self.confirmed_payload(
                [
                    {
                        "institution_id": str(self.first_institution.id),
                        "rationale": "The claim names Example University.",
                    },
                    {
                        "institution_id": str(self.second_institution.id),
                        "rationale": "The claim names Second University.",
                    },
                ]
            ),
            format="json",
        )
        self.assertEqual(first_response.status_code, status.HTTP_200_OK)

        second_response = client.put(
            self.url,
            self.confirmed_payload(
                [
                    {
                        "institution_id": str(self.second_institution.id),
                        "rationale": "Review confirmed only Second University.",
                    }
                ]
            ),
            format="json",
        )

        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        associations = ClaimInstitutionAssociation.objects.filter(
            classification=self.classification
        )
        self.assertEqual(associations.count(), 1)
        self.assertEqual(
            associations.get().institution,
            self.second_institution,
        )
        self.assertEqual(
            AccountabilityEvent.objects.filter(
                action_type=(
                    AccountabilityEvent.ActionType.CLAIM_INSTITUTION_CONTEXT_UPDATED
                ),
                resource_id=str(self.claim.id),
            ).count(),
            2,
        )

    def test_clearing_to_unassessed_removes_links_and_review_metadata(self):
        client = self.client_for(self.platform_admin)
        self.assertEqual(
            client.put(
                self.url,
                self.confirmed_payload(),
                format="json",
            ).status_code,
            status.HTTP_200_OK,
        )

        response = client.put(
            self.url,
            {
                "campus_context_state": None,
                "campus_context_rationale": "",
                "institutions": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.classification.refresh_from_db()
        self.assertIsNone(self.classification.campus_context_state)
        self.assertEqual(self.classification.campus_context_rationale, "")
        self.assertIsNone(self.classification.campus_context_reviewed_by)
        self.assertIsNone(self.classification.campus_context_reviewed_at)
        self.assertFalse(self.classification.institution_associations.exists())

    def test_duplicate_institution_ids_are_rejected(self):
        response = self.client_for(self.platform_admin).put(
            self.url,
            self.confirmed_payload(
                [
                    {
                        "institution_id": str(self.first_institution.id),
                        "rationale": "First duplicate entry.",
                    },
                    {
                        "institution_id": str(self.first_institution.id),
                        "rationale": "Second duplicate entry.",
                    },
                ]
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(self.classification.institution_associations.exists())

    def test_inactive_institution_is_rejected_atomically(self):
        response = self.client_for(self.platform_admin).put(
            self.url,
            self.confirmed_payload(
                [
                    {
                        "institution_id": str(self.inactive_institution.id),
                        "rationale": "Inactive institutions must not authorize routing.",
                    }
                ]
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.classification.refresh_from_db()
        self.assertIsNone(self.classification.campus_context_state)
        self.assertFalse(self.classification.institution_associations.exists())
        self.assertFalse(
            AccountabilityEvent.objects.filter(
                action_type=(
                    AccountabilityEvent.ActionType.CLAIM_INSTITUTION_CONTEXT_UPDATED
                ),
                resource_id=str(self.claim.id),
            ).exists()
        )

    def test_non_platform_user_cannot_update_context(self):
        response = self.client_for(self.ordinary_user).put(
            self.url,
            self.confirmed_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.classification.refresh_from_db()
        self.assertIsNone(self.classification.campus_context_state)

    def test_claim_without_authoritative_classification_returns_conflict(self):
        unclassified_claim = Claim.objects.create(
            context_text="A claim without authoritative subject classification."
        )
        url = reverse(
            "management_claim_institution_context",
            kwargs={"claim_id": unclassified_claim.id},
        )

        response = self.client_for(self.platform_admin).put(
            url,
            {
                "campus_context_state": (
                    ClaimInvestigationClassification.CampusContextState.CONFIRMED
                ),
                "campus_context_rationale": "Campus relevance is otherwise clear.",
                "institutions": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("no authoritative investigation classification", response.data["detail"])

    def test_association_model_rejects_non_confirmed_classification(self):
        self.classification.campus_context_state = (
            ClaimInvestigationClassification.CampusContextState.UNCERTAIN
        )
        self.classification.save(update_fields=["campus_context_state"])

        with self.assertRaises(ValidationError):
            ClaimInstitutionAssociation.objects.create(
                classification=self.classification,
                institution=self.first_institution,
                rationale="This association is invalid while campus context is uncertain.",
                assigned_by=self.platform_admin,
            )

    def test_get_returns_current_context(self):
        update_response = self.client_for(self.platform_admin).put(
            self.url,
            self.confirmed_payload(),
            format="json",
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)

        response = self.client_for(self.platform_admin).get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["claim_id"], str(self.claim.id))
        self.assertEqual(len(response.data["institutions"]), 1)
        self.assertEqual(
            response.data["institutions"][0]["institution"]["id"],
            str(self.first_institution.id),
        )
