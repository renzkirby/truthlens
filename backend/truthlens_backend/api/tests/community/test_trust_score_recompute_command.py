from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase


class TrustScoreRecomputeCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="trust-recompute-user",
            password="pass1234",
        )
        self.user.profile.trust_score = 0.0
        self.user.profile.save(
            update_fields=["trust_score"],
        )

        self.platform_admin = User.objects.create_superuser(
            username="trust-recompute-platform-admin",
            email="platform-admin@example.com",
            password="pass1234",
        )
        self.platform_admin.profile.trust_score = 5.0
        self.platform_admin.profile.save(
            update_fields=["trust_score"],
        )

    def test_preview_reports_impact_without_writing(self):
        output = StringIO()

        call_command(
            "recompute_trust_scores",
            stdout=output,
        )

        self.user.profile.refresh_from_db()
        self.platform_admin.profile.refresh_from_db()

        self.assertEqual(
            self.user.profile.trust_score,
            0.0,
        )
        self.assertEqual(
            self.platform_admin.profile.trust_score,
            5.0,
        )

        rendered = output.getvalue()
        self.assertIn("mode=PREVIEW", rendered)
        self.assertIn("changed_users=1", rendered)
        self.assertIn("platform_staff_skipped=1", rendered)
        self.assertIn("legacy_zero_to_neutral=1", rendered)
        self.assertIn("delta_over_15=1", rendered)
        self.assertIn("changed_with_resolved_actions=0", rendered)
        self.assertIn("changed_with_community_votes=0", rendered)
        self.assertIn("NO DATABASE WRITES", rendered)
        self.assertNotIn(self.user.username, rendered)
        self.assertNotIn(self.platform_admin.username, rendered)

    def test_apply_persists_only_applicable_community_scores(self):
        output = StringIO()

        call_command(
            "recompute_trust_scores",
            "--apply",
            stdout=output,
        )

        self.user.profile.refresh_from_db()
        self.platform_admin.profile.refresh_from_db()

        self.assertEqual(
            self.user.profile.trust_score,
            50.0,
        )
        self.assertEqual(
            self.platform_admin.profile.trust_score,
            5.0,
        )

        rendered = output.getvalue()
        self.assertIn("mode=APPLY", rendered)
        self.assertIn("changed_users=1", rendered)
        self.assertIn("APPLIED", rendered)
