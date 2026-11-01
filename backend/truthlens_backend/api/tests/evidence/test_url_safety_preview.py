import socket
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from api.models import Claim, EvidenceSubmission, Thread
from api.services import validate_public_url
from api.tasks import build_evidence_url_preview
from api.url_safety import (
    CHECK_UNAVAILABLE,
    KNOWN_THREAT,
    NO_KNOWN_THREATS,
    UrlPreviewFetchError,
    UrlPreviewMetadata,
    _public_address_records,
    normalize_url_safety_result,
)


class UrlSafetyFoundationTests(SimpleTestCase):
    def test_basic_validator_rejects_credentials_and_disguised_localhost(self):
        for value in (
            "https://user:secret@example.com/article",
            "http://localhost./admin",
            "http://sub.localhost./admin",
        ):
            with self.subTest(value=value):
                safe_url, error = validate_public_url(value)
                self.assertIsNone(safe_url)
                self.assertIsNotNone(error)

    def test_reputation_states_do_not_call_clear_result_safe(self):
        self.assertEqual(
            normalize_url_safety_result({"status": "SAFE"})["status"],
            NO_KNOWN_THREATS,
        )
        self.assertEqual(
            normalize_url_safety_result({"status": "UNSAFE"})["status"],
            KNOWN_THREAT,
        )
        self.assertEqual(
            normalize_url_safety_result({"status": "UNKNOWN"})["status"],
            CHECK_UNAVAILABLE,
        )

    @patch("api.url_safety.socket.getaddrinfo")
    def test_dns_resolution_rejects_any_private_address(self, getaddrinfo):
        getaddrinfo.return_value = [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("93.184.216.34", 443),
            ),
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("10.0.0.7", 443),
            ),
        ]

        with self.assertRaises(UrlPreviewFetchError) as raised:
            _public_address_records("example.com", 443)

        self.assertEqual(raised.exception.code, "NON_PUBLIC_ADDRESS")

    @patch("api.url_safety.socket.getaddrinfo")
    def test_dns_resolution_preserves_public_socket_target(self, getaddrinfo):
        sockaddr = ("93.184.216.34", 443)
        getaddrinfo.return_value = [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                sockaddr,
            )
        ]

        hostname, records = _public_address_records("example.com", 443)

        self.assertEqual(hostname, "example.com")
        self.assertEqual(records[0][3], sockaddr)


class EvidenceUrlPreviewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="url-preview-contributor",
            password="test-password",
        )
        self.claim = Claim.objects.create(context_text="Preview test claim")
        self.thread = Thread.objects.create(
            claim=self.claim,
            author=self.user,
            caption="Preview test thread",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @patch("api.views.dispatch_evidence_url_preview")
    @patch("api.serializers.check_url_threat_reputation")
    def test_submission_persists_reputation_and_queues_preview_after_commit(
        self,
        check_reputation,
        dispatch_preview,
    ):
        check_reputation.return_value = {
            "status": "SAFE",
            "provider": "GOOGLE_SAFE_BROWSING",
            "threat_types": [],
        }
        url = "https://example.com/source"

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("evidence-list"),
                {
                    "thread_id": str(self.thread.pk),
                    "evidence_caption": "Primary source",
                    "evidence_url": url,
                    "evidence_type": EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION,
                },
                format="json",
            )

        self.assertEqual(response.status_code, 201)
        evidence = EvidenceSubmission.objects.get(pk=response.data["id"])
        self.assertEqual(
            evidence.url_safety_status,
            EvidenceSubmission.UrlSafetyStatus.NO_KNOWN_THREATS,
        )
        self.assertEqual(evidence.url_safety_provider, "GOOGLE_SAFE_BROWSING")
        self.assertIsNotNone(evidence.url_safety_checked_at)
        self.assertEqual(
            evidence.url_preview_status,
            EvidenceSubmission.UrlPreviewStatus.PENDING,
        )
        self.assertEqual(
            response.data["url_safety"]["status"],
            EvidenceSubmission.UrlSafetyStatus.NO_KNOWN_THREATS,
        )
        self.assertEqual(
            response.data["url_preview"]["status"],
            EvidenceSubmission.UrlPreviewStatus.PENDING,
        )
        dispatch_preview.assert_called_once_with(evidence.pk, url)

    @patch("api.serializers.check_url_threat_reputation")
    def test_known_threat_still_blocks_submission(self, check_reputation):
        check_reputation.return_value = {
            "status": "UNSAFE",
            "provider": "GOOGLE_SAFE_BROWSING",
            "threat_types": ["MALWARE"],
        }

        response = self.client.post(
            reverse("evidence-list"),
            {
                "thread_id": str(self.thread.pk),
                "evidence_caption": "Unsafe source",
                "evidence_url": "https://malicious.example/source",
                "evidence_type": EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            EvidenceSubmission.objects.filter(
                evidence_url="https://malicious.example/source",
            ).exists()
        )

    @patch("api.tasks.fetch_url_preview_metadata")
    def test_preview_task_persists_bounded_metadata(self, fetch_metadata):
        evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.user,
            evidence_caption="Preview source",
            evidence_url="https://example.com/source",
            url_safety_status=EvidenceSubmission.UrlSafetyStatus.NO_KNOWN_THREATS,
            url_preview_status=EvidenceSubmission.UrlPreviewStatus.PENDING,
        )
        fetch_metadata.return_value = UrlPreviewMetadata(
            final_url="https://example.com/final",
            title="Example report",
            description="A concise source description.",
            site_name="Example",
        )

        self.assertTrue(
            build_evidence_url_preview.run(
                str(evidence.pk),
                evidence.evidence_url,
            )
        )
        evidence.refresh_from_db()
        self.assertEqual(
            evidence.url_preview_status,
            EvidenceSubmission.UrlPreviewStatus.READY,
        )
        self.assertEqual(evidence.url_preview_title, "Example report")
        self.assertEqual(
            evidence.url_preview_final_url,
            "https://example.com/final",
        )
        self.assertIsNotNone(evidence.url_preview_checked_at)

    @patch("api.tasks.fetch_url_preview_metadata")
    def test_preview_failure_is_non_destructive(self, fetch_metadata):
        evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.user,
            evidence_caption="Blocked fetch target",
            evidence_url="https://example.com/source",
            url_safety_status=EvidenceSubmission.UrlSafetyStatus.CHECK_UNAVAILABLE,
            url_preview_status=EvidenceSubmission.UrlPreviewStatus.PENDING,
        )
        fetch_metadata.side_effect = UrlPreviewFetchError("NON_PUBLIC_ADDRESS")

        self.assertFalse(
            build_evidence_url_preview.run(
                str(evidence.pk),
                evidence.evidence_url,
            )
        )
        evidence.refresh_from_db()
        self.assertEqual(
            evidence.url_preview_status,
            EvidenceSubmission.UrlPreviewStatus.BLOCKED,
        )
        self.assertEqual(
            evidence.url_preview_failure_reason,
            "NON_PUBLIC_ADDRESS",
        )
        self.assertEqual(evidence.evidence_url, "https://example.com/source")

    @patch("api.tasks.fetch_url_preview_metadata")
    def test_stale_preview_job_cannot_overwrite_changed_url(self, fetch_metadata):
        evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.user,
            evidence_caption="Changed source",
            evidence_url="https://example.com/new",
            url_preview_status=EvidenceSubmission.UrlPreviewStatus.PENDING,
        )

        self.assertFalse(
            build_evidence_url_preview.run(
                str(evidence.pk),
                "https://example.com/old",
            )
        )
        fetch_metadata.assert_not_called()
        evidence.refresh_from_db()
        self.assertEqual(
            evidence.url_preview_status,
            EvidenceSubmission.UrlPreviewStatus.PENDING,
        )
