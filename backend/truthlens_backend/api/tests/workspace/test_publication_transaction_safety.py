import threading
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase

from api.models import (
    AdjudicationDecision,
    Claim,
    EvidenceSubmission,
    ModerationEvent,
    OfficialFactCheck,
    OrganizationMembership,
    VerificationAssignment,
)
from api.publishing_service import (
    PublishingAuthorizationError,
    PublishingConflict,
    create_fact_check_draft,
    publish_fact_check,
    submit_fact_check_for_review,
    update_fact_check_draft,
)
from api.tests.adjudication.test_adjudication_transaction_contract import (
    AdjudicationContractFixtures,
)
from api.verification_assignment_service import (
    VerificationAssignmentConflict,
    VerificationAssignmentReleaseBlocked,
    complete_verification_assignment,
    release_verification_assignment,
)


class PublicationTransactionFixtures(AdjudicationContractFixtures):
    def make_decided_context(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        context["decision"] = self.issue(context)["decision"]
        return context

    def make_draft(self, context, *, suffix="default"):
        return create_fact_check_draft(
            decision=context["decision"],
            actor=self.lead,
            headline=f"Fact Check {suffix}",
            summary="A professional summary of the reviewed claim.",
            article_body="The article explains the reviewed evidence.",
            source_urls=[f"https://example.com/publication-{suffix}"],
        )

    def make_submitted_draft(self, context, *, suffix="default"):
        return submit_fact_check_for_review(
            fact_check=self.make_draft(context, suffix=suffix),
            actor=self.lead,
        )

    def create_test_revision(self, context):
        current = AdjudicationDecision.objects.get(pk=context["decision"].pk)
        current.is_current = False
        current.save(update_fields=["is_current"])
        replacement = AdjudicationDecision.objects.create(
            claim=context["claim"],
            moderation_case=context["case"],
            verdict=AdjudicationDecision.Verdict.MISLEADING,
            canonical_claim="The reviewed claim requires additional context.",
            rationale="Test-only historical revision state.",
            decided_by=self.lead,
            organization=self.organization,
            revision_number=2,
            supersedes=current,
            is_current=True,
        )
        Claim.objects.filter(pk=context["claim"].pk).update(
            final_verdict=replacement.verdict
        )
        return replacement


class PublicationTransactionSafetyTests(
    PublicationTransactionFixtures,
    TestCase,
):
    def test_first_publication_completes_the_active_assignment(self):
        context = self.make_decided_context()
        submitted = self.make_submitted_draft(context, suffix="first")

        result = publish_fact_check(
            fact_check=submitted,
            actor=self.lead,
        )

        context["assignment"].refresh_from_db()
        self.assertEqual(
            result["fact_check"].publication_status,
            OfficialFactCheck.PublicationStatus.PUBLISHED,
        )
        self.assertIsNone(result["archived_fact_check"])
        self.assertEqual(
            context["assignment"].status,
            VerificationAssignment.Status.COMPLETED,
        )
        self.assertIsNotNone(context["assignment"].completed_at)

    def test_stale_decision_identity_cannot_create_a_draft(self):
        context = self.make_decided_context()
        self.create_test_revision(context)

        with self.assertRaises(PublishingConflict):
            self.make_draft(context, suffix="stale-create")

        self.assertFalse(
            OfficialFactCheck.objects.filter(claim=context["claim"]).exists()
        )

    def test_stale_decision_cannot_edit_an_existing_draft(self):
        context = self.make_decided_context()
        draft = self.make_draft(context, suffix="stale-edit")
        self.create_test_revision(context)

        with self.assertRaises(PublishingConflict):
            update_fact_check_draft(
                fact_check=draft,
                actor=self.lead,
                headline="Unsafe stale edit",
            )

        draft.refresh_from_db()
        self.assertNotEqual(draft.headline, "Unsafe stale edit")

    def test_stale_decision_cannot_publish_an_existing_article(self):
        context = self.make_decided_context()
        submitted = self.make_submitted_draft(context, suffix="stale-publish")
        self.create_test_revision(context)

        with self.assertRaises(PublishingConflict):
            publish_fact_check(
                fact_check=submitted,
                actor=self.lead,
            )

        submitted.refresh_from_db()
        self.assertEqual(
            submitted.publication_status,
            OfficialFactCheck.PublicationStatus.IN_REVIEW,
        )

    def test_assignment_organization_change_blocks_draft_submission(self):
        context = self.make_decided_context()
        draft = self.make_draft(context, suffix="assignment-change")
        OrganizationMembership.objects.create(
            organization=self.other_organization,
            user=self.lead,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        VerificationAssignment.objects.filter(pk=context["assignment"].pk).update(
            organization=self.other_organization
        )

        with self.assertRaises(PublishingConflict):
            submit_fact_check_for_review(
                fact_check=draft,
                actor=self.lead,
            )

        draft.refresh_from_db()
        self.assertEqual(
            draft.publication_status,
            OfficialFactCheck.PublicationStatus.DRAFT,
        )

    def test_other_organization_capability_does_not_authorize_drafting(self):
        context = self.make_decided_context()
        OrganizationMembership.objects.create(
            organization=self.other_organization,
            user=self.author,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )

        with self.assertRaises(PublishingAuthorizationError):
            create_fact_check_draft(
                decision=context["decision"],
                actor=self.author,
                headline="Cross-organization draft",
                summary="This action must remain organization-scoped.",
            )

        self.assertFalse(
            OfficialFactCheck.objects.filter(claim=context["claim"]).exists()
        )

    def test_revoked_draft_authority_blocks_edit_and_submission(self):
        context = self.make_decided_context()
        draft = self.make_draft(context, suffix="revoked")
        OrganizationMembership.objects.filter(
            organization=self.organization,
            user=self.lead,
        ).update(status=OrganizationMembership.Status.SUSPENDED)

        with self.assertRaises(PublishingAuthorizationError):
            update_fact_check_draft(
                fact_check=draft,
                actor=self.lead,
                headline="Unauthorized edit",
            )
        with self.assertRaises(PublishingAuthorizationError):
            submit_fact_check_for_review(
                fact_check=draft,
                actor=self.lead,
            )

        draft.refresh_from_db()
        self.assertNotEqual(draft.headline, "Unauthorized edit")
        self.assertEqual(
            draft.publication_status,
            OfficialFactCheck.PublicationStatus.DRAFT,
        )

    def test_revoked_publication_authority_blocks_publication(self):
        context = self.make_decided_context()
        submitted = self.make_submitted_draft(context, suffix="revoked-publish")
        OrganizationMembership.objects.filter(
            organization=self.organization,
            user=self.lead,
        ).update(status=OrganizationMembership.Status.SUSPENDED)

        with self.assertRaises(PublishingAuthorizationError):
            publish_fact_check(
                fact_check=submitted,
                actor=self.lead,
            )

        submitted.refresh_from_db()
        context["assignment"].refresh_from_db()
        self.assertEqual(
            submitted.publication_status,
            OfficialFactCheck.PublicationStatus.IN_REVIEW,
        )
        self.assertEqual(
            context["assignment"].status,
            VerificationAssignment.Status.ACTIVE,
        )

    def test_existing_publication_blocks_ordinary_replacement_without_changes(self):
        context = self.make_decided_context()
        first = self.make_submitted_draft(context, suffix="published-first")
        first = publish_fact_check(fact_check=first, actor=self.lead)["fact_check"]
        event_count = ModerationEvent.objects.filter(case=context["case"]).count()

        with self.assertRaises(PublishingConflict):
            self.make_draft(context, suffix="replacement")

        first.refresh_from_db()
        self.assertEqual(
            first.publication_status,
            OfficialFactCheck.PublicationStatus.PUBLISHED,
        )
        self.assertIsNone(first.archived_at)
        self.assertEqual(
            OfficialFactCheck.objects.filter(claim=context["claim"]).count(),
            1,
        )
        self.assertEqual(
            OfficialFactCheck.objects.filter(
                claim=context["claim"],
                publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            ).count(),
            1,
        )
        self.assertEqual(
            ModerationEvent.objects.filter(case=context["case"]).count(),
            event_count,
        )

    def test_assignment_completion_failure_rolls_back_publication(self):
        context = self.make_decided_context()
        submitted = self.make_submitted_draft(context, suffix="rollback")
        event_count = ModerationEvent.objects.filter(case=context["case"]).count()

        def fail_after_assignment_update(*, claim, organization):
            complete_verification_assignment(
                claim=claim,
                organization=organization,
            )
            raise VerificationAssignmentConflict(
                "The assignment changed before completion."
            )

        with patch(
            "api.publishing_service.complete_verification_assignment",
            side_effect=fail_after_assignment_update,
        ):
            with self.assertRaises(PublishingConflict):
                publish_fact_check(
                    fact_check=submitted,
                    actor=self.lead,
                )

        submitted.refresh_from_db()
        context["assignment"].refresh_from_db()
        self.assertEqual(
            submitted.publication_status,
            OfficialFactCheck.PublicationStatus.IN_REVIEW,
        )
        self.assertEqual(
            context["assignment"].status,
            VerificationAssignment.Status.ACTIVE,
        )
        self.assertEqual(
            ModerationEvent.objects.filter(case=context["case"]).count(),
            event_count,
        )

    def test_legacy_missing_assignment_is_not_fabricated(self):
        context = self.make_decided_context()
        VerificationAssignment.objects.filter(pk=context["assignment"].pk).delete()
        submitted = self.make_submitted_draft(context, suffix="legacy")

        result = publish_fact_check(
            fact_check=submitted,
            actor=self.lead,
        )

        self.assertEqual(
            result["fact_check"].publication_status,
            OfficialFactCheck.PublicationStatus.PUBLISHED,
        )
        self.assertFalse(
            VerificationAssignment.objects.filter(claim=context["claim"]).exists()
        )


class PublicationPostgresLockingTests(
    PublicationTransactionFixtures,
    TransactionTestCase,
):
    def require_postgres(self):
        if connection.vendor != "postgresql":
            self.skipTest("Row-lock concurrency coverage requires PostgreSQL.")

    def test_assignment_release_and_publication_terminate_without_deadlock(self):
        self.require_postgres()
        context = self.make_decided_context()
        submitted = self.make_submitted_draft(context, suffix="lock-order")
        barrier = threading.Barrier(2)
        outcomes = []

        def release_assignment():
            close_old_connections()
            assignment = VerificationAssignment.objects.get(pk=context["assignment"].pk)
            actor = User.objects.get(pk=self.lead.pk)
            barrier.wait(timeout=10)
            try:
                release_verification_assignment(
                    assignment=assignment,
                    actor=actor,
                )
            except (
                VerificationAssignmentConflict,
                VerificationAssignmentReleaseBlocked,
            ):
                outcomes.append("release-blocked")
            else:  # pragma: no cover - authoritative work blocks release
                outcomes.append("release-success")
            finally:
                close_old_connections()

        def publish():
            close_old_connections()
            fact_check = OfficialFactCheck.objects.get(pk=submitted.pk)
            actor = User.objects.get(pk=self.lead.pk)
            barrier.wait(timeout=10)
            try:
                publish_fact_check(fact_check=fact_check, actor=actor)
            except Exception as error:  # pragma: no cover - asserted below
                outcomes.append(f"publish-error:{type(error).__name__}")
            else:
                outcomes.append("publish-success")
            finally:
                close_old_connections()

        workers = [
            threading.Thread(target=release_assignment),
            threading.Thread(target=publish),
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=10)

        self.assertFalse(any(worker.is_alive() for worker in workers))
        self.assertCountEqual(
            outcomes,
            ["release-blocked", "publish-success"],
        )
        submitted.refresh_from_db()
        context["assignment"].refresh_from_db()
        self.assertEqual(
            submitted.publication_status,
            OfficialFactCheck.PublicationStatus.PUBLISHED,
        )
        self.assertEqual(
            context["assignment"].status,
            VerificationAssignment.Status.COMPLETED,
        )

    def test_concurrent_decision_change_blocks_stale_publication(self):
        self.require_postgres()
        context = self.make_decided_context()
        submitted = self.make_submitted_draft(context, suffix="decision-race")
        revision_holds_claim = threading.Event()
        publisher_started = threading.Event()
        allow_revision_commit = threading.Event()
        outcomes = []

        def revise_decision():
            close_old_connections()
            try:
                with transaction.atomic():
                    Claim.objects.select_for_update().get(pk=context["claim"].pk)
                    current = AdjudicationDecision.objects.select_for_update(
                        of=("self",)
                    ).get(pk=context["decision"].pk)
                    revision_holds_claim.set()
                    allow_revision_commit.wait(timeout=10)
                    current.is_current = False
                    current.save(update_fields=["is_current"])
                    replacement = AdjudicationDecision.objects.create(
                        claim_id=context["claim"].pk,
                        moderation_case_id=context["case"].pk,
                        verdict=AdjudicationDecision.Verdict.MISLEADING,
                        canonical_claim=(
                            "The reviewed claim requires additional context."
                        ),
                        rationale="Test-only concurrent revision state.",
                        decided_by_id=self.lead.pk,
                        organization_id=self.organization.pk,
                        revision_number=2,
                        supersedes=current,
                        is_current=True,
                    )
                    Claim.objects.filter(pk=context["claim"].pk).update(
                        final_verdict=replacement.verdict
                    )
                outcomes.append("revision-committed")
            except Exception as error:  # pragma: no cover - asserted below
                outcomes.append(f"revision-error:{type(error).__name__}")
            finally:
                close_old_connections()

        def publish_stale_article():
            close_old_connections()
            revision_holds_claim.wait(timeout=10)
            fact_check = OfficialFactCheck.objects.get(pk=submitted.pk)
            actor = User.objects.get(pk=self.lead.pk)
            publisher_started.set()
            try:
                publish_fact_check(fact_check=fact_check, actor=actor)
            except PublishingConflict:
                outcomes.append("publication-conflict")
            except Exception as error:  # pragma: no cover - asserted below
                outcomes.append(f"publication-error:{type(error).__name__}")
            else:  # pragma: no cover - stale decision must be rejected
                outcomes.append("publication-success")
            finally:
                close_old_connections()

        reviser = threading.Thread(target=revise_decision)
        publisher = threading.Thread(target=publish_stale_article)
        reviser.start()
        revision_holds_claim.wait(timeout=10)
        publisher.start()
        publisher_started.wait(timeout=10)
        allow_revision_commit.set()
        reviser.join(timeout=10)
        publisher.join(timeout=10)

        self.assertFalse(reviser.is_alive())
        self.assertFalse(publisher.is_alive())
        self.assertCountEqual(
            outcomes,
            ["revision-committed", "publication-conflict"],
        )
        submitted.refresh_from_db()
        self.assertEqual(
            submitted.publication_status,
            OfficialFactCheck.PublicationStatus.IN_REVIEW,
        )
        self.assertFalse(
            OfficialFactCheck.objects.filter(
                claim=context["claim"],
                publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            ).exists()
        )
