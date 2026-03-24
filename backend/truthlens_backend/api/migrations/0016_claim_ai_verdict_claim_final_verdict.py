from django.db import migrations, models


def forwards_copy_verdicts(apps, schema_editor):
    Claim = apps.get_model("api", "Claim")
    for claim in Claim.objects.all().iterator():
        changed = False
        if claim.ai_verdict is None and claim.verdict is not None:
            claim.ai_verdict = claim.verdict
            changed = True
        if claim.final_verdict is None and claim.verdict is not None:
            claim.final_verdict = claim.verdict
            changed = True
        if changed:
            claim.save(update_fields=["ai_verdict", "final_verdict"])


def backwards_copy_verdicts(apps, schema_editor):
    Claim = apps.get_model("api", "Claim")
    for claim in Claim.objects.all().iterator():
        if claim.verdict is None and claim.final_verdict is not None:
            claim.verdict = claim.final_verdict
            claim.save(update_fields=["verdict"])


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0015_thread_moderated_at_thread_moderated_by_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="claim",
            name="ai_verdict",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="claim",
            name="final_verdict",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.RunPython(forwards_copy_verdicts, backwards_copy_verdicts),
    ]
