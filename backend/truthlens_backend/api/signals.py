from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User

from .models import UserProfile, EvidenceSubmission


@receiver(post_save, sender=EvidenceSubmission)
def update_claim_verdict(sender, instance, **kwargs):
    if instance.evidence_status == "VERIFIED":
        new_verdict = instance.thread.claim.compute_final_verdict()

        if (
            new_verdict
            and instance.thread.claim.final_verdict != new_verdict
        ):
            instance.thread.claim.final_verdict = new_verdict
            instance.thread.claim.save(
                update_fields=["final_verdict"]
            )


@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance, **kwargs):
    UserProfile.objects.get_or_create(user=instance)