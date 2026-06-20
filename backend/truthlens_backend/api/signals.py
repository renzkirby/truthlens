from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import UserProfile, EvidenceSubmission
from django.contrib.auth.models import User

@receiver(post_save, sender=EvidenceSubmission)
def update_claim_verdict(sender, instance, **kwargs):
    if instance.evidence_status == 'VERIFIED':
        new_verdict = instance.thread.claim.compute_final_verdict()
        if new_verdict and instance.thread.claim.final_verdict != new_verdict:
            instance.thread.claim.final_verdict = new_verdict
            instance.thread.claim.save(update_fields=['final_verdict'])

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()
