from django.db import models
import uuid


# Create your models here.
class Claim(models.Model):
    class VerificationSource(models.TextChoices):
        AI_EXTENSION = "AI_EXTENSION", "AI Extension"
        COMMUNITY = "COMMUNITY", "Community Platform"
        PENDING = "PENDING", "Pending"

    class ClaimType(models.TextChoices):
        IMAGE = "IMAGE", "Image"
        VIDEO = "VIDEO", "Video"
        URL = "URL", "URL"
        FILE = "FILE", "File"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    claim_type = models.CharField(max_length=20, choices=ClaimType.choices)
    media_url = models.CharField(max_length=500, blank=True, null=True)
    media_hash = models.CharField(max_length=64, blank=True, null=True)
    url_link = models.URLField(max_length=500, blank=True, null=True)
    context_text = models.TextField(blank=True, null=True)
    ai_summary = models.TextField(blank=True, null=True)
    verdict = models.CharField(max_length=20, blank=True, null=True)
    consensus_score = models.FloatField(blank=True, null=True)

    verified_via = models.CharField(
        max_length=20,
        choices=VerificationSource.choices,
        default=VerificationSource.PENDING,
    )

    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Claim {self.id} - Type: {self.claim_type} - Verdict: {self.verdict}"


class Thread(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name="threads")
    author = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="threads"
    )
    caption = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Thread {self.id} - Claim ID: {self.claim.id} - Author: {self.author.username}"
