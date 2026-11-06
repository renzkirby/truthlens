from django.contrib.auth.models import User
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Organization, UserProfile
from .public_read_cache import invalidate_public_organization_read_cache


@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance, **kwargs):
    UserProfile.objects.get_or_create(user=instance)


def _invalidate_public_organization_reads_after_commit(organization_id):
    transaction.on_commit(
        lambda: invalidate_public_organization_read_cache(organization_id)
    )


@receiver(post_save, sender=Organization)
def invalidate_public_organization_reads_on_save(sender, instance, **kwargs):
    _invalidate_public_organization_reads_after_commit(instance.pk)


@receiver(post_delete, sender=Organization)
def invalidate_public_organization_reads_on_delete(sender, instance, **kwargs):
    _invalidate_public_organization_reads_after_commit(instance.pk)
