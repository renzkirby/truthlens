import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import call, patch

from django.contrib.auth.models import User
from django.db import connection
from django.test import SimpleTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from api.models import (
    AccountabilityEvent,
    AdjudicationDecision,
    Claim,
    OfficialFactCheck,
    Organization,
    OrganizationMembership,
    UserProfile,
    VerificationAssignment,
)
from api.organization_service import PartnerCapability
from api.verification_current_state_metrics_service import (
    get_organization_verification_current_state,
)
from api.verification_metrics_query_service import (
    VerificationMetricsAuthorizationError,
    VerificationMetricsCompositionError,
    get_organization_verification_metrics,
)
from api.verification_metrics_service import VerificationMetricsIntegrityError
from api.verification_activity_metrics_service import VerificationActivityMetricsIntegrityError
from api.verification_activity_trends_service import VerificationActivityTrendInputError
from api.verification_resolution_metrics_service import VerificationResolutionMetricsIntegrityError
from api.verification_reviewer_participation_metrics_service import (
    VerificationReviewerParticipationMetricsIntegrityError,
)
from api.verification_public_reach_metrics_service import VerificationPublicReachMetricsIntegrityError
from api.verification_knowledge_reuse_metrics_service import VerificationKnowledgeReuseMetricsIntegrityError


BASELINE_PATCH = (
    "api.verification_metrics_query_service.get_organization_verification_baseline"
)
ACTIVITY_PATCH = (
    "api.verification_metrics_query_service.get_organization_verification_activity"
)
TREND_PATCH = (
    "api.verification_metrics_query_service.get_organization_verification_activity_trend"
)
RESOLUTION_PATCH = (
    "api.verification_metrics_query_service.get_organization_verification_resolution_distribution"
)
REVIEWERS_PATCH = (
    "api.verification_metrics_query_service.get_organization_verification_reviewer_participation"
)
PUBLIC_REACH_PATCH = "api.verification_metrics_query_service.get_organization_public_reach_metrics"
KNOWLEDGE_REUSE_PATCH = "api.verification_metrics_query_service.get_organization_knowledge_reuse_metrics"
CURRENT_STATE_PATCH = (
    "api.verification_metrics_query_service."
    "get_organization_verification_current_state"
)


def make_public_reach_payload(organization):
    return {
        "organization_id": str(organization.pk),
        "measurement_basis": {
            "source": "PUBLIC_REACH_EVENT",
            "attribution_source": "SOURCE_ORGANIZATION_ID_SNAPSHOT",
            "publication_identity_source": "FACT_CHECK_ID_SNAPSHOT",
            "coverage": "INSTRUMENTATION_ERA_ONLY",
            "historical_backfill": False,
            "unique_audience_measurement": False,
            "first_observed_interaction_at": None,
            "last_observed_interaction_at": None,
        },
        "observed_interactions": {
            "events": 0,
            "by_type": {"PUBLICATION_VIEW": 0, "PARTNER_PROFILE_VIEW": 0,
                        "EXTENSION_PUBLICATION_IMPRESSION": 0, "EXTENSION_PUBLICATION_CLICK": 0},
            "by_surface": {"PUBLIC_FACT_CHECK_PAGE": 0, "PUBLIC_PARTNER_PROFILE": 0,
                           "EXTENSION_OFFICIAL_FACT_CHECK": 0, "EXTENSION_RELATED_FACT_CHECK": 0},
            "distinct_publications": 0,
        },
        "extension_publications": {
            "impressions": {"official": 0, "related": 0, "total": 0},
            "clicks": {"official": 0, "related": 0, "total": 0},
        },
    }


def make_knowledge_reuse_payload(organization):
    return {
        "organization_id": str(organization.pk),
        "measurement_basis": {
            "source": "KNOWLEDGE_REUSE_EVENT",
            "attribution_source": "SOURCE_ORGANIZATION_ID_SNAPSHOT",
            "target_identity_source": "TARGET_CLAIM_ID_SNAPSHOT",
            "coverage": "ATTRIBUTED_INSTRUMENTATION_ERA_ONLY",
            "historical_backfill": False,
            "historical_unattributed_rows_excluded": True,
            "first_observed_reuse_at": None,
            "last_observed_reuse_at": None,
        },
        "material_reuse": {
            "events": 0, "by_type": {"USER_RESPONSE": 0, "VERIFICATION_CONTEXT": 0},
            "by_match_method": {"EXACT_TEXT": 0, "SEMANTIC": 0, "FULL_TEXT": 0, "CLAIM_CACHE": 0},
            "distinct_publications": 0, "distinct_target_claims": 0,
        },
        "repeat_claim_reuse": {"cached_published_responses": 0, "distinct_cached_claims": 0},
    }


def measurement_section(payload):
    return {key: value for key, value in payload.items() if key != "organization_id"}


def make_current_state_payload(organization):
    return {
        "organization_id": str(organization.pk),
        "measurement_basis": {
            "source": "PERSISTED_OPERATIONAL_RECORDS",
            "coverage": "CURRENT_STATE",
        },
        "published_fact_checks": {"distinct_claims": 2},
        "factual_corrections": {"active_requests": 1},
        "investigations": {"active_assignments": 3},
        "publication_work": {"distinct_claims": 1},
    }


def make_resolution_payload(organization):
    return {
        "organization_id": str(organization.pk),
        "measurement_basis": {
            "source": "ACCOUNTABILITY_EVENT",
            "coverage": "OBSERVED_AUTHORITATIVE_RESOLUTION_EVENTS_ONLY",
            "historical_backfill": False,
            "first_observed_resolution_at": datetime(
                2026, 9, 10, 8, 0, 0, 345678, tzinfo=timezone.utc,
            ),
            "last_observed_resolution_at": datetime(
                2026, 9, 16, 9, 0, 0, 456789, tzinfo=timezone.utc,
            ),
        },
        "latest_observed_resolutions": {
            "count": 4, "by_verdict": {"FACT": 1, "FAKE": 2, "MISLEADING": 1, "SATIRE": 0},
        },
    }


def make_reviewer_participation_payload(organization):
    return {
        "organization_id": str(organization.pk),
        "measurement_basis": {
            "source": "ACCOUNTABILITY_EVENT",
            "identity_source": "ACTOR_ID_SNAPSHOT",
            "coverage": "DURABLE_ACTOR_ID_SNAPSHOT_EVENTS_ONLY",
            "historical_backfill": False,
            "first_observed_participation_at": datetime(
                2026, 9, 16, 10, 0, 0, 567890, tzinfo=timezone.utc,
            ),
            "last_observed_participation_at": datetime(
                2026, 9, 16, 11, 0, 0, 678901, tzinfo=timezone.utc,
            ),
        },
        "reviewer_participation": {
            "unique_reviewers": 3, "by_stage": {"evidence_review": 2, "adjudication": 2},
        },
    }


class VerificationMetricsApiTests(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Metrics Partner",
            slug="metrics-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.other_organization = Organization.objects.create(
            name="Other Metrics Partner",
            slug="other-metrics-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.members = {}
        for role in (
            OrganizationMembership.Role.OWNER,
            OrganizationMembership.Role.ADMIN,
            OrganizationMembership.Role.LEAD_VERIFIER,
            OrganizationMembership.Role.CONTRIBUTOR,
            OrganizationMembership.Role.RESEARCHER,
            OrganizationMembership.Role.MODERATOR,
        ):
            actor = User.objects.create_user(username=f"metrics-{role.lower()}")
            OrganizationMembership.objects.create(
                organization=self.organization,
                user=actor,
                role=role,
                status=OrganizationMembership.Status.ACTIVE,
            )
            self.members[role] = actor
        self.outsider = User.objects.create_user(username="metrics-outsider")
        self.safety_moderator = User.objects.create_user(username="metrics-safety-mod")
        self.safety_moderator.profile.role = UserProfile.Role.MOD
        self.safety_moderator.profile.save(update_fields=["role"])
        self.url = self.metrics_url(self.organization.pk)
        self.baseline = {
            "organization_id": str(self.organization.pk),
            "measurement_basis": {
                "source": "ACCOUNTABILITY_EVENT",
                "coverage": "INSTRUMENTATION_ERA_ONLY",
                "historical_backfill": False,
                "first_observed_claimed_at": datetime(
                    2026, 9, 15, 8, 0, 0, 123456, tzinfo=timezone.utc,
                ),
                "last_observed_claimed_at": datetime(
                    2026, 9, 15, 9, 0, 0, 654321, tzinfo=timezone.utc,
                ),
            },
            "attempts": {
                "claimed": 5, "active": 2, "released": 1, "completed": 2, "terminal": 3,
            },
            "reliability": {
                "terminal_completion_rate": 2 / 3,
                "terminal_release_rate": 1 / 3,
            },
            "completed_turnaround": {
                "count": 2,
                "average_seconds": 5.9375,
                "median_seconds": 5.9375,
                "minimum_seconds": 1.625,
                "maximum_seconds": 10.25,
            },
        }
        self.activity_payload = {
            "organization_id": str(self.organization.pk),
            "measurement_basis": {
                "source": "ACCOUNTABILITY_EVENT",
                "coverage": "INSTRUMENTATION_ERA_ONLY",
                "historical_backfill": False,
                "first_observed_activity_at": datetime(
                    2026, 9, 15, 10, 0, 0, 234567, tzinfo=timezone.utc,
                ),
                "last_observed_activity_at": datetime(
                    2026, 9, 15, 11, 0, 0, 765432, tzinfo=timezone.utc,
                ),
            },
            "evidence_review": {"decisions": 7, "verified": 3, "rejected": 4},
            "adjudication": {"started": 2, "verdicts_issued": 1},
            "publication": {"initial_published": 1},
        }
        self.resolution_payload = make_resolution_payload(self.organization)
        self.reviewer_participation_payload = make_reviewer_participation_payload(self.organization)
        self.public_reach_payload = make_public_reach_payload(self.organization)
        self.knowledge_reuse_payload = make_knowledge_reuse_payload(self.organization)
        self.current_state_payload = make_current_state_payload(self.organization)
        self.public_reach = self.enterContext(patch(PUBLIC_REACH_PATCH, return_value=self.public_reach_payload))
        self.knowledge_reuse = self.enterContext(patch(KNOWLEDGE_REUSE_PATCH, return_value=self.knowledge_reuse_payload))
        self.current_state = self.enterContext(
            patch(CURRENT_STATE_PATCH, return_value=self.current_state_payload)
        )
        # Default trusted mocks keep existing transport cases independent of raw history.
        resolution_patch = patch(RESOLUTION_PATCH, return_value=self.resolution_payload)
        self.resolution = resolution_patch.start()
        self.addCleanup(resolution_patch.stop)
        reviewers_patch = patch(REVIEWERS_PATCH, return_value=self.reviewer_participation_payload)
        self.reviewers = reviewers_patch.start()
        self.addCleanup(reviewers_patch.stop)
        # Windowed fixture activity differs from the earlier full-history summaries.
        self.created_after = datetime(2026, 9, 20, 10, tzinfo=timezone.utc)
        self.created_before = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
        self.window = {
            "created_after": "2026-09-20T10:00:00Z",
            "created_before": "2026-09-22T12:00:00Z",
        }
        totals = {
            "assignment": {"claimed": 1, "released": 0, "completed": 0},
            "evidence_review": {"decisions": 1, "verified": 1, "rejected": 0},
            "adjudication": {"started": 0, "verdicts_issued": 0},
            "publication": {"initial_published": 0},
        }
        zeros = {section: dict.fromkeys(fields, 0) for section, fields in totals.items()}
        self.trend_payload = {
            "organization_id": str(self.organization.pk),
            "measurement_basis": {
                "source": "ACCOUNTABILITY_EVENT",
                "coverage": "INSTRUMENTATION_ERA_ONLY",
                "historical_backfill": False,
                "granularity": "DAY",
                "bucket_timezone": "UTC",
                "created_after": self.created_after,
                "created_before": self.created_before,
            },
            "totals": totals,
            "daily": [
                {"date": "2026-09-20", **deepcopy(totals)},
                {"date": "2026-09-21", **deepcopy(zeros)},
                {"date": "2026-09-22", **deepcopy(zeros)},
            ],
        }

    def expected_payload(self):
        return {
            **self.baseline,
            "activity": {
                "measurement_basis": self.activity_payload["measurement_basis"],
                "evidence_review": self.activity_payload["evidence_review"],
                "adjudication": self.activity_payload["adjudication"],
                "publication": self.activity_payload["publication"],
            },
            "resolution_distribution": {
                "measurement_basis": self.resolution_payload["measurement_basis"],
                "latest_observed_resolutions": self.resolution_payload["latest_observed_resolutions"],
            },
            "reviewer_participation": {
                "measurement_basis": self.reviewer_participation_payload["measurement_basis"],
                **self.reviewer_participation_payload["reviewer_participation"],
            },
            "public_reach": measurement_section(self.public_reach_payload),
            "knowledge_reuse": measurement_section(self.knowledge_reuse_payload),
            "current_state": measurement_section(self.current_state_payload),
        }

    def metrics_url(self, organization_id):
        return reverse(
            "organization_verification_metrics",
            kwargs={"organization_id": organization_id},
        )

    def request_metrics(self, actor, *, url=None, params=None):
        client = APIClient()
        client.force_authenticate(user=actor)
        return client.get(self.url if url is None else url, data=params or {})

    def assert_allowed(self, actor):
        original_baseline = deepcopy(self.baseline)
        original_activity = deepcopy(self.activity_payload)
        original_resolution = deepcopy(self.resolution_payload)
        original_reviewers = deepcopy(self.reviewer_participation_payload)
        original_reach = deepcopy(self.public_reach_payload)
        original_reuse = deepcopy(self.knowledge_reuse_payload)
        original_current_state = deepcopy(self.current_state_payload)
        with (
            patch(BASELINE_PATCH, return_value=self.baseline) as baseline,
            patch(ACTIVITY_PATCH, return_value=self.activity_payload) as activity,
            patch(RESOLUTION_PATCH, return_value=self.resolution_payload) as resolution,
            patch(REVIEWERS_PATCH, return_value=self.reviewer_participation_payload) as reviewers,
            patch(PUBLIC_REACH_PATCH, return_value=self.public_reach_payload) as reach,
            patch(KNOWLEDGE_REUSE_PATCH, return_value=self.knowledge_reuse_payload) as reuse,
            patch(CURRENT_STATE_PATCH, return_value=self.current_state_payload) as current_state,
            patch(TREND_PATCH) as trend,
        ):
            response = self.request_metrics(actor)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, self.expected_payload())
        self.assertIsNot(response.data, self.baseline)
        self.assertIsNot(response.data["activity"], self.activity_payload)
        self.assertEqual(self.baseline, original_baseline)
        self.assertEqual(self.activity_payload, original_activity)
        self.assertEqual(self.resolution_payload, original_resolution)
        self.assertEqual(self.reviewer_participation_payload, original_reviewers)
        self.assertEqual(self.public_reach_payload, original_reach)
        self.assertEqual(self.knowledge_reuse_payload, original_reuse)
        self.assertEqual(self.current_state_payload, original_current_state)
        self.assertIsNot(response.data["resolution_distribution"], self.resolution_payload)
        self.assertIsNot(response.data["reviewer_participation"], self.reviewer_participation_payload)
        self.assertIsNot(response.data["reviewer_participation"],
                         self.reviewer_participation_payload["reviewer_participation"])
        self.assertEqual(set(response.data), {
            "organization_id", "measurement_basis", "attempts", "reliability",
            "completed_turnaround", "activity", "resolution_distribution", "reviewer_participation",
            "public_reach", "knowledge_reuse", "current_state",
        })
        self.assertEqual(set(response.data["activity"]), {
            "measurement_basis", "evidence_review", "adjudication", "publication",
        })
        self.assertEqual(set(response.data["resolution_distribution"]), {
            "measurement_basis", "latest_observed_resolutions",
        })
        self.assertEqual(set(response.data["reviewer_participation"]), {
            "measurement_basis", "unique_reviewers", "by_stage",
        })
        self.assertEqual(set(response.data["public_reach"]), {
            "measurement_basis", "observed_interactions", "extension_publications",
        })
        self.assertEqual(set(response.data["knowledge_reuse"]), {
            "measurement_basis", "material_reuse", "repeat_claim_reuse",
        })
        self.assertEqual(set(response.data["current_state"]), {
            "measurement_basis", "published_fact_checks", "factual_corrections",
            "investigations", "publication_work",
        })
        self.assertIsNot(response.data["public_reach"], self.public_reach_payload)
        self.assertIsNot(response.data["knowledge_reuse"], self.knowledge_reuse_payload)
        self.assertIsNot(response.data["current_state"], self.current_state_payload)
        self.assertEqual(response.data["resolution_distribution"]["measurement_basis"],
                         original_resolution["measurement_basis"])
        self.assertEqual(response.data["reviewer_participation"]["measurement_basis"],
                         original_reviewers["measurement_basis"])
        for key, value in self.baseline.items():
            self.assertEqual(response.data[key], value)
        self.assertEqual(response.data["activity"]["measurement_basis"],
                         original_activity["measurement_basis"])
        baseline.assert_called_once_with(organization=self.organization)
        activity.assert_called_once_with(organization=self.organization)
        resolution.assert_called_once_with(organization=self.organization)
        reviewers.assert_called_once_with(organization=self.organization)
        reach.assert_called_once_with(organization=self.organization)
        reuse.assert_called_once_with(organization=self.organization)
        current_state.assert_called_once_with(organization=self.organization)
        trend.assert_not_called()
        return response

    def assert_forbidden(self, actor, *, url=None, params=None):
        with (
            patch(BASELINE_PATCH) as baseline,
            patch(ACTIVITY_PATCH) as activity,
            patch(RESOLUTION_PATCH) as resolution,
            patch(REVIEWERS_PATCH) as reviewers,
            patch(PUBLIC_REACH_PATCH) as reach,
            patch(KNOWLEDGE_REUSE_PATCH) as reuse,
            patch(CURRENT_STATE_PATCH) as current_state,
            patch(TREND_PATCH) as trend,
        ):
            response = self.request_metrics(actor, url=url, params=params)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(set(response.data), {"detail"})
        baseline.assert_not_called()
        activity.assert_not_called()
        resolution.assert_not_called()
        reviewers.assert_not_called()
        reach.assert_not_called()
        reuse.assert_not_called()
        current_state.assert_not_called()
        trend.assert_not_called()

    def test_unauthenticated_request_returns_401(self):
        for params in ({}, self.window):
            with (
                self.subTest(params=params),
                patch(BASELINE_PATCH) as baseline,
                patch(ACTIVITY_PATCH) as activity,
                patch(TREND_PATCH) as trend,
            ):
                response = APIClient().get(self.url, data=params)
                self.assertEqual(response.status_code, 401)
                baseline.assert_not_called()
                activity.assert_not_called()
                self.resolution.assert_not_called()
                self.reviewers.assert_not_called()
                self.public_reach.assert_not_called()
                self.knowledge_reuse.assert_not_called()
                self.current_state.assert_not_called()
                trend.assert_not_called()

    def test_owner_can_read_metrics(self):
        self.assert_allowed(self.members[OrganizationMembership.Role.OWNER])

    def test_admin_can_read_metrics(self):
        self.assert_allowed(self.members[OrganizationMembership.Role.ADMIN])

    def test_lead_verifier_can_read_metrics(self):
        self.assert_allowed(self.members[OrganizationMembership.Role.LEAD_VERIFIER])

    def test_contributor_is_forbidden(self):
        self.assert_forbidden(self.members[OrganizationMembership.Role.CONTRIBUTOR])

    def test_researcher_is_forbidden(self):
        self.assert_forbidden(self.members[OrganizationMembership.Role.RESEARCHER])

    def test_organization_moderator_is_forbidden(self):
        self.assert_forbidden(self.members[OrganizationMembership.Role.MODERATOR])

    def test_platform_safety_moderator_is_forbidden(self):
        self.assert_forbidden(self.safety_moderator)

    def test_outsider_is_forbidden(self):
        self.assert_forbidden(self.outsider)

    def assert_inactive_memberships_forbidden(self, membership_status, *, params=None):
        for role in (
            OrganizationMembership.Role.OWNER,
            OrganizationMembership.Role.ADMIN,
            OrganizationMembership.Role.LEAD_VERIFIER,
        ):
            with self.subTest(role=role):
                actor = self.members[role]
                membership = OrganizationMembership.objects.get(
                    organization=self.organization, user=actor,
                )
                membership.status = membership_status
                membership.save(update_fields=["status"])
                self.assert_forbidden(actor, params=params)

    def test_suspended_membership_is_forbidden(self):
        self.assert_inactive_memberships_forbidden(OrganizationMembership.Status.SUSPENDED)

    def test_left_membership_is_forbidden(self):
        self.assert_inactive_memberships_forbidden(OrganizationMembership.Status.LEFT)

    def test_qualifying_capabilities_do_not_cross_organizations(self):
        for role in (
            OrganizationMembership.Role.OWNER,
            OrganizationMembership.Role.ADMIN,
            OrganizationMembership.Role.LEAD_VERIFIER,
        ):
            with self.subTest(role=role):
                actor = self.members[role]
                OrganizationMembership.objects.create(
                    organization=self.other_organization,
                    user=actor,
                    role=OrganizationMembership.Role.CONTRIBUTOR,
                    status=OrganizationMembership.Status.ACTIVE,
                )
                self.assert_allowed(actor)
                self.assert_forbidden(
                    actor, url=self.metrics_url(self.other_organization.pk),
                )

    def test_unknown_organization_returns_404(self):
        with (
            patch(BASELINE_PATCH) as baseline,
            patch(ACTIVITY_PATCH) as activity,
            patch(TREND_PATCH) as trend,
        ):
            response = self.request_metrics(
                self.members[OrganizationMembership.Role.OWNER],
                url=self.metrics_url(uuid.uuid4()),
            )
        self.assertEqual(response.status_code, 404)
        baseline.assert_not_called()
        activity.assert_not_called()
        self.resolution.assert_not_called()
        self.reviewers.assert_not_called()
        self.public_reach.assert_not_called()
        self.knowledge_reuse.assert_not_called()
        self.current_state.assert_not_called()
        trend.assert_not_called()

    def test_success_preserves_baseline_and_activity_coverage_on_the_wire(self):
        response = self.assert_allowed(self.members[OrganizationMembership.Role.OWNER])
        expected = {
            **self.expected_payload(),
            "measurement_basis": {
                **self.baseline["measurement_basis"],
                "first_observed_claimed_at": "2026-09-15T08:00:00.123456Z",
                "last_observed_claimed_at": "2026-09-15T09:00:00.654321Z",
            },
            "activity": {
                **self.expected_payload()["activity"],
                "measurement_basis": {
                    **self.activity_payload["measurement_basis"],
                    "first_observed_activity_at": "2026-09-15T10:00:00.234567Z",
                    "last_observed_activity_at": "2026-09-15T11:00:00.765432Z",
                },
            },
            "resolution_distribution": {
                **self.expected_payload()["resolution_distribution"],
                "measurement_basis": {
                    **self.resolution_payload["measurement_basis"],
                    "first_observed_resolution_at": "2026-09-10T08:00:00.345678Z",
                    "last_observed_resolution_at": "2026-09-16T09:00:00.456789Z",
                },
            },
            "reviewer_participation": {
                **self.expected_payload()["reviewer_participation"],
                "measurement_basis": {
                    **self.reviewer_participation_payload["measurement_basis"],
                    "first_observed_participation_at": "2026-09-16T10:00:00.567890Z",
                    "last_observed_participation_at": "2026-09-16T11:00:00.678901Z",
                },
            },
        }
        self.assertEqual(response.json(), expected)

    def test_empty_baseline_and_activity_preserve_zero_counts_and_nulls(self):
        self.baseline["measurement_basis"]["first_observed_claimed_at"] = None
        self.baseline["measurement_basis"]["last_observed_claimed_at"] = None
        self.baseline["attempts"] = dict.fromkeys(self.baseline["attempts"], 0)
        self.baseline["reliability"] = dict.fromkeys(self.baseline["reliability"])
        self.baseline["completed_turnaround"] = {
            "count": 0,
            "average_seconds": None,
            "median_seconds": None,
            "minimum_seconds": None,
            "maximum_seconds": None,
        }
        self.activity_payload["measurement_basis"]["first_observed_activity_at"] = None
        self.activity_payload["measurement_basis"]["last_observed_activity_at"] = None
        self.activity_payload["evidence_review"] = {"decisions": 0, "verified": 0, "rejected": 0}
        self.activity_payload["adjudication"] = {"started": 0, "verdicts_issued": 0}
        self.activity_payload["publication"] = {"initial_published": 0}
        for field in ("first_observed_resolution_at", "last_observed_resolution_at"):
            self.resolution_payload["measurement_basis"][field] = None
        self.resolution_payload["latest_observed_resolutions"] = {
            "count": 0, "by_verdict": {"FACT": 0, "FAKE": 0, "MISLEADING": 0, "SATIRE": 0},
        }
        for field in ("first_observed_participation_at", "last_observed_participation_at"):
            self.reviewer_participation_payload["measurement_basis"][field] = None
        self.reviewer_participation_payload["reviewer_participation"] = {
            "unique_reviewers": 0, "by_stage": {"evidence_review": 0, "adjudication": 0},
        }
        response = self.assert_allowed(self.members[OrganizationMembership.Role.ADMIN])
        self.assertEqual(response.json(), self.expected_payload())

    def test_integrity_error_returns_generic_503_without_partial_metrics(self):
        error = VerificationMetricsIntegrityError(
            "Assignment internal-assignment-id has malformed event details."
        )
        with (
            patch(BASELINE_PATCH, side_effect=error) as baseline,
            patch(ACTIVITY_PATCH, return_value=self.activity_payload) as activity,
            patch("api.views.logger.exception") as log_exception,
        ):
            response = self.request_metrics(self.members[OrganizationMembership.Role.OWNER])
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {
            "detail": "Verification metrics are temporarily unavailable.",
        })
        self.assertNotIn(str(error), response.content.decode())
        baseline.assert_called_once_with(organization=self.organization)
        activity.assert_not_called()
        log_exception.assert_called_once_with(
            "Organization verification metrics projection failed."
        )
        self.public_reach.assert_not_called()
        self.knowledge_reuse.assert_not_called()
        self.current_state.assert_not_called()

    def assert_generic_unavailable(self, response, log_exception):
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {
            "detail": "Verification metrics are temporarily unavailable.",
        })
        log_exception.assert_called_once_with(
            "Organization verification metrics projection failed."
        )

    def test_activity_integrity_error_returns_503_without_valid_baseline(self):
        error = VerificationActivityMetricsIntegrityError(
            "Claim internal-claim-id has duplicate history at internal-event-id."
        )
        with (
            patch(BASELINE_PATCH, return_value=self.baseline) as baseline,
            patch(ACTIVITY_PATCH, side_effect=error) as activity,
            patch("api.views.logger.exception") as log_exception,
        ):
            response = self.request_metrics(self.members[OrganizationMembership.Role.OWNER])
        self.assert_generic_unavailable(response, log_exception)
        self.assertNotIn(str(error), response.content.decode())
        baseline.assert_called_once_with(organization=self.organization)
        activity.assert_called_once_with(organization=self.organization)
        self.public_reach.assert_not_called()
        self.knowledge_reuse.assert_not_called()
        self.current_state.assert_not_called()

    def test_composition_error_returns_generic_503_without_partial_metrics(self):
        error = VerificationMetricsCompositionError("Internal identity details.")
        with (
            patch("api.views.get_organization_verification_metrics", side_effect=error),
            patch("api.views.logger.exception") as log_exception,
        ):
            response = self.request_metrics(self.members[OrganizationMembership.Role.OWNER])
        self.assert_generic_unavailable(response, log_exception)
        self.assertNotIn(str(error), response.content.decode())
        self.public_reach.assert_not_called()
        self.knowledge_reuse.assert_not_called()
        self.current_state.assert_not_called()

    def test_missing_or_mismatched_service_identities_return_generic_503(self):
        for service in (
            "baseline", "activity", "resolution", "reviewers", "reach", "reuse", "current",
        ):
            for identity in (None, str(self.other_organization.pk)):
                with self.subTest(service=service, identity=identity):
                    baseline_payload = deepcopy(self.baseline)
                    activity_payload = deepcopy(self.activity_payload)
                    resolution_payload = deepcopy(self.resolution_payload)
                    reviewer_payload = deepcopy(self.reviewer_participation_payload)
                    reach_payload = deepcopy(self.public_reach_payload)
                    reuse_payload = deepcopy(self.knowledge_reuse_payload)
                    current_payload = deepcopy(self.current_state_payload)
                    malformed = {
                        "baseline": baseline_payload, "activity": activity_payload,
                        "resolution": resolution_payload, "reviewers": reviewer_payload,
                        "reach": reach_payload, "reuse": reuse_payload,
                        "current": current_payload,
                    }[service]
                    if identity is None:
                        del malformed["organization_id"]
                    else:
                        malformed["organization_id"] = identity
                    with (
                        patch(BASELINE_PATCH, return_value=baseline_payload) as baseline,
                        patch(ACTIVITY_PATCH, return_value=activity_payload) as activity,
                        patch(RESOLUTION_PATCH, return_value=resolution_payload) as resolution,
                        patch(REVIEWERS_PATCH, return_value=reviewer_payload) as reviewers,
                        patch(PUBLIC_REACH_PATCH, return_value=reach_payload) as reach,
                        patch(KNOWLEDGE_REUSE_PATCH, return_value=reuse_payload) as reuse,
                        patch(CURRENT_STATE_PATCH, return_value=current_payload) as current_state,
                        patch(TREND_PATCH) as trend,
                        patch("api.views.logger.exception") as log_exception,
                    ):
                        response = self.request_metrics(
                            self.members[OrganizationMembership.Role.OWNER],
                        )
                    self.assert_generic_unavailable(response, log_exception)
                    baseline.assert_called_once_with(organization=self.organization)
                    activity.assert_called_once_with(organization=self.organization)
                    resolution.assert_called_once_with(organization=self.organization)
                    reviewers.assert_called_once_with(organization=self.organization)
                    reach.assert_called_once_with(organization=self.organization)
                    reuse.assert_called_once_with(organization=self.organization)
                    current_state.assert_called_once_with(organization=self.organization)
                    trend.assert_not_called()


    def assert_window_allowed(self, actor, *, params=None, after=None, before=None):
        after = self.created_after if after is None else after
        before = self.created_before if before is None else before
        payload = deepcopy(self.trend_payload)
        payload["measurement_basis"].update(created_after=after, created_before=before)
        original_trend = deepcopy(payload)
        original_baseline = deepcopy(self.baseline)
        original_activity = deepcopy(self.activity_payload)
        original_resolution = deepcopy(self.resolution_payload)
        original_reviewers = deepcopy(self.reviewer_participation_payload)
        original_reach = deepcopy(self.public_reach_payload)
        original_reuse = deepcopy(self.knowledge_reuse_payload)
        original_current_state = deepcopy(self.current_state_payload)
        with (
            patch(BASELINE_PATCH, return_value=self.baseline) as baseline,
            patch(ACTIVITY_PATCH, return_value=self.activity_payload) as activity,
            patch(RESOLUTION_PATCH, return_value=self.resolution_payload) as resolution,
            patch(REVIEWERS_PATCH, return_value=self.reviewer_participation_payload) as reviewers,
            patch(PUBLIC_REACH_PATCH, return_value=self.public_reach_payload) as reach,
            patch(KNOWLEDGE_REUSE_PATCH, return_value=self.knowledge_reuse_payload) as reuse,
            patch(CURRENT_STATE_PATCH, return_value=self.current_state_payload) as current_state,
            patch(TREND_PATCH, return_value=payload) as trend,
        ):
            response = self.request_metrics(actor, params=self.window if params is None else params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {
            "organization_id", "measurement_basis", "attempts", "reliability",
            "completed_turnaround", "activity", "resolution_distribution", "reviewer_participation",
            "public_reach", "knowledge_reuse", "current_state", "trend",
        })
        for key, value in self.expected_payload().items():
            self.assertEqual(response.data[key], value)
        self.assertEqual(response.data["trend"], {
            "measurement_basis": original_trend["measurement_basis"],
            "totals": original_trend["totals"],
            "daily": original_trend["daily"],
        })
        self.assertEqual(set(response.data["trend"]), {"measurement_basis", "totals", "daily"})
        self.assertIsNot(response.data["trend"], payload)
        self.assertEqual(payload, original_trend)
        self.assertEqual(self.baseline, original_baseline)
        self.assertEqual(self.activity_payload, original_activity)
        self.assertEqual(self.resolution_payload, original_resolution)
        self.assertEqual(self.reviewer_participation_payload, original_reviewers)
        self.assertEqual(self.public_reach_payload, original_reach)
        self.assertEqual(self.knowledge_reuse_payload, original_reuse)
        self.assertEqual(self.current_state_payload, original_current_state)
        baseline.assert_called_once_with(organization=self.organization)
        activity.assert_called_once_with(organization=self.organization)
        resolution.assert_called_once_with(organization=self.organization)
        reviewers.assert_called_once_with(organization=self.organization)
        reach.assert_called_once_with(organization=self.organization)
        reuse.assert_called_once_with(organization=self.organization)
        current_state.assert_called_once_with(organization=self.organization)
        trend.assert_called_once_with(
            organization=self.organization, created_after=after, created_before=before,
        )
        self.assertIs(trend.call_args.kwargs["created_after"].tzinfo, timezone.utc)
        self.assertIs(trend.call_args.kwargs["created_before"].tzinfo, timezone.utc)
        return response

    def assert_invalid_query(self, params):
        with (
            patch(BASELINE_PATCH) as baseline,
            patch(ACTIVITY_PATCH) as activity,
            patch(RESOLUTION_PATCH) as resolution,
            patch(REVIEWERS_PATCH) as reviewers,
            patch(PUBLIC_REACH_PATCH) as reach,
            patch(KNOWLEDGE_REUSE_PATCH) as reuse,
            patch(CURRENT_STATE_PATCH) as current_state,
            patch(TREND_PATCH) as trend,
        ):
            response = self.request_metrics(self.members[OrganizationMembership.Role.OWNER], params=params)
        self.assertEqual(response.status_code, 400)
        baseline.assert_not_called()
        activity.assert_not_called()
        resolution.assert_not_called()
        reviewers.assert_not_called()
        reach.assert_not_called()
        reuse.assert_not_called()
        current_state.assert_not_called()
        trend.assert_not_called()
        return response

    def test_owner_window_adds_only_trend_and_preserves_full_history_summaries(self):
        self.assert_window_allowed(self.members[OrganizationMembership.Role.OWNER])

    def test_admin_with_valid_window_is_allowed(self):
        self.assert_window_allowed(self.members[OrganizationMembership.Role.ADMIN])

    def test_lead_verifier_with_valid_window_is_allowed(self):
        self.assert_window_allowed(self.members[OrganizationMembership.Role.LEAD_VERIFIER])

    def test_explicit_offsets_are_accepted_and_passed_downstream_as_utc(self):
        self.assert_window_allowed(self.members[OrganizationMembership.Role.OWNER], params={
            "created_after": "2026-09-20T18:00:00+08:00",
            "created_before": "2026-09-22T07:00:00-05:00",
        })

    def test_each_timezone_naive_boundary_is_rejected(self):
        for boundary, value in (
            ("created_after", "2026-09-20T10:00:00"),
            ("created_before", "2026-09-22T12:00:00"),
        ):
            with self.subTest(boundary=boundary):
                self.assert_invalid_query({**self.window, boundary: value})

    def test_invalid_datetime_syntax_and_blank_boundaries_are_rejected(self):
        for boundary in self.window:
            for value in ("not-a-datetime", "2026-13-20T10:00:00Z",
                          "2026-09-20T10:00:00+25:00", ""):
                with self.subTest(boundary=boundary, value=value):
                    self.assert_invalid_query({**self.window, boundary: value})

    def test_partial_query_windows_are_rejected(self):
        for boundary in self.window:
            with self.subTest(boundary=boundary):
                self.assert_invalid_query({boundary: self.window[boundary]})

    def test_two_blank_boundaries_are_not_treated_as_no_window(self):
        self.assert_invalid_query({"created_after": "", "created_before": ""})

    def test_reversed_window_after_utc_normalization_is_rejected(self):
        self.assert_invalid_query({
            "created_after": "2026-09-20T10:00:00-05:00",
            "created_before": "2026-09-20T11:00:00+05:00",
        })

    def test_equal_boundaries_are_accepted(self):
        self.assert_window_allowed(self.members[OrganizationMembership.Role.OWNER],
                                   params={"created_after": self.window["created_after"],
                                           "created_before": self.window["created_after"]},
                                   before=self.created_after)

    def test_exactly_90_intersected_utc_dates_are_accepted(self):
        after = self.created_after.replace(hour=23, minute=59)
        before = (after + timedelta(days=89)).replace(hour=0, minute=0)
        self.assert_window_allowed(self.members[OrganizationMembership.Role.OWNER],
                                   params={"created_after": after.isoformat(),
                                           "created_before": before.isoformat()},
                                   after=after, before=before)

    def test_91_intersected_utc_dates_are_rejected_even_with_duration_under_90_days(self):
        after = self.created_after.replace(hour=23, minute=59)
        before = (after + timedelta(days=90)).replace(hour=0, minute=0)
        self.assertLess(before - after, timedelta(days=90))
        self.assert_invalid_query({"created_after": after.isoformat(), "created_before": before.isoformat()})

    def test_90_utc_dates_are_accepted_even_when_local_boundary_dates_span_92(self):
        after = self.created_after.replace(hour=0, minute=30)
        before = (after + timedelta(days=89)).replace(hour=23, minute=30)
        local_after = after.astimezone(timezone(timedelta(hours=-2)))
        local_before = before.astimezone(timezone(timedelta(hours=8)))
        self.assertEqual((local_before.date() - local_after.date()).days + 1, 92)
        self.assert_window_allowed(self.members[OrganizationMembership.Role.OWNER],
                                   params={"created_after": local_after.isoformat(),
                                           "created_before": local_before.isoformat()},
                                   after=after, before=before)

    def test_91_utc_dates_are_rejected_even_when_local_boundary_dates_span_89(self):
        after = self.created_after.replace(hour=23, minute=30)
        before = (after + timedelta(days=90)).replace(hour=0, minute=30)
        local_after = after.astimezone(timezone(timedelta(hours=8)))
        local_before = before.astimezone(timezone(timedelta(hours=-2)))
        self.assertEqual((local_before.date() - local_after.date()).days + 1, 89)
        self.assert_invalid_query({"created_after": local_after.isoformat(),
                                   "created_before": local_before.isoformat()})

    def test_unknown_query_parameters_are_rejected_in_both_modes(self):
        for params in ({"created_aftr": self.window["created_after"]},
                       {**self.window, "limit": "90"}):
            with self.subTest(params=params):
                response = self.assert_invalid_query(params)
                unknown = "limit" if "limit" in params else "created_aftr"
                self.assertEqual(response.json(), {unknown: ["Unknown query parameter."]})

    def test_forbidden_windowed_actors_execute_no_measurement_services(self):
        for actor in (
            self.members[OrganizationMembership.Role.CONTRIBUTOR],
            self.members[OrganizationMembership.Role.RESEARCHER],
            self.members[OrganizationMembership.Role.MODERATOR],
            self.safety_moderator, self.outsider,
        ):
            with self.subTest(actor=actor.username):
                self.assert_forbidden(actor, params=self.window)

    def test_suspended_and_left_memberships_are_forbidden_with_window(self):
        for membership_status in (OrganizationMembership.Status.SUSPENDED,
                                  OrganizationMembership.Status.LEFT):
            with self.subTest(status=membership_status):
                self.assert_inactive_memberships_forbidden(membership_status, params=self.window)

    def test_windowed_capabilities_do_not_cross_organizations(self):
        for role in (OrganizationMembership.Role.OWNER, OrganizationMembership.Role.ADMIN,
                     OrganizationMembership.Role.LEAD_VERIFIER):
            with self.subTest(role=role):
                actor = self.members[role]
                OrganizationMembership.objects.create(
                    organization=self.other_organization, user=actor,
                    role=OrganizationMembership.Role.CONTRIBUTOR,
                    status=OrganizationMembership.Status.ACTIVE,
                )
                self.assert_window_allowed(actor)
                self.assert_forbidden(actor, params=self.window,
                                      url=self.metrics_url(self.other_organization.pk))

    def test_unknown_organization_with_window_remains_404(self):
        with (
            patch(BASELINE_PATCH) as baseline,
            patch(ACTIVITY_PATCH) as activity,
            patch(TREND_PATCH) as trend,
        ):
            response = self.request_metrics(self.members[OrganizationMembership.Role.OWNER],
                                            params=self.window, url=self.metrics_url(uuid.uuid4()))
        self.assertEqual(response.status_code, 404)
        baseline.assert_not_called()
        activity.assert_not_called()
        self.resolution.assert_not_called()
        self.reviewers.assert_not_called()
        self.public_reach.assert_not_called()
        self.knowledge_reuse.assert_not_called()
        self.current_state.assert_not_called()
        trend.assert_not_called()

    def assert_windowed_integrity_failure(self, source, error):
        with (
            patch(BASELINE_PATCH, return_value=self.baseline,
                  side_effect=error if source == "baseline" else None) as baseline,
            patch(ACTIVITY_PATCH, return_value=self.activity_payload,
                  side_effect=error if source == "activity" else None) as activity,
            patch(RESOLUTION_PATCH, return_value=self.resolution_payload,
                  side_effect=error if source == "resolution" else None) as resolution,
            patch(REVIEWERS_PATCH, return_value=self.reviewer_participation_payload,
                  side_effect=error if source == "reviewers" else None) as reviewers,
            patch(PUBLIC_REACH_PATCH, return_value=self.public_reach_payload,
                  side_effect=error if source == "reach" else None) as reach,
            patch(KNOWLEDGE_REUSE_PATCH, return_value=self.knowledge_reuse_payload,
                  side_effect=error if source == "reuse" else None) as reuse,
            patch(CURRENT_STATE_PATCH, return_value=self.current_state_payload) as current_state,
            patch(TREND_PATCH, return_value=self.trend_payload,
                  side_effect=error if source == "trend" else None) as trend,
            patch("api.views.logger.exception") as log_exception,
        ):
            response = self.request_metrics(self.members[OrganizationMembership.Role.OWNER], params=self.window)
        self.assert_generic_unavailable(response, log_exception)
        self.assertNotIn(str(error), response.content.decode())
        baseline.assert_called_once_with(organization=self.organization)
        if source == "baseline":
            activity.assert_not_called()
        else:
            activity.assert_called_once_with(organization=self.organization)
        if source in ("baseline", "activity"):
            resolution.assert_not_called()
        else:
            resolution.assert_called_once_with(organization=self.organization)
        if source in ("baseline", "activity", "resolution"):
            reviewers.assert_not_called()
        else:
            reviewers.assert_called_once_with(organization=self.organization)
        if source in ("baseline", "activity", "resolution", "reviewers"):
            reach.assert_not_called()
        else:
            reach.assert_called_once_with(organization=self.organization)
        if source in ("baseline", "activity", "resolution", "reviewers", "reach"):
            reuse.assert_not_called()
        else:
            reuse.assert_called_once_with(organization=self.organization)
        if source == "trend":
            current_state.assert_called_once_with(organization=self.organization)
        else:
            current_state.assert_not_called()
        if source == "trend":
            trend.assert_called_once_with(organization=self.organization,
                                          created_after=self.created_after, created_before=self.created_before)
        else:
            trend.assert_not_called()

    def test_windowed_baseline_and_activity_integrity_failures_remain_generic_503(self):
        for source, error in (
            ("baseline", VerificationMetricsIntegrityError("Internal assignment-id details.")),
            ("activity", VerificationActivityMetricsIntegrityError("Internal claim-id details.")),
        ):
            with self.subTest(source=source):
                self.assert_windowed_integrity_failure(source, error)

    def test_new_measurement_integrity_failures_return_generic_503_in_both_modes(self):
        for source, error_type in (
            ("resolution", VerificationResolutionMetricsIntegrityError),
            ("reviewers", VerificationReviewerParticipationMetricsIntegrityError),
            ("reach", VerificationPublicReachMetricsIntegrityError),
            ("reuse", VerificationKnowledgeReuseMetricsIntegrityError),
        ):
            for params in ({}, self.window):
                with self.subTest(source=source, params=params):
                    error = error_type("Internal actor-id claim-id event-id integrity details.")
                    original_resolution = deepcopy(self.resolution_payload)
                    original_reviewers = deepcopy(self.reviewer_participation_payload)
                    original_reach = deepcopy(self.public_reach_payload)
                    original_reuse = deepcopy(self.knowledge_reuse_payload)
                    with (
                        patch(BASELINE_PATCH, return_value=self.baseline) as baseline,
                        patch(ACTIVITY_PATCH, return_value=self.activity_payload) as activity,
                        patch(RESOLUTION_PATCH, return_value=self.resolution_payload,
                              side_effect=error if source == "resolution" else None) as resolution,
                        patch(REVIEWERS_PATCH, return_value=self.reviewer_participation_payload,
                              side_effect=error if source == "reviewers" else None) as reviewers,
                        patch(PUBLIC_REACH_PATCH, return_value=self.public_reach_payload,
                              side_effect=error if source == "reach" else None) as reach,
                        patch(KNOWLEDGE_REUSE_PATCH, return_value=self.knowledge_reuse_payload,
                              side_effect=error if source == "reuse" else None) as reuse,
                        patch(CURRENT_STATE_PATCH, return_value=self.current_state_payload) as current_state,
                        patch(TREND_PATCH) as trend,
                        patch("api.views.logger.exception") as log_exception,
                    ):
                        response = self.request_metrics(
                            self.members[OrganizationMembership.Role.OWNER], params=params,
                        )
                    self.assert_generic_unavailable(response, log_exception)
                    self.assertNotIn(str(error), response.content.decode())
                    baseline.assert_called_once_with(organization=self.organization)
                    activity.assert_called_once_with(organization=self.organization)
                    resolution.assert_called_once_with(organization=self.organization)
                    if source == "resolution":
                        reviewers.assert_not_called()
                    else:
                        reviewers.assert_called_once_with(organization=self.organization)
                    if source in ("resolution", "reviewers"):
                        reach.assert_not_called()
                    else:
                        reach.assert_called_once_with(organization=self.organization)
                    if source in ("resolution", "reviewers", "reach"):
                        reuse.assert_not_called()
                    else:
                        reuse.assert_called_once_with(organization=self.organization)
                    current_state.assert_not_called()
                    trend.assert_not_called()
                    self.assertEqual(self.resolution_payload, original_resolution)
                    self.assertEqual(self.reviewer_participation_payload, original_reviewers)
                    self.assertEqual(self.public_reach_payload, original_reach)
                    self.assertEqual(self.knowledge_reuse_payload, original_reuse)

    def test_each_trend_projection_integrity_failure_is_generic_503(self):
        for error in (
            VerificationMetricsIntegrityError("Internal trend assignment-id details."),
            VerificationActivityMetricsIntegrityError("Internal trend event-id details."),
        ):
            with self.subTest(error=type(error).__name__):
                self.assert_windowed_integrity_failure("trend", error)

    def test_missing_or_mismatched_trend_identity_returns_generic_503(self):
        for identity in (None, str(self.other_organization.pk)):
            with self.subTest(identity=identity):
                payload = deepcopy(self.trend_payload)
                if identity is None:
                    del payload["organization_id"]
                else:
                    payload["organization_id"] = identity
                original = deepcopy(payload)
                with (
                    patch(BASELINE_PATCH, return_value=self.baseline),
                    patch(ACTIVITY_PATCH, return_value=self.activity_payload),
                    patch(PUBLIC_REACH_PATCH, return_value=self.public_reach_payload) as reach,
                    patch(KNOWLEDGE_REUSE_PATCH, return_value=self.knowledge_reuse_payload) as reuse,
                    patch(CURRENT_STATE_PATCH, return_value=self.current_state_payload) as current_state,
                    patch(TREND_PATCH, return_value=payload),
                    patch("api.views.logger.exception") as log_exception,
                ):
                    response = self.request_metrics(self.members[OrganizationMembership.Role.OWNER], params=self.window)
                self.assert_generic_unavailable(response, log_exception)
                self.assertEqual(payload, original)
                reach.assert_called_once_with(organization=self.organization)
                reuse.assert_called_once_with(organization=self.organization)
                current_state.assert_called_once_with(organization=self.organization)

    def test_defensive_trend_input_error_returns_generic_400(self):
        error = VerificationActivityTrendInputError("Internal invalid-window details.")
        with (
            patch(BASELINE_PATCH, return_value=self.baseline),
            patch(ACTIVITY_PATCH, return_value=self.activity_payload),
            patch(TREND_PATCH, side_effect=error),
            patch("api.views.logger.exception") as log_exception,
        ):
            response = self.request_metrics(self.members[OrganizationMembership.Role.OWNER], params=self.window)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "Invalid verification analytics time window."})
        log_exception.assert_not_called()
        self.public_reach.assert_called_once_with(organization=self.organization)
        self.knowledge_reuse.assert_called_once_with(organization=self.organization)
        self.current_state.assert_called_once_with(organization=self.organization)

    def test_trend_datetimes_serialize_as_utc_over_http(self):
        response = self.assert_window_allowed(self.members[OrganizationMembership.Role.OWNER])
        self.assertEqual(response.json()["trend"], {
            "measurement_basis": {
                **self.trend_payload["measurement_basis"],
                "created_after": "2026-09-20T10:00:00Z",
                "created_before": "2026-09-22T12:00:00Z",
            },
            "totals": self.trend_payload["totals"],
            "daily": self.trend_payload["daily"],
        })

    def test_empty_trend_counts_and_daily_buckets_are_preserved_exactly(self):
        zeros = {section: dict.fromkeys(fields, 0)
                 for section, fields in self.trend_payload["totals"].items()}
        self.trend_payload["totals"] = deepcopy(zeros)
        self.trend_payload["daily"] = [
            {"date": value, **deepcopy(zeros)}
            for value in ("2026-09-20", "2026-09-21", "2026-09-22")
        ]
        response = self.assert_window_allowed(self.members[OrganizationMembership.Role.OWNER])
        self.assertEqual(response.json()["trend"]["totals"], zeros)
        self.assertEqual(response.json()["trend"]["daily"], self.trend_payload["daily"])

    def test_existing_route_name_and_path_are_preserved(self):
        self.assertTrue(self.url.endswith(
            f"/organizations/{self.organization.pk}/analytics/verification/"
        ))

    def test_new_sections_expose_only_structural_aggregate_metrics(self):
        response = self.assert_allowed(self.members[OrganizationMembership.Role.OWNER])
        resolution = response.json()["resolution_distribution"]
        reviewers = response.json()["reviewer_participation"]
        self.assertEqual(set(resolution["latest_observed_resolutions"]), {"count", "by_verdict"})
        self.assertEqual(set(resolution["latest_observed_resolutions"]["by_verdict"]), {
            "FACT", "FAKE", "MISLEADING", "SATIRE",
        })
        self.assertEqual(set(reviewers["by_stage"]), {"evidence_review", "adjudication"})
        self.assertEqual(reviewers["unique_reviewers"], 3)
        self.assertEqual(reviewers["by_stage"], {"evidence_review": 2, "adjudication": 2})
        self.assertEqual(set(reviewers["measurement_basis"]), {
            "source", "identity_source", "coverage", "historical_backfill",
            "first_observed_participation_at", "last_observed_participation_at",
        })
        self.assertEqual(set(resolution["measurement_basis"]), {
            "source", "coverage", "historical_backfill",
            "first_observed_resolution_at", "last_observed_resolution_at",
        })
        for actor in self.members.values():
            self.assertNotIn(actor.username, response.content.decode())
        for section in (response.json()["public_reach"], response.json()["knowledge_reuse"]):
            def check_keys(value):
                if isinstance(value, dict):
                    for key, child in value.items():
                        self.assertNotIn(key, {
                            "organization_id", "client_event_id", "actor", "actor_id", "user", "user_id",
                            "triggered_by", "triggered_by_id", "query_fingerprint", "metadata",
                        })
                        check_keys(child)
            check_keys(section)

        current_state = response.json()["current_state"]
        self.assertEqual(current_state, {
            "measurement_basis": {
                "source": "PERSISTED_OPERATIONAL_RECORDS",
                "coverage": "CURRENT_STATE",
            },
            "published_fact_checks": {"distinct_claims": 2},
            "factual_corrections": {"active_requests": 1},
            "investigations": {"active_assignments": 3},
            "publication_work": {"distinct_claims": 1},
        })
        for section, field in (
            ("published_fact_checks", "distinct_claims"),
            ("factual_corrections", "active_requests"),
            ("investigations", "active_assignments"),
            ("publication_work", "distinct_claims"),
        ):
            self.assertIsInstance(current_state[section][field], int)

    def test_current_state_uses_real_records_is_unwindowed_and_get_is_read_only(self):
        published_claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Current published API metric claim.",
        )
        published_decision = AdjudicationDecision.objects.create(
            claim=published_claim,
            verdict=AdjudicationDecision.Verdict.FACT,
            canonical_claim="Current published API metric claim.",
            rationale="Persisted API metric decision.",
            decided_by=self.members[OrganizationMembership.Role.LEAD_VERIFIER],
            organization=self.organization,
        )
        publication = OfficialFactCheck.objects.create(
            claim=published_claim,
            adjudication_decision=published_decision,
            organization=self.organization,
            canonical_claim=published_decision.canonical_claim,
            verdict=published_decision.verdict,
            headline="Private current publication headline",
            summary="Private current publication summary.",
            article_body="Private current publication body.",
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            revision_kind=OfficialFactCheck.RevisionKind.INITIAL,
        )
        draft_claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Current open publication work API metric claim.",
        )
        draft_decision = AdjudicationDecision.objects.create(
            claim=draft_claim,
            verdict=AdjudicationDecision.Verdict.FACT,
            canonical_claim="Current open publication work API metric claim.",
            rationale="Persisted draft API metric decision.",
            decided_by=self.members[OrganizationMembership.Role.LEAD_VERIFIER],
            organization=self.organization,
        )
        draft = OfficialFactCheck.objects.create(
            claim=draft_claim,
            adjudication_decision=draft_decision,
            organization=self.organization,
            canonical_claim=draft_decision.canonical_claim,
            verdict=draft_decision.verdict,
            headline="Private current draft headline",
            summary="Private current draft summary.",
            article_body="Private current draft body.",
            publication_status=OfficialFactCheck.PublicationStatus.DRAFT,
            revision_kind=OfficialFactCheck.RevisionKind.INITIAL,
        )
        assignment_claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Current active investigation API metric claim.",
        )
        assignment = VerificationAssignment.objects.create(
            claim=assignment_claim,
            organization=self.organization,
            claimed_by=self.members[OrganizationMembership.Role.LEAD_VERIFIER],
            status=VerificationAssignment.Status.ACTIVE,
        )
        event_count = AccountabilityEvent.objects.count()
        record_counts = {
            OfficialFactCheck: OfficialFactCheck.objects.count(),
            VerificationAssignment: VerificationAssignment.objects.count(),
        }

        with (
            CaptureQueriesContext(connection) as queries,
            patch(BASELINE_PATCH, return_value=self.baseline),
            patch(ACTIVITY_PATCH, return_value=self.activity_payload),
            patch(RESOLUTION_PATCH, return_value=self.resolution_payload),
            patch(REVIEWERS_PATCH, return_value=self.reviewer_participation_payload),
            patch(PUBLIC_REACH_PATCH, return_value=self.public_reach_payload),
            patch(KNOWLEDGE_REUSE_PATCH, return_value=self.knowledge_reuse_payload),
            patch(
                CURRENT_STATE_PATCH,
                wraps=get_organization_verification_current_state,
            ) as current_state,
            patch(TREND_PATCH, return_value=self.trend_payload),
        ):
            aggregate = self.request_metrics(
                self.members[OrganizationMembership.Role.OWNER]
            )
            windowed = self.request_metrics(
                self.members[OrganizationMembership.Role.OWNER],
                params=self.window,
            )

        expected_current_state = {
            "measurement_basis": {
                "source": "PERSISTED_OPERATIONAL_RECORDS",
                "coverage": "CURRENT_STATE",
            },
            "published_fact_checks": {"distinct_claims": 1},
            "factual_corrections": {"active_requests": 0},
            "investigations": {"active_assignments": 1},
            "publication_work": {"distinct_claims": 1},
        }
        self.assertEqual(aggregate.status_code, 200)
        self.assertEqual(windowed.status_code, 200)
        self.assertTrue(queries.captured_queries)
        for query in queries.captured_queries:
            sql = query["sql"].lstrip().upper()
            self.assertFalse(sql.startswith(("INSERT", "UPDATE", "DELETE")))
        self.assertEqual(aggregate.data["current_state"], expected_current_state)
        self.assertEqual(windowed.data["current_state"], expected_current_state)
        self.assertEqual(current_state.call_count, 2)
        for key, value in self.expected_payload().items():
            if key != "current_state":
                self.assertEqual(aggregate.data[key], value)
                self.assertEqual(windowed.data[key], value)
        serialized = str(aggregate.data["current_state"])
        for private_value in (
            publication.id,
            publication.claim_id,
            publication.headline,
            draft.id,
            draft.claim_id,
            draft.article_body,
            assignment.id,
            assignment.claim_id,
        ):
            self.assertNotIn(str(private_value), serialized)
        self.assertEqual(AccountabilityEvent.objects.count(), event_count)
        self.assertEqual(
            {
                OfficialFactCheck: OfficialFactCheck.objects.count(),
                VerificationAssignment: VerificationAssignment.objects.count(),
            },
            record_counts,
        )

    def test_populated_reach_and_reuse_are_unchanged_by_trend_window(self):
        # These observations predate the requested trend window.
        observed_at = datetime(2026, 9, 16, 8, tzinfo=timezone.utc)
        self.public_reach_payload["measurement_basis"].update(
            first_observed_interaction_at=observed_at, last_observed_interaction_at=observed_at,
        )
        self.public_reach_payload["observed_interactions"].update(events=3, distinct_publications=1)
        self.public_reach_payload["observed_interactions"]["by_type"]["PUBLICATION_VIEW"] = 3
        self.public_reach_payload["observed_interactions"]["by_surface"]["PUBLIC_FACT_CHECK_PAGE"] = 3
        self.knowledge_reuse_payload["measurement_basis"].update(
            first_observed_reuse_at=observed_at, last_observed_reuse_at=observed_at,
        )
        self.knowledge_reuse_payload["material_reuse"].update(events=2, distinct_publications=1, distinct_target_claims=1)
        self.knowledge_reuse_payload["material_reuse"]["by_type"]["USER_RESPONSE"] = 2
        self.knowledge_reuse_payload["material_reuse"]["by_match_method"]["CLAIM_CACHE"] = 2
        self.knowledge_reuse_payload["repeat_claim_reuse"].update(cached_published_responses=2, distinct_cached_claims=1)
        actor = self.members[OrganizationMembership.Role.OWNER]
        aggregate = self.assert_allowed(actor)
        windowed = self.assert_window_allowed(actor)
        for section in ("public_reach", "knowledge_reuse"):
            self.assertEqual(aggregate.data[section], windowed.data[section])
        self.assertEqual(aggregate.json()["public_reach"]["measurement_basis"]["first_observed_interaction_at"],
                         "2026-09-16T08:00:00Z")


class VerificationMetricsQueryBoundaryTests(SimpleTestCase):
    """No database access is permitted at this delegation boundary."""

    def setUp(self):
        self.public_reach = self.enterContext(patch(PUBLIC_REACH_PATCH, side_effect=make_public_reach_payload))
        self.knowledge_reuse = self.enterContext(patch(KNOWLEDGE_REUSE_PATCH, side_effect=make_knowledge_reuse_payload))
        self.current_state = self.enterContext(
            patch(CURRENT_STATE_PATCH, side_effect=make_current_state_payload)
        )
        resolution_patch = patch(RESOLUTION_PATCH, side_effect=make_resolution_payload)
        self.resolution = resolution_patch.start()
        self.addCleanup(resolution_patch.stop)
        reviewers_patch = patch(REVIEWERS_PATCH, side_effect=make_reviewer_participation_payload)
        self.reviewers = reviewers_patch.start()
        self.addCleanup(reviewers_patch.stop)

    def test_each_qualifying_capability_delegates_and_composes_without_mutation(self):
        actor = object()
        organization = SimpleNamespace(pk=uuid.uuid4())
        payload = {"organization_id": str(organization.pk), "attempts": {"claimed": 2}}
        activity_payload = {
            "organization_id": str(organization.pk),
            "measurement_basis": {"first_observed_activity_at": None},
            "evidence_review": {"decisions": 1, "verified": 1, "rejected": 0},
            "adjudication": {"started": 0, "verdicts_issued": 0},
            "publication": {"initial_published": 0},
        }
        original_baseline = deepcopy(payload)
        original_activity = deepcopy(activity_payload)
        resolution_payload = make_resolution_payload(organization)
        reviewers_payload = make_reviewer_participation_payload(organization)
        original_resolution = deepcopy(resolution_payload)
        original_reviewers = deepcopy(reviewers_payload)
        reach_payload = make_public_reach_payload(organization)
        reuse_payload = make_knowledge_reuse_payload(organization)
        current_state_payload = make_current_state_payload(organization)
        original_reach = deepcopy(reach_payload)
        original_reuse = deepcopy(reuse_payload)
        original_current_state = deepcopy(current_state_payload)
        for results, capabilities in (
            ([True], [PartnerCapability.MANAGE_ORGANIZATION]),
            ([False, True], [
                PartnerCapability.MANAGE_ORGANIZATION,
                PartnerCapability.CLAIM_VERIFICATION_WORK,
            ]),
        ):
            with (
                self.subTest(results=results),
                patch(
                    "api.verification_metrics_query_service.has_capability",
                    side_effect=results,
                ) as capability,
                patch(BASELINE_PATCH, return_value=payload) as baseline,
                patch(ACTIVITY_PATCH, return_value=activity_payload) as activity,
                patch(RESOLUTION_PATCH, return_value=resolution_payload) as resolution,
                patch(REVIEWERS_PATCH, return_value=reviewers_payload) as reviewers,
                patch(PUBLIC_REACH_PATCH, return_value=reach_payload) as reach,
                patch(KNOWLEDGE_REUSE_PATCH, return_value=reuse_payload) as reuse,
                patch(CURRENT_STATE_PATCH, return_value=current_state_payload) as current_state,
                patch(TREND_PATCH) as trend,
            ):
                result = get_organization_verification_metrics(
                    actor=actor, organization=organization,
                )
            self.assertEqual(result, {
                "organization_id": str(organization.pk),
                "attempts": {"claimed": 2},
                "activity": {
                    "measurement_basis": {"first_observed_activity_at": None},
                    "evidence_review": {"decisions": 1, "verified": 1, "rejected": 0},
                    "adjudication": {"started": 0, "verdicts_issued": 0},
                    "publication": {"initial_published": 0},
                },
                "resolution_distribution": {
                    "measurement_basis": original_resolution["measurement_basis"],
                    "latest_observed_resolutions": original_resolution["latest_observed_resolutions"],
                },
                "reviewer_participation": {
                    "measurement_basis": original_reviewers["measurement_basis"],
                    "unique_reviewers": 3,
                    "by_stage": {"evidence_review": 2, "adjudication": 2},
                },
                "public_reach": measurement_section(original_reach),
                "knowledge_reuse": measurement_section(original_reuse),
                "current_state": measurement_section(original_current_state),
            })
            self.assertIsNot(result, payload)
            self.assertIsNot(result["activity"], activity_payload)
            self.assertEqual(payload, original_baseline)
            self.assertEqual(activity_payload, original_activity)
            self.assertEqual(resolution_payload, original_resolution)
            self.assertEqual(reviewers_payload, original_reviewers)
            self.assertEqual(reach_payload, original_reach)
            self.assertEqual(reuse_payload, original_reuse)
            self.assertEqual(current_state_payload, original_current_state)
            self.assertIsNot(result["resolution_distribution"], resolution_payload)
            self.assertIsNot(result["reviewer_participation"], reviewers_payload["reviewer_participation"])
            self.assertEqual(capability.call_args_list, [
                call(actor, required, organization=organization)
                for required in capabilities
            ])
            baseline.assert_called_once_with(organization=organization)
            activity.assert_called_once_with(organization=organization)
            resolution.assert_called_once_with(organization=organization)
            reviewers.assert_called_once_with(organization=organization)
            reach.assert_called_once_with(organization=organization)
            reuse.assert_called_once_with(organization=organization)
            current_state.assert_called_once_with(organization=organization)
            trend.assert_not_called()

    def test_missing_capabilities_raise_without_reading_any_service(self):
        actor = object()
        organization = SimpleNamespace(pk=uuid.uuid4())
        with (
            patch(
                "api.verification_metrics_query_service.has_capability",
                return_value=False,
            ) as capability,
            patch(BASELINE_PATCH) as baseline,
            patch(ACTIVITY_PATCH) as activity,
            patch(TREND_PATCH) as trend,
        ):
            with self.assertRaises(VerificationMetricsAuthorizationError):
                get_organization_verification_metrics(actor=actor, organization=organization)
        self.assertEqual(capability.call_args_list, [
            call(actor, PartnerCapability.MANAGE_ORGANIZATION, organization=organization),
            call(actor, PartnerCapability.CLAIM_VERIFICATION_WORK, organization=organization),
        ])
        baseline.assert_not_called()
        activity.assert_not_called()
        self.resolution.assert_not_called()
        self.reviewers.assert_not_called()
        self.public_reach.assert_not_called()
        self.knowledge_reuse.assert_not_called()
        self.current_state.assert_not_called()
        trend.assert_not_called()

    def test_missing_or_mismatched_service_identity_raises_composition_error(self):
        actor = object()
        organization = SimpleNamespace(pk=uuid.uuid4())
        for service in (
            "baseline", "activity", "resolution", "reviewers", "reach", "reuse", "current",
        ):
            for identity in (None, str(uuid.uuid4())):
                with self.subTest(service=service, identity=identity):
                    baseline_payload = {"organization_id": str(organization.pk)}
                    activity_payload = {"organization_id": str(organization.pk)}
                    resolution_payload = make_resolution_payload(organization)
                    reviewers_payload = make_reviewer_participation_payload(organization)
                    reach_payload = make_public_reach_payload(organization)
                    reuse_payload = make_knowledge_reuse_payload(organization)
                    current_payload = make_current_state_payload(organization)
                    malformed = {
                        "baseline": baseline_payload, "activity": activity_payload,
                        "resolution": resolution_payload, "reviewers": reviewers_payload,
                        "reach": reach_payload, "reuse": reuse_payload,
                        "current": current_payload,
                    }[service]
                    if identity is None:
                        del malformed["organization_id"]
                    else:
                        malformed["organization_id"] = identity
                    original_baseline = deepcopy(baseline_payload)
                    original_activity = deepcopy(activity_payload)
                    original_resolution = deepcopy(resolution_payload)
                    original_reviewers = deepcopy(reviewers_payload)
                    original_reach = deepcopy(reach_payload)
                    original_reuse = deepcopy(reuse_payload)
                    original_current = deepcopy(current_payload)
                    with (
                        patch(
                            "api.verification_metrics_query_service.has_capability",
                            return_value=True,
                        ),
                        patch(BASELINE_PATCH, return_value=baseline_payload) as baseline,
                        patch(ACTIVITY_PATCH, return_value=activity_payload) as activity,
                        patch(RESOLUTION_PATCH, return_value=resolution_payload) as resolution,
                        patch(REVIEWERS_PATCH, return_value=reviewers_payload) as reviewers,
                        patch(PUBLIC_REACH_PATCH, return_value=reach_payload) as reach,
                        patch(KNOWLEDGE_REUSE_PATCH, return_value=reuse_payload) as reuse,
                        patch(CURRENT_STATE_PATCH, return_value=current_payload) as current_state,
                        patch(TREND_PATCH) as trend,
                    ):
                        with self.assertRaises(VerificationMetricsCompositionError):
                            get_organization_verification_metrics(
                                actor=actor, organization=organization,
                            )
                    baseline.assert_called_once_with(organization=organization)
                    activity.assert_called_once_with(organization=organization)
                    resolution.assert_called_once_with(organization=organization)
                    reviewers.assert_called_once_with(organization=organization)
                    reach.assert_called_once_with(organization=organization)
                    reuse.assert_called_once_with(organization=organization)
                    current_state.assert_called_once_with(organization=organization)
                    trend.assert_not_called()
                    self.assertEqual(baseline_payload, original_baseline)
                    self.assertEqual(activity_payload, original_activity)
                    self.assertEqual(resolution_payload, original_resolution)
                    self.assertEqual(reviewers_payload, original_reviewers)
                    self.assertEqual(reach_payload, original_reach)
                    self.assertEqual(reuse_payload, original_reuse)
                    self.assertEqual(current_payload, original_current)

    def test_direct_partial_window_fails_after_authorization_before_all_measurements(self):
        actor = object()
        organization = SimpleNamespace(pk=uuid.uuid4())
        boundary = datetime(2026, 9, 20, 10, tzinfo=timezone.utc)
        for kwargs in ({"created_after": boundary}, {"created_before": boundary}):
            with self.subTest(kwargs=kwargs):
                with (
                    patch("api.verification_metrics_query_service.has_capability",
                          return_value=True) as capability,
                    patch(BASELINE_PATCH) as baseline,
                    patch(ACTIVITY_PATCH) as activity,
                    patch(TREND_PATCH) as trend,
                ):
                    with self.assertRaises(VerificationActivityTrendInputError):
                        get_organization_verification_metrics(
                            actor=actor, organization=organization, **kwargs,
                        )
                capability.assert_called_once_with(
                    actor, PartnerCapability.MANAGE_ORGANIZATION, organization=organization,
                )
                baseline.assert_not_called()
                activity.assert_not_called()
                self.resolution.assert_not_called()
                self.reviewers.assert_not_called()
                self.public_reach.assert_not_called()
                self.knowledge_reuse.assert_not_called()
                self.current_state.assert_not_called()
                trend.assert_not_called()

    def test_direct_partial_window_does_not_bypass_authorization(self):
        actor = object()
        organization = SimpleNamespace(pk=uuid.uuid4())
        with (
            patch("api.verification_metrics_query_service.has_capability",
                  return_value=False) as capability,
            patch(BASELINE_PATCH) as baseline,
            patch(ACTIVITY_PATCH) as activity,
            patch(TREND_PATCH) as trend,
        ):
            with self.assertRaises(VerificationMetricsAuthorizationError):
                get_organization_verification_metrics(
                    actor=actor, organization=organization,
                    created_after=datetime(2026, 9, 20, 10, tzinfo=timezone.utc),
                )
        self.assertEqual(capability.call_args_list, [
            call(actor, PartnerCapability.MANAGE_ORGANIZATION, organization=organization),
            call(actor, PartnerCapability.CLAIM_VERIFICATION_WORK, organization=organization),
        ])
        baseline.assert_not_called()
        activity.assert_not_called()
        self.resolution.assert_not_called()
        self.reviewers.assert_not_called()
        self.public_reach.assert_not_called()
        self.knowledge_reuse.assert_not_called()
        self.current_state.assert_not_called()
        trend.assert_not_called()

    def test_direct_missing_or_mismatched_trend_identity_raises_composition_error(self):
        organization = SimpleNamespace(pk=uuid.uuid4())
        after = datetime(2026, 9, 20, 10, tzinfo=timezone.utc)
        before = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
        for identity in (None, str(uuid.uuid4())):
            with self.subTest(identity=identity):
                baseline_payload = {"organization_id": str(organization.pk)}
                activity_payload = {
                    "organization_id": str(organization.pk),
                    "measurement_basis": {}, "evidence_review": {},
                    "adjudication": {}, "publication": {},
                }
                trend_payload = {} if identity is None else {"organization_id": identity}
                original = deepcopy(trend_payload)
                with (
                    patch("api.verification_metrics_query_service.has_capability", return_value=True),
                    patch(BASELINE_PATCH, return_value=baseline_payload) as baseline,
                    patch(ACTIVITY_PATCH, return_value=activity_payload) as activity,
                    patch(PUBLIC_REACH_PATCH, side_effect=make_public_reach_payload) as reach,
                    patch(KNOWLEDGE_REUSE_PATCH, side_effect=make_knowledge_reuse_payload) as reuse,
                    patch(CURRENT_STATE_PATCH, side_effect=make_current_state_payload) as current_state,
                    patch(TREND_PATCH, return_value=trend_payload) as trend,
                ):
                    with self.assertRaises(VerificationMetricsCompositionError):
                        get_organization_verification_metrics(
                            actor=object(), organization=organization,
                            created_after=after, created_before=before,
                        )
                baseline.assert_called_once_with(organization=organization)
                activity.assert_called_once_with(organization=organization)
                reach.assert_called_once_with(organization=organization)
                reuse.assert_called_once_with(organization=organization)
                current_state.assert_called_once_with(organization=organization)
                trend.assert_called_once_with(
                    organization=organization, created_after=after, created_before=before,
                )
                self.assertEqual(trend_payload, original)
