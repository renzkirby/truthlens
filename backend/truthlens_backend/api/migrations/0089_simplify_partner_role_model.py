from django.db import migrations, models
from django.db.models import Count, Q


LEGACY_OWNER = "OWNER"
LEGACY_MODERATOR = "MODERATOR"
LEGACY_CONTRIBUTOR = "CONTRIBUTOR"
ADMIN = "ADMIN"
VERIFICATION_REVIEWER = "VERIFICATION_REVIEWER"
LEFT = "LEFT"
PENDING = "PENDING"
CANCELLED = "CANCELLED"
LEGACY_PRIMARY_ADMIN_ONBOARDING = "PRIMARY_ADMIN_ONBOARDING"
ORGANIZATION_ADMIN_ONBOARDING = "ORGANIZATION_ADMIN_ONBOARDING"


def migrate_partner_role_model(apps, schema_editor):
    OrganizationMembership = apps.get_model("api", "OrganizationMembership")
    OrganizationInvitation = apps.get_model("api", "OrganizationInvitation")

    OrganizationMembership.objects.filter(role=LEGACY_OWNER).update(role=ADMIN)
    OrganizationMembership.objects.filter(role=LEGACY_MODERATOR).update(
        role=VERIFICATION_REVIEWER
    )

    # Contributor carried no organization capability. Preserve the historical
    # membership row, but retire any current affiliation instead of inventing
    # a new authority-bearing role.
    OrganizationMembership.objects.filter(
        role=LEGACY_CONTRIBUTOR,
    ).exclude(status=LEFT).update(status=LEFT)

    OrganizationInvitation.objects.filter(invited_role=LEGACY_OWNER).update(
        invited_role=ADMIN
    )
    OrganizationInvitation.objects.filter(invited_role=LEGACY_MODERATOR).update(
        invited_role=VERIFICATION_REVIEWER
    )
    OrganizationInvitation.objects.filter(
        invited_role=LEGACY_CONTRIBUTOR,
        status=PENDING,
    ).update(status=CANCELLED)
    OrganizationInvitation.objects.filter(
        purpose=LEGACY_PRIMARY_ADMIN_ONBOARDING,
    ).update(purpose=ORGANIZATION_ADMIN_ONBOARDING)

    conflicts = list(
        OrganizationMembership.objects.exclude(status=LEFT)
        .values("user_id")
        .annotate(current_count=Count("id"))
        .filter(current_count__gt=1)
        .values_list("user_id", "current_count")
    )
    if conflicts:
        user_ids = ", ".join(
            f"{user_id} ({count} memberships)" for user_id, count in conflicts[:25]
        )
        suffix = "" if len(conflicts) <= 25 else f" and {len(conflicts) - 25} more"
        raise RuntimeError(
            "Cannot enforce one current Partner Organization per user. "
            f"Resolve these existing membership conflicts first: {user_ids}{suffix}."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0088_claim_relatedness_context_nullable"),
    ]

    operations = [
        migrations.RunPython(
            migrate_partner_role_model,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="organizationmembership",
            name="role",
            field=models.CharField(
                choices=[
                    ("ADMIN", "Administrator"),
                    ("LEAD_VERIFIER", "Lead Verifier"),
                    ("VERIFICATION_REVIEWER", "Verification Reviewer"),
                    ("RESEARCHER", "Researcher"),
                ],
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="organizationinvitation",
            name="invited_role",
            field=models.CharField(
                choices=[
                    ("ADMIN", "Administrator"),
                    ("LEAD_VERIFIER", "Lead Verifier"),
                    ("VERIFICATION_REVIEWER", "Verification Reviewer"),
                    ("RESEARCHER", "Researcher"),
                ],
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="organizationinvitation",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("MEMBERSHIP", "Membership"),
                    (
                        "ORGANIZATION_ADMIN_ONBOARDING",
                        "Organization Admin onboarding",
                    ),
                ],
                default="MEMBERSHIP",
                max_length=40,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="organizationinvitation",
            name="unique_pending_primary_admin_invite_org",
        ),
        migrations.AddConstraint(
            model_name="organizationinvitation",
            constraint=models.UniqueConstraint(
                condition=Q(
                    purpose="ORGANIZATION_ADMIN_ONBOARDING",
                    status="PENDING",
                ),
                fields=("organization",),
                name="unique_pending_org_admin_invite_org",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationmembership",
            constraint=models.UniqueConstraint(
                condition=~Q(status="LEFT"),
                fields=("user",),
                name="unique_current_organization_membership_per_user",
            ),
        ),
    ]
