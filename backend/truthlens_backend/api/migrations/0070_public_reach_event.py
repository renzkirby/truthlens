import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0069_claim_fact_check_relationship_unique")]

    operations = [
        migrations.CreateModel(
            name="PublicReachEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("client_event_id", models.UUIDField(editable=False, unique=True)),
                ("event_type", models.CharField(choices=[
                    ("PUBLICATION_VIEW", "Publication view"),
                    ("PARTNER_PROFILE_VIEW", "Partner profile view"),
                    ("EXTENSION_PUBLICATION_IMPRESSION", "Extension publication impression"),
                    ("EXTENSION_PUBLICATION_CLICK", "Extension publication click"),
                ], db_index=True, max_length=40)),
                ("source_surface", models.CharField(choices=[
                    ("PUBLIC_FACT_CHECK_PAGE", "Public fact-check page"),
                    ("PUBLIC_PARTNER_PROFILE", "Public partner profile"),
                    ("EXTENSION_OFFICIAL_FACT_CHECK", "Extension official fact-check"),
                    ("EXTENSION_RELATED_FACT_CHECK", "Extension related fact-check"),
                ], db_index=True, max_length=40)),
                ("source_organization_id_snapshot", models.CharField(db_index=True, max_length=255)),
                ("fact_check_id_snapshot", models.CharField(blank=True, db_index=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("organization", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="public_reach_events", to="api.organization")),
                ("fact_check", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="public_reach_events", to="api.officialfactcheck")),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["event_type", "-created_at"], name="reach_event_time_idx"),
                    models.Index(fields=["source_surface", "-created_at"], name="reach_surface_time_idx"),
                    models.Index(fields=["source_organization_id_snapshot", "-created_at"], name="reach_org_time_idx"),
                    models.Index(fields=["fact_check_id_snapshot", "-created_at"], name="reach_publication_time_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(condition=(
                        models.Q(event_type="PARTNER_PROFILE_VIEW", source_surface="PUBLIC_PARTNER_PROFILE")
                        | models.Q(event_type="PUBLICATION_VIEW", source_surface="PUBLIC_FACT_CHECK_PAGE")
                        | models.Q(
                            event_type__in=["EXTENSION_PUBLICATION_IMPRESSION", "EXTENSION_PUBLICATION_CLICK"],
                            source_surface__in=["EXTENSION_OFFICIAL_FACT_CHECK", "EXTENSION_RELATED_FACT_CHECK"],
                        )
                    ), name="reach_valid_event_surface"),
                    models.CheckConstraint(condition=(
                        models.Q(event_type="PARTNER_PROFILE_VIEW", fact_check_id_snapshot="", fact_check__isnull=True)
                        | (~models.Q(event_type="PARTNER_PROFILE_VIEW") & ~models.Q(fact_check_id_snapshot=""))
                    ), name="reach_publication_snapshot"),
                    models.CheckConstraint(condition=~models.Q(source_organization_id_snapshot=""), name="reach_organization_snapshot"),
                ],
            },
        ),
    ]
