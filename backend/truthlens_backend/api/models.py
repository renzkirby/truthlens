from django.db import models
from django.contrib.auth.models import User
from pgvector.django import VectorField, HnswIndex
import uuid


# Create your models here.
class UserProfile(models.Model):
    class Role(models.TextChoices):
        USER = "USER", "User"
        MODERATOR = "MODERATOR", "Moderator"
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.USER)
    trust_score = models.FloatField(default=50.0)
    bio = models.TextField(blank=True, null=True)
    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=64, blank=True, null=True)
    followers = models.ManyToManyField(User, related_name="following_profiles", blank=True)

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
    ai_verdict = models.CharField(max_length=20, blank=True, null=True)
    final_verdict = models.CharField(max_length=20, blank=True, null=True)
    verdict = models.CharField(max_length=20, blank=True, null=True)
    consensus_score = models.FloatField(blank=True, null=True)
    score_context = models.CharField(max_length=255, null=True, blank=True)
    source_type = models.CharField(max_length=50, blank=True, null=True)
    verified_via = models.CharField(
        max_length=20,
        choices=VerificationSource.choices,
        default=VerificationSource.PENDING,
    )

    source_link = models.URLField(max_length=500, blank=True, null=True)
    top_verdict_source = models.URLField(max_length=500, blank=True, null=True)

    last_updated = models.DateTimeField(auto_now=True)
    is_ai_generated = models.BooleanField(default=False)

    # Deduplication fingerprint for claim matching / resolution cache
    claim_fingerprint = models.CharField(
        max_length=128, db_index=True, blank=True, null=True,
        help_text="Canonical fingerprint for deduplication (pHash for images, normalized URL hash, or text hash)"
    )

    # Semantic similarity embedding for paraphrase detection
    claim_embedding = VectorField(
        dimensions=384, null=True, blank=True,
        help_text="384-dim embedding vector from all-MiniLM-L6-v2 for semantic claim matching"
    )

    def __str__(self):
        return f"Claim {self.id} - Type: {self.claim_type} - Final Verdict: {self.final_verdict or self.verdict}"
    
    def compute_final_verdict(self):
        """
        Compute final verdict based on verified evidence in all threads for this claim.
        Returns the verdict that should be set as final_verdict.
        
        Logic:
        - If all verified evidence SUPPORTS → FACT
        - If all verified evidence CONTRADICTS → FAKE
        - If mixed → MISLEADING (partially accurate)
        - If only CONTEXT/VERIFICATION → no change (keep existing)
        - If no verified evidence → no change
        """
        from django.db.models import Q
        
        # Get all threads for this claim
        threads = self.threads.all()
        
        # Get all VERIFIED evidence submissions for these threads
        verified_evidence = EvidenceSubmission.objects.filter(
            thread__in=threads,
            evidence_status='VERIFIED'
        ).select_related('thread')
        
        if not verified_evidence.exists():
            return None
        
        # Count evidence types
        supports_count = verified_evidence.filter(evidence_type='SUPPORTS CLAIM').count()
        contradicts_count = verified_evidence.filter(evidence_type='CONTRADICTS CLAIM').count()
        context_count = verified_evidence.filter(evidence_type='PROVIDES CONTEXT').count()
        verification_count = verified_evidence.filter(evidence_type='SOURCE VERIFICATION').count()
        
        # Determine verdict based on evidence
        if contradicts_count == 0 and supports_count > 0:
            return 'FACT'  # All verified evidence supports the claim
        elif supports_count == 0 and contradicts_count > 0:
            return 'FAKE'  # All verified evidence contradicts the claim
        elif supports_count > 0 and contradicts_count > 0:
            return 'MISLEADING'  # Mixed evidence - partially accurate
        else:
            return None  # Not enough decisive evidence

    class Meta:
        indexes = [
            HnswIndex(
                name="claim_embedding_hnsw_idx",
                fields=["claim_embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            )
        ]


class Thread(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"
        REJECTED = "REJECTED", "Rejected"    
    class EscalationReason(models.TextChoices):
        INCORRECT_VERDICT = "INCORRECT_VERDICT", "AI gave an incorrect or unverified verdict"
        LOW_CONFIDENCE = "LOW_CONFIDENCE", "AI confidence score is too low"
        MISSING_CONTEXT = "MISSING_CONTEXT", "The context provided is incomplete or missing"
        OUTDATED_INFO = "OUTDATED_INFO", "The AI relied on outdated information or news"
        OTHER = "OTHER", "Other"
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name="threads")
    author = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="authored_threads"
    )
    caption = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, blank=True, null=True, default="OPEN")
    # flag_reason = models.CharField(max_length=20, choices=FlagReason.choices, blank=True, null=True)
    escalation_reason = models.CharField(max_length=20, choices=EscalationReason.choices, blank=True, null=True)
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


class FlagResolutionLog(models.Model):
    class ResolutionAction(models.TextChoices):
        DISMISS = "DISMISS", "Dismiss"
        REMOVE = "REMOVE", "Remove"
        ESCALATE = "ESCALATE", "Escalate"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="flag_resolution_logs")
    flagged_by = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="resolved_thread_flags"
    )
    reason = models.CharField(max_length=20, choices=ThreadFlag.Reason.choices)
    notes = models.TextField(blank=True, null=True)
    flagged_at = models.DateTimeField()
    resolved_action = models.CharField(max_length=20, choices=ResolutionAction.choices)
    is_valid_report = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="resolved_flags_moderated"
    )
    resolved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-resolved_at"]

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
    verified_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="verified_evidence", help_text="Moderator who verified this evidence"
    )
    verified_at = models.DateTimeField(
        null=True, blank=True, help_text="Timestamp when evidence was verified by moderator"
    )
    moderator_notes = models.TextField(blank=True, null=True, help_text="Notes from moderator why evidence was verified/rejected")

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
