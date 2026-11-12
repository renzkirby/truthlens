from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


def backfill_pre_removal_thread_status(apps, schema_editor):
    CommunitySafetyDecision = apps.get_model("api", "CommunitySafetyDecision")
    AccountabilityEvent = apps.get_model("api", "AccountabilityEvent")

    valid_statuses = {"PENDING", "OPEN", "CLOSED"}

    for decision in CommunitySafetyDecision.objects.filter(
        action="REMOVE",
        pre_removal_thread_status__isnull=True,
    ).iterator():
        event = (
            AccountabilityEvent.objects.filter(
                action_type="SAFETY_CONTENT_REMOVED",
                resource_type="MODERATION_CASE",
                resource_id=str(decision.moderation_case_id),
            )
            .order_by("-created_at", "-id")
            .first()
        )
        previous_status = (
            (event.previous_state or {}).get("thread_status")
            if event is not None
            else None
        )
        if previous_status in valid_statuses:
            CommunitySafetyDecision.objects.filter(pk=decision.pk).update(
                pre_removal_thread_status=previous_status,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0109_community_safety_decisions"),
    ]

    operations = [
        migrations.AddField(
            model_name="communitysafetydecision",
            name="pre_removal_thread_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("PENDING", "Pending"),
                    ("OPEN", "Open"),
                    ("CLOSED", "Closed"),
                    ("REJECTED", "Rejected"),
                ],
                max_length=20,
                null=True,
            ),
        ),
        migrations.RunPython(
            backfill_pre_removal_thread_status,
            migrations.RunPython.noop,
        ),
        migrations.CreateModel(
            name="CommunitySafetyReconsideration",
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
                ("request_statement", models.TextField()),
                (
                    "outcome",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("UPHELD", "Removal upheld"),
                            ("REVERSED", "Removal reversed"),
                        ],
                        default="",
                        max_length=20,
                    ),
                ),
                (
                    "resolution_rationale",
                    models.TextField(blank=True, default=""),
                ),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="community_safety_reconsideration_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="community_safety_reconsiderations_reviewed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "safety_decision",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reconsideration",
                        to="api.communitysafetydecision",
                    ),
                ),
            ],
            options={
                "ordering": ["-submitted_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="communitysafetyreconsideration",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        outcome="",
                        reviewed_by__isnull=True,
                        resolved_at__isnull=True,
                        resolution_rationale="",
                    )
                    | (
                        models.Q(outcome__in=["UPHELD", "REVERSED"])
                        & models.Q(reviewed_by__isnull=False)
                        & models.Q(resolved_at__isnull=False)
                        & ~models.Q(resolution_rationale="")
                    )
                ),
                name="comm_safety_reconsideration_state_ck",
            ),
        ),
    ]
