from django.db import models
from django.contrib.auth.models import User
import uuid


# Create your models here.
class UserProfile(models.Model):
    class Role(models.TextChoices):
        USER = "USER", "User"
        MODERATOR = "MODERATOR", "Moderator"
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.USER)
    trust_score = models.FloatField(default=0.0)
    bio = models.TextField(blank=True, null=True)
    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=64, blank=True, null=True)

    def __str__(self):
        return f"UserProfile {self.id} - User: {self.user.username} - Trust Score: {self.trust_score}"


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
    image = models.ImageField(upload_to='claims/images/', null=True, blank=True)
    media_hash = models.CharField(max_length=64, blank=True, null=True)
    url_link = models.URLField(max_length=500, blank=True, null=True)
    context_text = models.TextField(blank=True, null=True)
    ai_summary = models.TextField(blank=True, null=True)
    verdict = models.CharField(max_length=20, blank=True, null=True)
    consensus_score = models.FloatField(blank=True, null=True)
    source_type = models.CharField(max_length=50, blank=True, null=True)
    verified_via = models.CharField(
        max_length=20,
        choices=VerificationSource.choices,
        default=VerificationSource.PENDING,
    )

    source_link = models.URLField(max_length=500, blank=True, null=True)
    top_verdict_source = models.URLField(max_length=500, blank=True, null=True)

    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Claim {self.id} - Type: {self.claim_type} - Verdict: {self.verdict}"


class Thread(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"
        REJECTED = "REJECTED", "Rejected"    
    class FlagReason(models.TextChoices):
        FACT = "FACT", "Fact"
        FAKE = "FAKE", "Fake"
        MISLEADING = "MISLEADING", "Misleading"
        SATIRE = "SATIRE", "Satire"
        UNVERIFIED = "UNVERIFIED", "Unverified"
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name="threads")
    author = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="authored_threads"
    )
    caption = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, blank=True, null=True, default="OPEN")
    flag_reason = models.CharField(max_length=20, choices=FlagReason.choices, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    moderator_verdict = models.CharField(max_length=20, blank=True, null=True)
    moderator_notes = models.TextField(blank=True, null=True)
    moderated_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="moderated_threads"
    )
    moderated_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Thread {self.id} - Claim ID: {self.claim.id} - Author: {self.author.username}"

class ThreadFlag(models.Model):
    class Reason(models.TextChoices):
        INAPPROPRIATE = "INAPPROPRIATE", "Inappropriate Content"
        SPAM = "SPAM", "Spam"
        HARASSMENT = "HARASSMENT", "Harassment"
        OTHER = "OTHER", "Other"
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="flags")
    flagged_by = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="thread_flags"
    )
    reason = models.CharField(max_length=20, choices=Reason.choices)
    notes = models.TextField(blank=True, null=True)
    flagged_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["thread", "flagged_by"], name="unique_flag_per_thread_per_user"
            )
        ]

class EvidenceSubmission(models.Model):
    class EvidenceType(models.TextChoices):
        CONTRADICTS = "CONTRADICTS CLAIM", "Contradicts Claim"
        SUPPORTS = "SUPPORTS CLAIM", "Supports Claim"
        PROVIDES_CONTEXT = "PROVIDES CONTEXT", "Provides Context"
        SOURCE_VERIFICATION = "SOURCE VERIFICATION", "Source Verification"
    
    class EvidenceStatus(models.TextChoices):
        UNVERIFIED = "UNVERIFIED", "Unverified"
        VERIFIED = "VERIFIED", "Verified"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(
        Thread, on_delete=models.CASCADE, related_name="evidence_submissions"
    )
    contributor = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="contributed_evidence"
    )
    evidence_caption = models.TextField(blank=True, null=True)
    evidence_url = models.URLField(max_length=500, blank=True, null=True)
    evidence_type = models.CharField(
        max_length=20, choices=EvidenceType.choices, blank=True, null=True
    )
    evidence_verdict = models.CharField(max_length=20, blank=True, null=True)
    evidence_status = models.CharField(
        max_length=20, choices=EvidenceStatus.choices, default=EvidenceStatus.UNVERIFIED
    )
    contributor_trust_snapshot = models.FloatField(blank=True, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"EvidenceSubmission {self.id} - Thread ID: {self.thread.id} - Contributor: {self.contributor.username}"


class Vote(models.Model):
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["evidence", "voter"], name="unique_vote_per_evidence_per_user"
            )
        ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    evidence = models.ForeignKey(
        EvidenceSubmission, on_delete=models.CASCADE, related_name="votes"
    )
    voter = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="user_votes"
    )
    vote_value = models.BooleanField()  # True for upvote, False for downvote
    vote_trust_snapshot = models.FloatField(blank=True, null=True)
    voted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Vote {self.id} - Evidence ID: {self.evidence.id} - Voter: {self.voter.username} - Vote: {'Upvote' if self.vote_value else 'Downvote'}"


class ThreadComment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(
        Thread, on_delete=models.CASCADE, related_name="comments"
    )
    commenter = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="user_comments"
    )
    comment_text = models.TextField(blank=True, null=True)
    commented_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"ThreadComment {self.id} - Thread ID: {self.thread.id} - Commenter: {self.commenter.username}"
