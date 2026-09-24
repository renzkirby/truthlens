import base64
import uuid
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api import notification_service as inbox, publishing_service, tasks
from api.evidence_review_service import review_evidence_submission
from api.models import (
    AccountabilityEvent, Claim, ClaimCheckHistory, EvidenceSubmission, Notification,
    ModerationCase, ModerationEvent, OfficialFactCheck, Organization,
    OrganizationMembership, Thread, VerificationAssignment, VerificationRun,
)
from api.organization_membership_service import (
    change_organization_membership_role, suspend_organization_membership,
    restore_organization_membership, remove_organization_membership,
)
from api.tests.workspace.test_publication_transaction_safety import PublicationTransactionFixtures
from api.tests.workspace.test_factual_correction_handoff import FactualCorrectionHandoffFixtures
from api.tests.workspace.test_factual_correction_request import FactualCorrectionRequestFixtures
from api.verification import runs

Type = Notification.NotificationType


class ThreadCommentNotificationTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(username="thread-notification-author")
        self.commenter = User.objects.create_user(username="thread-notification-commenter")
        self.unrelated = User.objects.create_user(username="thread-notification-unrelated")
        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="A community claim with a discussion.",
        )
        self.thread = Thread.objects.create(
            claim=self.claim,
            author=self.author,
            caption="Discuss this claim.",
        )
        self.client = APIClient()

    def post_comment(self, user, text="A useful comment"):
        self.client.force_authenticate(user)
        return self.client.post(
            reverse("comment-list"),
            {"thread_id": str(self.thread.pk), "comment_text": text},
            format="json",
        )

    def test_comment_notifies_only_thread_author_after_commit_and_dedupes(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_comment(self.commenter)
            self.assertEqual(response.status_code, 201, response.content)
            self.assertFalse(Notification.objects.exists())

        comment = self.thread.comments.get(pk=response.data["id"])
        row = Notification.objects.get()
        self.assertEqual(row.recipient, self.author)
        self.assertEqual(row.actor, self.commenter)
        self.assertEqual(row.notification_type, Type.THREAD_COMMENTED)
        self.assertEqual(row.target_type, Notification.TargetType.THREAD)
        self.assertEqual(row.target_id, self.thread.pk)
        self.assertEqual(row.title, "New comment on your discussion")
        self.assertEqual(
            row.message,
            "thread-notification-commenter commented on your discussion.",
        )
        self.assertNotIn("A useful comment", row.message)
        self.assertFalse(Notification.objects.filter(recipient=self.unrelated).exists())
        self.assertEqual(inbox.notify_thread_commented(comment).pk, row.pk)
        self.assertEqual(Notification.objects.count(), 1)

    def test_commenter_does_not_notify_themselves(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_comment(self.author)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertFalse(Notification.objects.exists())

    def test_notification_failure_does_not_fail_comment_creation(self):
        with patch.object(
            inbox,
            "create_notification_once",
            side_effect=RuntimeError("notification unavailable"),
        ):
            with self.assertLogs("api.notification_service", level="ERROR"):
                with self.captureOnCommitCallbacks(execute=True):
                    response = self.post_comment(self.commenter, "Still persists")

        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(
            self.thread.comments.filter(
                commenter=self.commenter,
                comment_text="Still persists",
            ).exists()
        )
        self.assertFalse(Notification.objects.exists())


class EvidenceReviewNotificationTests(TestCase):
    def setUp(self):
        self.contributor = User.objects.create_user(username="evidence-notification-contributor")
        self.reviewer = User.objects.create_user(username="evidence-notification-reviewer")
        self.organization = Organization.objects.create(
            name="Evidence Notification Partner",
            slug="evidence-notification-partner",
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.reviewer,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Evidence notification claim.",
        )
        self.thread = Thread.objects.create(
            claim=self.claim,
            author=self.contributor,
            caption="Evidence notification thread.",
        )
        VerificationAssignment.objects.create(
            claim=self.claim,
            organization=self.organization,
            claimed_by=self.reviewer,
            status=VerificationAssignment.Status.ACTIVE,
            claimed_at=timezone.now(),
        )

    def make_evidence(self, suffix):
        evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.contributor,
            evidence_caption=f"Evidence {suffix}",
        )
        case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=evidence,
            organization=self.organization,
            source=ModerationCase.Source.EVIDENCE_SUBMISSION,
        )
        return evidence, case

    def review(self, evidence, case, decision, **overrides):
        values = {
            "evidence": evidence,
            "actor": self.reviewer,
            "evidence_status": decision,
            "expected_status": evidence.evidence_status,
            "expected_case_id": case.pk,
            "expected_organization_id": self.organization.pk,
            "allow_reopen": True,
        }
        values.update(overrides)
        return review_evidence_submission(**values)

    def test_verified_and_rejected_transitions_are_safe_targeted_and_retry_stable(self):
        decisions = (
            (
                EvidenceSubmission.EvidenceStatus.VERIFIED,
                "verified evidence you submitted",
                None,
            ),
            (
                EvidenceSubmission.EvidenceStatus.REJECTED,
                "rejected evidence you submitted",
                EvidenceSubmission.RejectionReason.IRRELEVANT,
            ),
        )
        for index, (decision, wording, rejection_reason) in enumerate(decisions):
            with self.subTest(decision=decision):
                evidence, case = self.make_evidence(index)
                private_notes = f"PRIVATE review note {index}"
                notification_count = Notification.objects.count()
                with self.captureOnCommitCallbacks(execute=True):
                    result = self.review(
                        evidence,
                        case,
                        decision,
                        moderator_notes=private_notes,
                        rejection_reason=rejection_reason,
                    )
                    self.assertEqual(Notification.objects.count(), notification_count)

                row = Notification.objects.get(
                    target_id=evidence.thread_id,
                    message__contains=wording,
                )
                self.assertEqual(row.recipient, self.contributor)
                self.assertEqual(row.actor, self.reviewer)
                self.assertEqual(row.notification_type, Type.EVIDENCE_REVIEWED)
                self.assertEqual(row.target_type, Notification.TargetType.THREAD)
                self.assertIn(wording, row.message)
                self.assertNotIn("PRIVATE", row.message)
                if rejection_reason:
                    self.assertNotIn(rejection_reason, row.message)
                event = ModerationEvent.objects.get(
                    case=result["case"],
                    event_type=(
                        ModerationEvent.EventType.EVIDENCE_VERIFIED
                        if decision == EvidenceSubmission.EvidenceStatus.VERIFIED
                        else ModerationEvent.EventType.EVIDENCE_REJECTED
                    ),
                )
                retried = inbox.notify_evidence_reviewed(
                    result["evidence"],
                    actor_id=self.reviewer.pk,
                    event_id=event.pk,
                    previous_status=EvidenceSubmission.EvidenceStatus.UNVERIFIED,
                    new_status=decision,
                )
                self.assertEqual(retried.pk, row.pk)
        self.assertEqual(Notification.objects.count(), 2)

    def test_helper_suppresses_contributor_self_notification(self):
        evidence, _case = self.make_evidence("self-suppression")
        self.assertIsNone(
            inbox.notify_evidence_reviewed(
                evidence,
                actor_id=self.contributor.pk,
                event_id=uuid.uuid4(),
                previous_status=EvidenceSubmission.EvidenceStatus.UNVERIFIED,
                new_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
            )
        )
        self.assertFalse(Notification.objects.exists())

    def test_delivery_failure_does_not_undo_authoritative_review(self):
        evidence, case = self.make_evidence("delivery-failure")
        with patch.object(
            inbox,
            "create_notification_once",
            side_effect=RuntimeError("notification unavailable"),
        ):
            with self.assertLogs("api.notification_service", level="ERROR"):
                with self.captureOnCommitCallbacks(execute=True):
                    result = self.review(
                        evidence,
                        case,
                        EvidenceSubmission.EvidenceStatus.REJECTED,
                        rejection_reason=EvidenceSubmission.RejectionReason.OUTDATED,
                    )

        result["evidence"].refresh_from_db()
        result["case"].refresh_from_db()
        self.assertEqual(
            result["evidence"].evidence_status,
            EvidenceSubmission.EvidenceStatus.REJECTED,
        )
        self.assertEqual(result["case"].status, ModerationCase.Status.RESOLVED)
        self.assertTrue(
            ModerationEvent.objects.filter(
                case=result["case"],
                event_type=ModerationEvent.EventType.EVIDENCE_REJECTED,
            ).exists()
        )
        self.assertFalse(Notification.objects.exists())


class CorrectionEvidenceReviewNotificationTests(
    FactualCorrectionRequestFixtures,
    TestCase,
):
    def test_correction_transition_notifies_and_both_reaffirmations_are_suppressed(self):
        rejected = self.make_correction_review_context(suffix="notification-rejected")
        with self.captureOnCommitCallbacks(execute=True):
            result = self.review_correction(
                rejected,
                evidence_status=EvidenceSubmission.EvidenceStatus.REJECTED,
                rejection_reason=EvidenceSubmission.RejectionReason.OUTDATED,
                moderator_notes="PRIVATE correction rejection details",
            )
            self.assertFalse(Notification.objects.exists())

        row = Notification.objects.get()
        self.assertEqual(row.recipient, self.contributor)
        self.assertEqual(row.actor, self.moderator)
        self.assertEqual(row.target_id, rejected["thread"].pk)
        self.assertIn("rejected evidence you submitted", row.message)
        self.assertNotIn("PRIVATE", row.message)
        self.assertNotIn(EvidenceSubmission.RejectionReason.OUTDATED, row.message)
        self.assertEqual(
            inbox.notify_evidence_reviewed(
                result["evidence"],
                actor_id=self.moderator.pk,
                event_id=result["event"].pk,
                previous_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
                new_status=EvidenceSubmission.EvidenceStatus.REJECTED,
            ).pk,
            row.pk,
        )

        with self.captureOnCommitCallbacks(execute=True):
            rejected_reaffirmation = self.review_correction(
                rejected,
                evidence_status=EvidenceSubmission.EvidenceStatus.REJECTED,
                expected_evidence_status=EvidenceSubmission.EvidenceStatus.REJECTED,
                rejection_reason=EvidenceSubmission.RejectionReason.OUTDATED,
            )
        self.assertFalse(result["event"].metadata["is_reaffirmation"])
        self.assertNotEqual(result["event"].pk, rejected_reaffirmation["event"].pk)
        self.assertTrue(rejected_reaffirmation["event"].metadata["is_reaffirmation"])
        self.assertEqual(
            ModerationEvent.objects.filter(
                case=rejected["evidence_case"],
                event_type=ModerationEvent.EventType.EVIDENCE_REJECTED,
                metadata__correction_request_id=str(rejected["correction_request"].pk),
            ).count(),
            2,
        )
        self.assertEqual(Notification.objects.count(), 1)

        verified = self.make_correction_review_context(suffix="notification-verified")
        with self.captureOnCommitCallbacks(execute=True):
            first_verified_reaffirmation = self.review_correction(verified)
            second_verified_reaffirmation = self.review_correction(verified)
        self.assertNotEqual(
            first_verified_reaffirmation["event"].pk,
            second_verified_reaffirmation["event"].pk,
        )
        self.assertTrue(
            first_verified_reaffirmation["event"].metadata["is_reaffirmation"]
        )
        self.assertTrue(
            second_verified_reaffirmation["event"].metadata["is_reaffirmation"]
        )
        self.assertEqual(
            ModerationEvent.objects.filter(
                case=verified["evidence_case"],
                event_type=ModerationEvent.EventType.EVIDENCE_VERIFIED,
                metadata__correction_request_id=str(verified["correction_request"].pk),
            ).count(),
            2,
        )
        self.assertEqual(Notification.objects.count(), 1)

    def test_correction_delivery_failure_preserves_review_state(self):
        context = self.make_correction_review_context(suffix="notification-failure")
        with patch.object(
            inbox,
            "create_notification_once",
            side_effect=RuntimeError("notification unavailable"),
        ):
            with self.assertLogs("api.notification_service", level="ERROR"):
                with self.captureOnCommitCallbacks(execute=True):
                    result = self.review_correction(
                        context,
                        evidence_status=EvidenceSubmission.EvidenceStatus.REJECTED,
                        rejection_reason=EvidenceSubmission.RejectionReason.OUTDATED,
                    )

        result["evidence"].refresh_from_db()
        result["case"].refresh_from_db()
        result["event"].refresh_from_db()
        self.assertEqual(
            result["evidence"].evidence_status,
            EvidenceSubmission.EvidenceStatus.REJECTED,
        )
        self.assertEqual(result["case"].status, ModerationCase.Status.RESOLVED)
        self.assertFalse(result["event"].metadata["is_reaffirmation"])
        self.assertFalse(Notification.objects.exists())


class VerificationNotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="analysis-recipient")
        self.claim = Claim.objects.create(claim_type=Claim.ClaimType.TEXT, context_text="Test claim")

    def started(self, user=True):
        return runs.start_verification_run(runs.create_verification_run(
            self.claim, triggered_by=self.user if user else None,
        ))

    def test_completed_abstained_and_failed_are_safe_and_idempotent(self):
        transitions = (
            (runs.complete_verification_run, {}, Type.AUTOMATED_VERIFICATION_COMPLETED),
            (runs.abstain_verification_run, {}, Type.AUTOMATED_VERIFICATION_COMPLETED),
            (runs.fail_verification_run, {"failure_message": "SECRET provider stack trace"}, Type.AUTOMATED_VERIFICATION_FAILED),
        )
        for transition, kwargs, expected in transitions:
            with self.subTest(transition=transition.__name__):
                run = self.started()
                with self.captureOnCommitCallbacks(execute=True):
                    run = transition(run, **kwargs)
                    self.assertFalse(Notification.objects.filter(dedupe_key=f"verification-run:{run.pk}:finished").exists())
                row = Notification.objects.get(dedupe_key=f"verification-run:{run.pk}:finished")
                self.assertEqual(row.recipient, self.user)
                self.assertEqual(row.target_id, self.claim.pk)
                self.assertEqual(row.notification_type, expected)
                self.assertNotIn("SECRET", row.message)
                if transition == runs.abstain_verification_run:
                    self.assertIn("without enough evidence", row.message)
                self.assertEqual(inbox.notify_verification_finished(run).pk, row.pk)
        self.assertEqual(Notification.objects.count(), 3)

    def test_guests_and_cancelled_runs_do_not_notify(self):
        with self.captureOnCommitCallbacks(execute=True):
            for transition in (runs.complete_verification_run, runs.abstain_verification_run, runs.fail_verification_run):
                transition(self.started(user=False))
            cancelled = runs.cancel_verification_run(self.started())
            inbox.notify_verification_finished(cancelled)
        self.assertFalse(Notification.objects.exists())

    def test_completion_does_not_fabricate_a_claim_verdict(self):
        with self.captureOnCommitCallbacks(execute=True):
            runs.complete_verification_run(self.started())
        self.claim.refresh_from_db()
        self.assertIsNone(self.claim.final_verdict)
        self.assertIsNone(self.claim.ai_verdict)
        self.assertIn("Open the results", Notification.objects.get().message)

    def test_delivery_failure_preserves_lifecycle_result(self):
        run = self.started()
        with patch.object(inbox, "create_notification_once", side_effect=RuntimeError("delivery")):
            with self.assertLogs("api.notification_service", level="ERROR"):
                with self.captureOnCommitCallbacks(execute=True):
                    runs.complete_verification_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, VerificationRun.Status.COMPLETED)
        self.assertIsNone(run.failure_message)

    def test_rollback_discards_terminal_notification(self):
        run = self.started()
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError), transaction.atomic():
                runs.complete_verification_run(run)
                raise RuntimeError("rollback")
        run.refresh_from_db()
        self.assertEqual(run.status, VerificationRun.Status.RUNNING)
        self.assertFalse(Notification.objects.exists())


class VerificationAttributionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="attribution-user")
        self.enterContext(patch("api.claim_matching.compute_fingerprint", return_value=None))
        self.enterContext(patch("api.claim_matching.find_matching_claim", return_value=None))
        self.enterContext(patch("api.tasks.clean_ocr_text", return_value={"cleaned_claim": "OUT_OF_SCOPE"}))
        self.enterContext(patch("api.tasks.extract_text_from_image", return_value="Extracted claim"))
        response = Mock(status_code=200)
        response.json.return_value = {"results": [{"raw_content": "Article text"}]}
        self.enterContext(patch("api.tasks.requests.post", return_value=response))
        self.enterContext(patch("api.tasks.clean_extracted_text", return_value="Article text"))
        self.enterContext(patch("api.tasks.extract_search_query", return_value={"cleaned_claim": "OUT_OF_SCOPE"}))

    def test_all_worker_paths_preserve_user_guest_and_deleted_attribution(self):
        deleted = User.objects.create_user(username="deleted-requester")
        deleted_id = deleted.pk
        deleted.delete()
        for identity in (self.user.pk, None, deleted_id):
            for path in ("core", "text", "snippet", "url"):
                with self.subTest(identity=identity, path=path):
                    claim = Claim.objects.create(claim_type=Claim.ClaimType.TEXT, context_text="Input")
                    with self.captureOnCommitCallbacks(execute=True):
                        if path == "core":
                            tasks.execute_core_text_pipeline("Input", claim.pk, triggered_by_id=identity)
                        elif path == "text":
                            tasks.text_fact_check_process.run("Input", claim.pk, triggered_by_id=identity)
                        elif path == "snippet":
                            tasks.snippet_fact_check_process.run("hash", claim.pk,
                                base64_string=base64.b64encode(b"image").decode(), triggered_by_id=identity)
                        else:
                            tasks.url_fact_check_process.run("https://example.com", claim.pk, triggered_by_id=identity)
                    run = claim.verification_runs.get()
                    self.assertEqual(run.triggered_by_id, self.user.pk if identity == self.user.pk else None)
                    self.assertEqual(run.status, VerificationRun.Status.ABSTAINED)
                    self.assertEqual(Notification.objects.filter(target_id=claim.pk).count(), int(identity == self.user.pk))

    def test_legacy_worker_call_without_attribution_remains_supported(self):
        claim = Claim.objects.create(claim_type=Claim.ClaimType.TEXT)
        tasks.text_fact_check_process.run("Input", claim.pk)
        self.assertIsNone(claim.verification_runs.get().triggered_by_id)

    def test_api_paths_forward_authenticated_identity_and_guest_none(self):
        client = APIClient()
        self.enterContext(patch("api.views.compute_fingerprint", return_value=None))
        self.enterContext(patch("api.views.find_matching_claim", return_value=None))
        self.enterContext(patch("api.views.process_image", return_value=("hash", None)))
        self.enterContext(patch("api.views.upload_image_to_database", return_value="https://example.com/image"))
        self.enterContext(patch("api.views.validate_public_url", return_value=("https://example.com", None)))
        self.enterContext(patch("api.views.check_url_threat_reputation", return_value={"status": "SAFE"}))
        for user in (self.user, None):
            client.force_authenticate(user)
            for route, payload, task in (
                ("verify_text", {"text": "Claim text"}, "text_fact_check_process"),
                ("verify_url", {"url": "https://example.com"}, "url_fact_check_process"),
                ("analyze_snippet", {"image_data": "data:image/png;base64,AAA"}, "snippet_fact_check_process"),
                ("verify_file", {"file_data": base64.b64encode(b"Document claim").decode(), "file_name": "claim.txt"}, "text_fact_check_process"),
            ):
                with self.subTest(user=user, route=route), patch(f"api.views.{task}.delay") as delay:
                    cache.clear()
                    result = client.post(reverse(route), payload, format="json")
                    self.assertEqual(result.status_code, 200, result.content)
                    self.assertEqual(delay.call_args.kwargs["triggered_by_id"], user.pk if user else None)


class PublicationNotificationTests(PublicationTransactionFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.publisher = User.objects.create_user(username="notification-publisher")
        OrganizationMembership.objects.create(organization=self.organization, user=self.publisher,
            role=OrganizationMembership.Role.LEAD_VERIFIER, status=OrganizationMembership.Status.ACTIVE)
        self.enterContext(patch("api.publishing_service._queue_fact_check_index"))

    def submitted(self, *, source=True, author=None):
        context = self.make_decided_context()
        if author:
            context["thread"].author = author
            context["thread"].save(update_fields=["author"])
        draft = self.make_draft(context)
        if source:
            draft.source_thread = context["thread"]
            draft.save(update_fields=["source_thread"])
        context["draft"] = publishing_service.submit_fact_check_for_review(
            fact_check=draft, actor=self.lead, organization_id=self.organization.pk,
            expected_edit_generation=draft.edit_generation,
            expected_decision_revision=context["decision"].revision_number,
        )
        return context

    def publish(self, context, **kwargs):
        return publishing_service.publish_fact_check(
            fact_check=context["draft"], actor=kwargs.get("actor", self.publisher),
            organization_id=self.organization.pk,
            expected_edit_generation=context["draft"].edit_generation,
            expected_decision_revision=context["decision"].revision_number,
        )["fact_check"]

    def test_only_successful_publication_notifies_author_and_drafter(self):
        with self.captureOnCommitCallbacks(execute=True):
            context = self.submitted()
        self.assertFalse(Notification.objects.exists())
        ClaimCheckHistory.objects.create(user=self.contributor, claim=context["claim"])
        with self.captureOnCommitCallbacks(execute=True):
            published = self.publish(context)
            self.assertFalse(Notification.objects.exists())
        self.assertEqual(set(Notification.objects.values_list("recipient_id", "notification_type")), {
            (self.author.pk, Type.PARTNER_FACT_CHECK_PUBLISHED),
            (self.lead.pk, Type.FACT_CHECK_PUBLISHED),
        })
        self.assertEqual(set(Notification.objects.values_list("target_id", flat=True)), {published.pk})
        inbox.notify_fact_check_published(published, actor_id=self.publisher.pk)
        self.assertEqual(Notification.objects.count(), 2)

    def test_missing_source_thread_does_not_notify_claim_history(self):
        context = self.submitted(source=False)
        ClaimCheckHistory.objects.create(user=self.author, claim=context["claim"])
        with self.captureOnCommitCallbacks(execute=True):
            self.publish(context)
        self.assertEqual(Notification.objects.get().recipient, self.lead)

    def test_workspace_role_wins_when_source_author_is_drafter(self):
        context = self.submitted(author=self.lead)
        with self.captureOnCommitCallbacks(execute=True):
            self.publish(context)
        self.assertEqual(Notification.objects.get().notification_type, Type.FACT_CHECK_PUBLISHED)

    def test_publishing_actor_is_suppressed_in_both_roles(self):
        context = self.submitted(author=self.lead)
        with self.captureOnCommitCallbacks(execute=True):
            self.publish(context, actor=self.lead)
        self.assertFalse(Notification.objects.exists())

    def test_outer_rollback_discards_success_notification(self):
        context = self.submitted()
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError), transaction.atomic():
                self.publish(context)
                raise RuntimeError("rollback publication")
        context["draft"].refresh_from_db()
        self.assertEqual(context["draft"].publication_status, OfficialFactCheck.PublicationStatus.IN_REVIEW)
        self.assertFalse(Notification.objects.exists())

    def test_failed_publication_does_not_notify(self):
        context = self.submitted()
        with patch("api.publishing_service._validate_publication_content", side_effect=RuntimeError("invalid")):
            with self.captureOnCommitCallbacks(execute=True), self.assertRaises(RuntimeError):
                self.publish(context)
        self.assertFalse(Notification.objects.exists())

    def test_delivery_failure_preserves_successful_publication(self):
        context = self.submitted()
        with patch.object(inbox, "create_notification_once", side_effect=RuntimeError("delivery")):
            with self.assertLogs("api.notification_service", level="ERROR"):
                with self.captureOnCommitCallbacks(execute=True):
                    published = self.publish(context)
        published.refresh_from_db()
        self.assertEqual(published.publication_status, OfficialFactCheck.PublicationStatus.PUBLISHED)
        self.assertIsNotNone(published.publication_snapshot)

    def test_rework_is_private_and_repeated_real_cycles_have_distinct_events(self):
        context = self.submitted()
        for _ in range(2):
            with self.captureOnCommitCallbacks(execute=True):
                draft = publishing_service.return_fact_check_for_rework(
                    fact_check=context["draft"], actor=self.publisher, organization_id=self.organization.pk,
                    expected_edit_generation=context["draft"].edit_generation, reason="PRIVATE detailed rework notes",
                )
            inbox.notify_article_returned_for_rework(draft, actor_id=self.publisher.pk)
            context["draft"] = publishing_service.submit_fact_check_for_review(
                fact_check=draft, actor=self.lead, organization_id=self.organization.pk,
                expected_edit_generation=draft.edit_generation,
                expected_decision_revision=context["decision"].revision_number,
            )
        self.assertEqual(Notification.objects.count(), 2)
        for row in Notification.objects.all():
            self.assertEqual(row.recipient, self.lead)
            self.assertEqual(row.notification_type, Type.ARTICLE_RETURNED_FOR_REWORK)
            self.assertEqual(inbox.notification_destination(row), "/workspace")
            self.assertNotIn("PRIVATE", row.message)


class CorrectionNotificationTests(FactualCorrectionHandoffFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.enterContext(patch("api.publishing_service._queue_fact_check_index"))

    def make_published_context(self, *, suffix="initial"):
        # Establish the legitimate thread link before the immutable publication seal.
        original = publishing_service.create_fact_check_draft
        def linked_draft(**kwargs):
            draft = original(**kwargs)
            draft.source_thread = draft.claim.threads.first()
            draft.save(update_fields=["source_thread"])
            return draft
        with patch("api.tests.workspace.test_editorial_revision_publication.create_fact_check_draft", side_effect=linked_draft):
            return super().make_published_context(suffix=suffix)

    def test_correction_notifies_source_author_and_distinct_workspace_recipient(self):
        context = self.make_prepared_context()
        self.assertEqual(context["correction_request"].requested_by_id, self.lead.pk)
        self.assertEqual(context["prepared_proposal"].prepared_by_id, self.lead.pk)
        with self.captureOnCommitCallbacks(execute=True):
            result = self.handoff(context)
            self.assertFalse(Notification.objects.exists())
        self.assertEqual(set(Notification.objects.values_list("recipient_id", "notification_type")), {
            (self.author.pk, Type.PARTNER_FACT_CHECK_CORRECTED),
            (self.lead.pk, Type.FACTUAL_CORRECTION_PUBLISHED),
        })
        self.assertEqual(set(Notification.objects.values_list("target_id", flat=True)), {result["fact_check"].pk})
        inbox.notify_factual_correction_published(result["fact_check"], actor_id=self.publisher.pk,
            workspace_recipient_ids=(self.lead.pk, self.lead.pk))
        self.assertEqual(Notification.objects.count(), 2)

    def test_correction_distinct_requester_and_preparer_are_both_notified(self):
        context = self.make_proposal_context()
        proposal = self.save_proposal(context)
        context["prepared_proposal"] = self.prepare_proposal(context, proposal, actor=self.moderator)["proposal"]
        with self.captureOnCommitCallbacks(execute=True):
            self.handoff(context)
        self.assertEqual(set(Notification.objects.filter(notification_type=Type.FACTUAL_CORRECTION_PUBLISHED)
                             .values_list("recipient_id", flat=True)), {self.lead.pk, self.moderator.pk})

    def test_correction_publisher_self_notification_is_suppressed(self):
        context = self.make_prepared_context()
        with self.captureOnCommitCallbacks(execute=True):
            self.handoff(context, actor=self.lead)
        self.assertEqual(Notification.objects.get().recipient, self.author)

    def test_correction_workspace_role_takes_precedence_over_source_author(self):
        context = self.make_prepared_context()
        thread = context["published"].source_thread
        thread.author = self.lead
        thread.save(update_fields=["author"])
        with self.captureOnCommitCallbacks(execute=True):
            self.handoff(context)
        self.assertEqual(Notification.objects.get().notification_type, Type.FACTUAL_CORRECTION_PUBLISHED)

    def test_correction_follows_original_thread_through_editorial_predecessor(self):
        context = self.make_prepared_context(editorial_first=True)
        self.assertIsNone(context["published"].source_thread_id)
        with self.captureOnCommitCallbacks(execute=True):
            self.handoff(context)
        self.assertTrue(Notification.objects.filter(recipient=self.author,
            notification_type=Type.PARTNER_FACT_CHECK_CORRECTED).exists())

    def test_correction_rollback_discards_notifications(self):
        context = self.make_prepared_context()
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError), transaction.atomic():
                self.handoff(context)
                raise RuntimeError("rollback correction")
        self.assertFalse(Notification.objects.exists())
        context["published"].refresh_from_db()
        self.assertEqual(context["published"].publication_status, OfficialFactCheck.PublicationStatus.PUBLISHED)

    def test_delivery_failure_preserves_authoritative_correction(self):
        context = self.make_prepared_context()
        with patch.object(inbox, "create_notification_once", side_effect=RuntimeError("delivery")):
            with self.assertLogs("api.notification_service", level="ERROR"):
                with self.captureOnCommitCallbacks(execute=True):
                    result = self.handoff(context)
        successor = result["fact_check"]
        successor.refresh_from_db()
        context["published"].refresh_from_db()
        context["correction_request"].refresh_from_db()
        context["claim"].refresh_from_db()
        result["decision"].refresh_from_db()
        self.assertEqual(successor.publication_status, OfficialFactCheck.PublicationStatus.PUBLISHED)
        self.assertEqual(context["published"].publication_status, OfficialFactCheck.PublicationStatus.ARCHIVED)
        self.assertEqual(context["correction_request"].status, context["correction_request"].Status.COMPLETED)
        self.assertTrue(result["decision"].is_current)
        self.assertEqual(context["claim"].final_verdict, result["decision"].verdict)
        self.assertEqual(successor.publication_snapshot.pk, result["publication_snapshot"].pk)
        self.assertFalse(Notification.objects.exists())

    def test_editorial_rework_and_publication_notify_drafter(self):
        context = self.make_published_context()
        revision = self.make_submitted_revision(context)
        with self.captureOnCommitCallbacks(execute=True):
            revision = publishing_service.return_editorial_revision_for_rework(
                revision=revision, actor=self.publisher, organization_id=self.organization.pk,
                expected_edit_generation=revision.edit_generation, reason="PRIVATE rework notes",
            )
        row = Notification.objects.get()
        self.assertEqual(row.notification_type, Type.ARTICLE_RETURNED_FOR_REWORK)
        self.assertEqual(row.recipient, self.lead)
        self.assertNotIn("PRIVATE", row.message)
        revision = publishing_service.submit_fact_check_for_review(
            fact_check=revision, actor=self.lead, organization_id=self.organization.pk,
            expected_edit_generation=revision.edit_generation,
            expected_decision_revision=context["decision"].revision_number,
        )
        with self.captureOnCommitCallbacks(execute=True):
            self.replace(context, revision, actor=self.publisher)
        self.assertEqual(Notification.objects.filter(recipient=self.lead,
            notification_type=Type.FACT_CHECK_PUBLISHED).count(), 1)


class MembershipNotificationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="membership-notification-owner")
        self.user = User.objects.create_user(username="membership-notification-member")
        self.organization = Organization.objects.create(name="Partner", slug="notification-partner",
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE)
        OrganizationMembership.objects.create(organization=self.organization, user=self.owner,
            role=OrganizationMembership.Role.OWNER, status=OrganizationMembership.Status.ACTIVE)
        self.membership = OrganizationMembership.objects.create(organization=self.organization, user=self.user,
            role=OrganizationMembership.Role.CONTRIBUTOR, status=OrganizationMembership.Status.ACTIVE)

    def change(self, service, **kwargs):
        return service(organization=self.organization, membership_id=self.membership.pk, actor=self.owner, **kwargs)

    def test_role_suspend_restore_and_remove_notify_affected_user(self):
        transitions = (
            (change_organization_membership_role, {"role": OrganizationMembership.Role.RESEARCHER}, "role has changed"),
            (suspend_organization_membership, {}, "suspended"),
            (restore_organization_membership, {}, "restored"),
            (suspend_organization_membership, {}, "suspended"),
            (restore_organization_membership, {}, "restored"),
            (remove_organization_membership, {}, "removed"),
        )
        for index, (service, kwargs, message) in enumerate(transitions):
            with self.captureOnCommitCallbacks(execute=True):
                self.change(service, **kwargs)
                self.assertEqual(Notification.objects.count(), index)
            row = Notification.objects.first()
            self.assertEqual(row.recipient, self.user)
            self.assertEqual(row.actor, self.owner)
            self.assertEqual(row.organization, self.organization)
            self.assertIn(message, row.message)
            self.assertEqual(row.notification_type, Type.ORGANIZATION_MEMBERSHIP_CHANGED)
            self.assertIsNone(inbox.notification_destination(row))
        self.assertEqual(Notification.objects.count(), 6)

    def test_membership_retry_dedupes_and_account_state_allows_self_notification(self):
        with self.captureOnCommitCallbacks(execute=True):
            membership = self.change(suspend_organization_membership)
        event = AccountabilityEvent.objects.get(action_type=AccountabilityEvent.ActionType.ORGANIZATION_MEMBERSHIP_SUSPENDED)
        inbox.notify_membership_changed(membership, actor_id=self.owner.pk, event_id=event.pk, change="suspended")
        self.assertEqual(Notification.objects.count(), 1)
        row = inbox.notify_membership_changed(membership, actor_id=self.user.pk,
            event_id="self-account-event", change="restored")
        self.assertEqual(row.recipient_id, row.actor_id)

    def test_membership_rollback_discards_notification(self):
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError), transaction.atomic():
                self.change(suspend_organization_membership)
                raise RuntimeError("rollback membership")
        self.assertFalse(Notification.objects.exists())
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.status, OrganizationMembership.Status.ACTIVE)

    def test_delivery_failure_preserves_membership_action(self):
        with patch.object(inbox, "create_notification_once", side_effect=RuntimeError("delivery")):
            with self.assertLogs("api.notification_service", level="ERROR"):
                with self.captureOnCommitCallbacks(execute=True):
                    self.change(suspend_organization_membership)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.status, OrganizationMembership.Status.SUSPENDED)
