from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0111_multitarget_community_safety"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PartnershipApplication",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("applicant_full_name", models.CharField(max_length=255)),
                ("applicant_position", models.CharField(max_length=255)),
                ("applicant_email", models.EmailField(max_length=254)),
                ("official_contact_email", models.EmailField(max_length=254)),
                ("organization_description", models.TextField(max_length=4000)),
                ("partnership_reason", models.TextField(max_length=4000)),
                ("supporting_links", models.JSONField(blank=True, default=list)),
                ("authorized_to_represent", models.BooleanField(default=False)),
                (
                    "agrees_to_partner_responsibilities",
                    models.BooleanField(default=False),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("SUBMITTED", "Submitted"),
                            ("UNDER_REVIEW", "Under Review"),
                            ("APPROVED", "Approved for Onboarding"),
                            ("REJECTED", "Rejected"),
                        ],
                        db_index=True,
                        default="SUBMITTED",
                        max_length=24,
                    ),
                ),
                ("review_started_at", models.DateTimeField(blank=True, null=True)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                (
                    "decision_notes",
                    models.TextField(blank=True, default="", max_length=4000),
                ),
                (
                    "approved_admin_email",
                    models.EmailField(blank=True, default="", max_length=254),
                ),
                ("onboarding_completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "decided_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="decided_partnership_applications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="partnership_application",
                        to="api.organization",
                    ),
                ),
                (
                    "reviewer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_partnership_applications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddIndex(
            model_name="partnershipapplication",
            index=models.Index(
                fields=["status", "-created_at"],
                name="partner_app_status_created_idx",
            ),
        ),
    ]
