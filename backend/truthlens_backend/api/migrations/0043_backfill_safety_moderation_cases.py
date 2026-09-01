from django.db import migrations


ACTIVE_STATUSES = [
    "OPEN",
    "IN_REVIEW",
    "ESCALATED",
    "REOPENED",
]


def backfill_safety_cases(
    apps,
    schema_editor,
):
    ThreadFlag = apps.get_model(
        "api",
        "ThreadFlag",
    )

    ModerationCase = apps.get_model(
        "api",
        "ModerationCase",
    )

    ModerationEvent = apps.get_model(
        "api",
        "ModerationEvent",
    )

    thread_ids = (
        ThreadFlag.objects
        .filter(
            resolved_at__isnull=True
        )
        .values_list(
            "thread_id",
            flat=True,
        )
        .distinct()
    )

    for thread_id in thread_ids:
        existing_case = (
            ModerationCase.objects
            .filter(
                case_type="SAFETY",
                thread_id=thread_id,
                status__in=ACTIVE_STATUSES,
            )
            .first()
        )

        if existing_case:
            continue

        case = ModerationCase.objects.create(
            case_type="SAFETY",
            status="OPEN",
            priority="NORMAL",
            source="USER_REPORT",
            thread_id=thread_id,
        )

        ModerationEvent.objects.create(
            case_id=case.id,
            event_type="CASE_CREATED",
            to_status="OPEN",
            metadata={
                "source": "USER_REPORT",
                "priority": "NORMAL",
                "legacy_backfill": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        (
            "api",
            "0042_remove_threadflag_unique_flag_per_thread_per_user_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(
            backfill_safety_cases,
            migrations.RunPython.noop,
        ),
    ]