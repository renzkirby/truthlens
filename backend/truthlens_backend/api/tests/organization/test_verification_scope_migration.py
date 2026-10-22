"""Forward migration coverage: preserve previous effective scope without rewriting history."""
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.test import TestCase

from api.models import Organization


backfill = import_module(
    "api.migrations.0085_organization_specializations"
).backfill_specializations


class OrganizationSpecializationsMigrationTests(TestCase):
    def make_org(self, slug, **fields):
        return Organization.objects.create(name=slug, slug=slug, **fields)

    def test_backfill_copies_only_historically_effective_subjects(self):
        legacy = self.make_org(
            "legacy",
            approved_verification_domains=["SCIENCE"],
            approved_verification_jurisdictions=["PH"],
        )
        narrowed = self.make_org(
            "narrowed",
            approved_verification_domains=["SCIENCE", "TECHNOLOGY"],
            approved_verification_jurisdictions=["PH", "US"],
            active_scope_configured=True,
            active_verification_domains=["TECHNOLOGY"],
            active_verification_jurisdictions=["PH"],
        )
        no_geo = self.make_org(
            "no-geo",
            approved_verification_domains=["SCIENCE"],
            approved_verification_jurisdictions=[],
        )
        inactive = self.make_org(
            "inactive",
            approved_verification_domains=["SCIENCE"],
            approved_verification_jurisdictions=["PH"],
            active_scope_configured=True,
        )
        backfill(apps, SimpleNamespace(connection=connection))
        for org in (legacy, narrowed, no_geo, inactive):
            org.refresh_from_db()
        self.assertEqual(legacy.verification_specializations, ["SCIENCE"])
        self.assertEqual(narrowed.verification_specializations, ["TECHNOLOGY"])
        self.assertEqual(no_geo.verification_specializations, [])
        self.assertEqual(inactive.verification_specializations, [])
        self.assertEqual(legacy.approved_verification_domains, ["SCIENCE"])
        self.assertEqual(narrowed.active_verification_domains, ["TECHNOLOGY"])
