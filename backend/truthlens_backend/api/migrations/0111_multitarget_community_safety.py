from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


ACTIVE_SAFETY_STATUSES = [
    "OPEN",
    "IN_REVIEW",
    "ESCALATED",
    "REOPENED",
]


def backfill_multitarget_safety(apps, schema_editor):
    CommunityReport = apps.get_model("api", "CommunityReport")
    CommunityReportOutcome = apps.get_model("api", "CommunityReportOutcome")
    ModerationCase = apps.get_model("api", "ModerationCase")
    CommunitySafetyDecision = apps.get_model("api", "CommunitySafetyDecision")

    CommunityReport.objects.all().update(target_type="THREAD")

    for outcome in CommunityReportOutcome.objects.filter(
        target_id_snapshot__isnull=True,
    ).iterator():
        CommunityReportOutcome.objects.filter(pk=outcome.pk).update(
            target_type="THREAD",
            target_id_snapshot=outcome.thread_id,
        )

    ModerationCase.objects.filter(case_type="SAFETY").update(
        safety_target_type="THREAD",
    )

    for decision in CommunitySafetyDecision.objects.filter(
        target_id_snapshot__isnull=True,
    ).iterator():
        CommunitySafetyDecision.objects.filter(pk=decision.pk).update(
            target_type="THREAD",
            target_id_snapshot=decision.thread_id_snapshot,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0110_community_safety_reconsideration"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="ThreadFlag",
            new_name="CommunityReport",
        ),
        migrations.RenameModel(
            old_name="FlagResolutionLog",
            new_name="CommunityReportOutcome",
        ),
        migrations.RenameField(
            model_name="communityreport",
            old_name="flagged_by",
            new_name="reporter",
        ),
        migrations.RenameField(
            model_name="communityreport",
            old_name="flagged_at",
            new_name="reported_at",
        ),
        migrations.RenameField(
            model_name="communityreportoutcome",
            old_name="flagged_by",
            new_name="reporter",
        ),
        migrations.RenameField(
            model_name="communityreportoutcome",
            old_name="flagged_at",
            new_name="reported_at",
        ),
        migrations.RenameField(
            model_name="communitysafetydecision",
            old_name="thread_author",
            new_name="content_owner",
        ),
        migrations.RenameField(
            model_name="communitysafetydecision",
            old_name="author_username_snapshot",
            new_name="owner_username_snapshot",
        ),
        migrations.RemoveConstraint(
            model_name="communityreport",
            name="unique_active_flag_per_thread_user",
        ),
        migrations.RemoveConstraint(
            model_name="communityreportoutcome",
            name="flag_report_decision_pair_ck",
        ),
        migrations.RemoveConstraint(
            model_name="communityreportoutcome",
            name="flag_report_outcome_valid_ck",
        ),
        migrations.RemoveConstraint(
            model_name="moderationcase",
            name="uniq_active_safety_case_thread",
        ),
        migrations.AlterField(
            model_name="communityreport",
            name="thread",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="community_reports",
                to="api.thread",
            ),
        ),
        migrations.AlterField(
            model_name="communityreport",
            name="reporter",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="community_reports",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="communityreportoutcome",
            name="thread",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="community_report_outcomes",
                to="api.thread",
            ),
        ),
        migrations.AlterField(
            model_name="communityreportoutcome",
            name="reporter",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="resolved_community_reports",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="communityreportoutcome",
            name="resolved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="resolved_community_reports_moderated",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="communityreport",
            name="target_type",
            field=models.CharField(
                choices=[
                    ("THREAD", "Discussion"),
                    ("COMMENT", "Comment"),
                    ("EVIDENCE", "Evidence"),
                ],
                db_index=True,
                default="THREAD",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="communityreport",
            name="comment",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="community_reports",
                to="api.threadcomment",
            ),
        ),
        migrations.AddField(
            model_name="communityreport",
            name="evidence_submission",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="community_reports",
                to="api.evidencesubmission",
            ),
        ),
        migrations.AddField(
            model_name="communityreportoutcome",
            name="target_type",
            field=models.CharField(
                choices=[
                    ("THREAD", "Discussion"),
                    ("COMMENT", "Comment"),
                    ("EVIDENCE", "Evidence"),
                ],
                db_index=True,
                default="THREAD",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="communityreportoutcome",
            name="target_id_snapshot",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="communityreportoutcome",
            name="comment",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="community_report_outcomes",
                to="api.threadcomment",
            ),
        ),
        migrations.AddField(
            model_name="communityreportoutcome",
            name="evidence_submission",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="community_report_outcomes",
                to="api.evidencesubmission",
            ),
        ),
        migrations.AddField(
            model_name="evidencesubmission",
            name="safety_removed_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="evidencesubmission",
            name="safety_removed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="safety_removed_evidence_submissions",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="threadcomment",
            name="safety_removed_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="threadcomment",
            name="safety_removed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="safety_removed_comments",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="moderationcase",
            name="safety_target_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("THREAD", "Discussion"),
                    ("COMMENT", "Comment"),
                    ("EVIDENCE", "Evidence"),
                ],
                db_index=True,
                max_length=16,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="moderationcase",
            name="thread_comment",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="moderation_cases",
                to="api.threadcomment",
            ),
        ),
        migrations.AddField(
            model_name="communitysafetydecision",
            name="target_type",
            field=models.CharField(
                choices=[
                    ("THREAD", "Discussion"),
                    ("COMMENT", "Comment"),
                    ("EVIDENCE", "Evidence"),
                ],
                db_index=True,
                default="THREAD",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="communitysafetydecision",
            name="target_id_snapshot",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.RunPython(
            backfill_multitarget_safety,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="communityreportoutcome",
            name="target_id_snapshot",
            field=models.UUIDField(),
        ),
        migrations.AlterField(
            model_name="communitysafetydecision",
            name="target_id_snapshot",
            field=models.UUIDField(),
        ),
        migrations.AddConstraint(
            model_name="communityreport",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        target_type="THREAD",
                        comment__isnull=True,
                        evidence_submission__isnull=True,
                    )
                    | models.Q(
                        target_type="COMMENT",
                        comment__isnull=False,
                        evidence_submission__isnull=True,
                    )
                    | models.Q(
                        target_type="EVIDENCE",
                        comment__isnull=True,
                        evidence_submission__isnull=False,
                    )
                ),
                name="community_report_target_shape_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="communityreport",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    target_type="THREAD",
                    resolved_at__isnull=True,
                ),
                fields=("thread", "reporter"),
                name="uniq_active_report_thread_user",
            ),
        ),
        migrations.AddConstraint(
            model_name="communityreport",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    target_type="COMMENT",
                    resolved_at__isnull=True,
                ),
                fields=("comment", "reporter"),
                name="uniq_active_report_comment_user",
            ),
        ),
        migrations.AddConstraint(
            model_name="communityreport",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    target_type="EVIDENCE",
                    resolved_at__isnull=True,
                ),
                fields=("evidence_submission", "reporter"),
                name="uniq_active_report_evidence_user",
            ),
        ),
        migrations.AddConstraint(
            model_name="communityreportoutcome",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        report_outcome__isnull=True,
                        safety_decision__isnull=True,
                    )
                    | models.Q(
                        report_outcome__isnull=False,
                        safety_decision__isnull=False,
                    )
                ),
                name="community_report_decision_pair_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="communityreportoutcome",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(report_outcome__isnull=True)
                    | models.Q(
                        report_outcome="CONFIRMED",
                        is_valid_report=True,
                    )
                    | models.Q(
                        report_outcome__in=[
                            "NOT_CONFIRMED",
                            "NO_VIOLATION",
                        ],
                        is_valid_report=False,
                    )
                ),
                name="community_report_outcome_valid_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="communityreportoutcome",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        target_type="THREAD",
                        comment__isnull=True,
                        evidence_submission__isnull=True,
                    )
                    | models.Q(
                        target_type="COMMENT",
                        evidence_submission__isnull=True,
                    )
                    | models.Q(
                        target_type="EVIDENCE",
                        comment__isnull=True,
                    )
                ),
                name="community_report_outcome_target_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="moderationcase",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        case_type="SAFETY",
                        safety_target_type="THREAD",
                        thread_comment__isnull=True,
                        evidence_submission__isnull=True,
                        claim__isnull=True,
                    )
                    | models.Q(
                        case_type="SAFETY",
                        safety_target_type="COMMENT",
                        evidence_submission__isnull=True,
                        claim__isnull=True,
                    )
                    | models.Q(
                        case_type="SAFETY",
                        safety_target_type="EVIDENCE",
                        thread_comment__isnull=True,
                        claim__isnull=True,
                    )
                    | ~models.Q(case_type="SAFETY")
                ),
                name="moderation_case_target_shape_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="moderationcase",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    case_type="SAFETY",
                    safety_target_type="THREAD",
                    status__in=ACTIVE_SAFETY_STATUSES,
                ),
                fields=("thread",),
                name="uniq_active_safety_case_thread",
            ),
        ),
        migrations.AddConstraint(
            model_name="moderationcase",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    case_type="SAFETY",
                    safety_target_type="COMMENT",
                    status__in=ACTIVE_SAFETY_STATUSES,
                ),
                fields=("thread_comment",),
                name="uniq_active_safety_case_comment",
            ),
        ),
        migrations.AddConstraint(
            model_name="moderationcase",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    case_type="SAFETY",
                    safety_target_type="EVIDENCE",
                    status__in=ACTIVE_SAFETY_STATUSES,
                ),
                fields=("evidence_submission",),
                name="uniq_active_safety_case_evidence",
            ),
        ),
    ]
