import json
from datetime import timedelta
from uuid import uuid4

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from api.models import (
    Claim,
    Organization,
    OrganizationMembership,
    VerificationRun,
    VerificationTelemetryEvent,
)


class ManagementPipelineTelemetryApiTests(APITestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="platform-admin",
            email="platform-admin@example.com",
            password="password",
        )
        self.ordinary = User.objects.create_user(username="ordinary")
        self.staff = User.objects.create_user(username="staff", is_staff=True)
        self.primary_admin = User.objects.create_user(username="primary-admin")
        self.organization_admin = User.objects.create_user(username="org-admin")
        self.inactive_superuser = User.objects.create_superuser(
            username="inactive-admin",
            email="inactive@example.com",
            password="password",
            is_active=False,
        )
        organization = Organization.objects.create(
            name="Organization",
            slug="organization",
        )
        OrganizationMembership.objects.create(
            organization=organization,
            user=self.primary_admin,
            role=OrganizationMembership.Role.OWNER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        OrganizationMembership.objects.create(
            organization=organization,
            user=self.organization_admin,
            role=OrganizationMembership.Role.ADMIN,
            status=OrganizationMembership.Status.ACTIVE,
        )
        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="DANGEROUS PRIVATE CLAIM TEXT",
            url_link="https://private.example/secret-url",
            media_url="https://private.example/secret-media",
        )
        now = timezone.now()
        self.run = VerificationRun.objects.create(
            claim=self.claim,
            triggered_by=self.ordinary,
            status=VerificationRun.Status.FAILED,
            pipeline_version="test-v1",
            started_at=now - timedelta(milliseconds=400),
            completed_at=now,
            failure_stage="claim_gate",
            failure_code="LLM_UNAVAILABLE",
            failure_message="DANGEROUS FAILURE MESSAGE",
        )
        VerificationTelemetryEvent.objects.create(
            verification_run=self.run,
            sequence=1,
            event_type=VerificationTelemetryEvent.EventType.PIPELINE_STAGE,
            name="tavily_evidence_ingestion_failed",
            duration_ms=300,
            outcome="failed",
            metadata={
                "status_code": 503,
                "results": 2,
                "error": "DANGEROUS STAGE ERROR",
                "claim_text": "DANGEROUS CLAIM METADATA",
                "authorization": "Bearer DANGEROUS TOKEN",
                "prompt": "DANGEROUS PROMPT",
            },
            occurred_at=now,
        )
        self.provider_call_id = uuid4()
        VerificationTelemetryEvent.objects.create(
            verification_run=self.run,
            sequence=2,
            event_type=VerificationTelemetryEvent.EventType.LLM_PROVIDER_CALL,
            name="claim_gate",
            provider="gemini",
            provider_call_id=self.provider_call_id,
            duration_ms=100,
            outcome="failed",
            error_label="RuntimeError code=503",
            metadata={"response": "DANGEROUS RESPONSE"},
            occurred_at=now,
        )
        VerificationTelemetryEvent.objects.create(
            verification_run=self.run,
            sequence=3,
            event_type=VerificationTelemetryEvent.EventType.LLM_PROVIDER_CALL,
            name="claim_gate",
            provider="groq",
            provider_call_id=self.provider_call_id,
            duration_ms=200,
            outcome="success",
            occurred_at=now,
        )

    def client_for(self, user):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    def test_platform_authority_is_required_for_every_endpoint(self):
        urls = (
            reverse("management_pipeline_overview"),
            reverse("management_pipeline_runs"),
            reverse("management_pipeline_run_detail", kwargs={"run_id": self.run.id}),
        )
        for user, expected in (
            (None, status.HTTP_401_UNAUTHORIZED),
            (self.ordinary, status.HTTP_403_FORBIDDEN),
            (self.staff, status.HTTP_403_FORBIDDEN),
            (self.primary_admin, status.HTTP_403_FORBIDDEN),
            (self.organization_admin, status.HTTP_403_FORBIDDEN),
            (self.inactive_superuser, status.HTTP_403_FORBIDDEN),
            (self.superuser, status.HTTP_200_OK),
        ):
            for url in urls:
                with self.subTest(user=user, url=url):
                    self.assertEqual(self.client_for(user).get(url).status_code, expected)

    def test_windows_are_strict_and_default_to_seven_days(self):
        client = self.client_for(self.superuser)
        default = client.get(reverse("management_pipeline_overview"))
        self.assertEqual(default.data["window"]["value"], "7d")
        for window in ("24h", "7d", "30d"):
            response = client.get(reverse("management_pipeline_overview"), {"window": window})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["window"]["value"], window)
        for params in (
            {"window": "90d"},
            {"created_after": "2026-01-01"},
            {"window": "7d", "unexpected": "value"},
        ):
            response = client.get(reverse("management_pipeline_overview"), params)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_overview_derives_durations_statuses_stages_and_fallback(self):
        now = timezone.now()
        durations = [100, 200, 300]
        for index, duration in enumerate(durations):
            claim = Claim.objects.create(claim_type=Claim.ClaimType.URL)
            VerificationRun.objects.create(
                claim=claim,
                status=VerificationRun.Status.COMPLETED,
                started_at=now - timedelta(milliseconds=duration),
                completed_at=now,
                pipeline_version=f"sample-{index}",
            )
        missing = VerificationRun.objects.create(
            claim=Claim.objects.create(claim_type=Claim.ClaimType.IMAGE),
            status=VerificationRun.Status.RUNNING,
        )
        response = self.client_for(self.superuser).get(
            reverse("management_pipeline_overview")
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["runs"]["total"], 5)
        self.assertEqual(response.data["runs"]["statuses"]["FAILED"], 1)
        self.assertEqual(response.data["runs"]["statuses"]["COMPLETED"], 3)
        self.assertEqual(response.data["runs"]["statuses"]["RUNNING"], 1)
        self.assertEqual(response.data["runs"]["duration_samples"], 4)
        self.assertEqual(response.data["runs"]["median_duration_ms"], 250)
        self.assertEqual(response.data["runs"]["p95_duration_ms"], 400)
        self.assertNotEqual(missing.id, self.run.id)

        stage = response.data["stages"][0]
        self.assertEqual(stage["stage"], "tavily_evidence_ingestion")
        self.assertEqual(stage["failures"], 1)
        provider_rows = {
            (row["operation"], row["provider"]): row
            for row in response.data["providers"]
        }
        self.assertEqual(provider_rows[("claim_gate", "gemini")]["failures"], 1)
        self.assertEqual(provider_rows[("claim_gate", "groq")]["successes"], 1)
        self.assertEqual(
            response.data["fallback"],
            {"groq_attempts": 1, "groq_successes": 1, "runs_using_groq": 1},
        )

    def test_stage_failure_aggregation_covers_terminal_failure_outcomes(self):
        now = timezone.now()
        stage_cases = (
            ("case_claim_gate", "claim_gate_failed", 1),
            ("case_url_extract", "url_extraction_failed_deleted", 1),
            ("case_final_evaluator", "final_evaluator_unavailable", 1),
            ("case_fatal", "fatal_error", 1),
            ("case_completed_fallback", "completed_tavily_fallback_unverified", 0),
            ("case_abstained", "abstained_out_of_scope", 0),
        )
        for offset, (stage_name, outcome, _expected_failures) in enumerate(
            stage_cases,
            start=4,
        ):
            VerificationTelemetryEvent.objects.create(
                verification_run=self.run,
                sequence=offset,
                event_type=VerificationTelemetryEvent.EventType.PIPELINE_STAGE,
                name=stage_name,
                duration_ms=10 + offset,
                outcome=outcome,
                occurred_at=now,
            )

        response = self.client_for(self.superuser).get(
            reverse("management_pipeline_overview")
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        stage_rows = {row["stage"]: row for row in response.data["stages"]}
        for stage_name, _outcome, expected_failures in stage_cases:
            with self.subTest(stage=stage_name):
                self.assertEqual(stage_rows[stage_name]["failures"], expected_failures)

    def test_p95_uses_nearest_rank(self):
        now = timezone.now()
        for duration in range(1, 21):
            run = VerificationRun.objects.create(
                claim=Claim.objects.create(claim_type=Claim.ClaimType.TEXT),
                status=VerificationRun.Status.COMPLETED,
                started_at=now - timedelta(milliseconds=duration),
                completed_at=now,
            )
            if duration == 1:
                self.run.delete()
        response = self.client_for(self.superuser).get(
            reverse("management_pipeline_overview")
        )
        self.assertEqual(response.data["runs"]["p95_duration_ms"], 19)
        self.assertEqual(run.status, VerificationRun.Status.COMPLETED)

    def test_run_list_filters_and_stable_page_number_pagination(self):
        for index in range(4):
            VerificationRun.objects.create(
                claim=Claim.objects.create(
                    claim_type=(Claim.ClaimType.URL if index % 2 else Claim.ClaimType.TEXT)
                ),
                status=(
                    VerificationRun.Status.COMPLETED
                    if index < 3
                    else VerificationRun.Status.ABSTAINED
                ),
            )
        client = self.client_for(self.superuser)
        url = reverse("management_pipeline_runs")
        filtered = client.get(
            url,
            {"window": "7d", "status": "COMPLETED", "claim_type": "URL"},
        )
        self.assertEqual(filtered.status_code, status.HTTP_200_OK)
        self.assertTrue(filtered.data["results"])
        self.assertTrue(
            all(row["status"] == "COMPLETED" for row in filtered.data["results"])
        )
        self.assertTrue(all(row["claim_type"] == "URL" for row in filtered.data["results"]))

        first = client.get(url, {"page_size": 2, "page": 1})
        second = client.get(url, {"page_size": 2, "page": 2})
        first_ids = {row["id"] for row in first.data["results"]}
        second_ids = {row["id"] for row in second.data["results"]}
        self.assertFalse(first_ids & second_ids)
        self.assertEqual(len(first_ids), 2)
        self.assertEqual(len(second_ids), 2)

    def test_run_list_rejects_unsupported_parameters(self):
        response = self.client_for(self.superuser).get(
            reverse("management_pipeline_runs"),
            {"created_before": timezone.now().isoformat()},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_detail_orders_events_and_exposes_only_safe_projection(self):
        response = self.client_for(self.superuser).get(
            reverse("management_pipeline_run_detail", kwargs={"run_id": self.run.id})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["duration_ms"], 400)
        self.assertNotIn("failure_message", response.data)
        self.assertNotIn("triggered_by", response.data)
        events = response.data["telemetry_events"]
        self.assertEqual([event["sequence"] for event in events], [1, 2, 3])
        self.assertEqual(events[0]["metadata"], {"status_code": 503, "results": 2})
        self.assertEqual(events[1]["error_label"], "RuntimeError code=503")

        payload = json.dumps(response.data, default=str)
        for secret in (
            "DANGEROUS PRIVATE CLAIM TEXT",
            "secret-url",
            "secret-media",
            "ordinary",
            "DANGEROUS FAILURE MESSAGE",
            "DANGEROUS STAGE ERROR",
            "DANGEROUS CLAIM METADATA",
            "DANGEROUS TOKEN",
            "DANGEROUS PROMPT",
            "DANGEROUS RESPONSE",
        ):
            self.assertNotIn(secret, payload)

    def test_missing_duration_is_null_not_zero(self):
        run = VerificationRun.objects.create(
            claim=Claim.objects.create(claim_type=Claim.ClaimType.FILE),
            status=VerificationRun.Status.PENDING,
        )
        response = self.client_for(self.superuser).get(
            reverse("management_pipeline_run_detail", kwargs={"run_id": run.id})
        )
        self.assertIsNone(response.data["duration_ms"])

    def test_detail_rejects_query_parameters_and_unknown_run_is_404(self):
        client = self.client_for(self.superuser)
        url = reverse("management_pipeline_run_detail", kwargs={"run_id": self.run.id})
        self.assertEqual(client.get(url, {"window": "7d"}).status_code, 400)
        missing_url = reverse(
            "management_pipeline_run_detail", kwargs={"run_id": uuid4()}
        )
        self.assertEqual(client.get(missing_url).status_code, 404)
