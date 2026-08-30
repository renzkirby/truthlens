from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.conf import settings
from django.contrib.postgres.search import SearchVectorField, SearchVector
from django.contrib.postgres.indexes import GinIndex
from pgvector.django import VectorField, HnswIndex
import uuid


def _claim_vector_indexes():
    engine = settings.DATABASES.get("default", {}).get("ENGINE", "")
    if "postgresql" not in engine:
        return []
    return [
        HnswIndex(
            name="claim_embedding_hnsw_idx",
            fields=["claim_embedding"],
            m=16,
            ef_construction=128,
            opclasses=["vector_cosine_ops"],
        )
    ]


# Create your models here.
class UserProfile(models.Model):
    class Role(models.TextChoices):
        USER = "USER", "User"
        MOD = "MOD", "Moderator"
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.USER)
    organization_name = models.CharField(max_length=255, blank=True, null=True)
    trust_score = models.FloatField(default=50.0)
    fact_check_points = models.PositiveIntegerField(default=0)
    bio = models.TextField(blank=True, null=True)
    avatar_url = models.URLField(max_length=500, blank=True, null=True)
    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=64, blank=True, null=True)
    email_verification_sent_at = models.DateTimeField(blank=True, null=True)
    followers = models.ManyToManyField(User, related_name="following_profiles", blank=True)
    saved_claims = models.ManyToManyField('Claim', related_name='saved_by_users', blank=True)
    has_completed_onboarding = models.BooleanField(default=False)

    def __str__(self):
        return f"UserProfile {self.id} - User: {self.user.username} - Trust Score: {self.trust_score}"


class Organization(models.Model):
    class OrganizationType(models.TextChoices):
        FACT_CHECKING = (
            "FACT_CHECKING",
            "Fact-Checking Organization",
        )
        NEWS = (
            "NEWS",
            "News Organization",
        )
        UNIVERSITY = (
            "UNIVERSITY",
            "University",
        )
        RESEARCH = (
            "RESEARCH",
            "Research Organization",
        )
        NGO = (
            "NGO",
            "Non-Governmental Organization",
        )
        GOVERNMENT = (
            "GOVERNMENT",
            "Government Organization",
        )
        OTHER = (
            "OTHER",
            "Other",
        )

    class VerificationStatus(models.TextChoices):
        UNVERIFIED = (
            "UNVERIFIED",
            "Unverified",
        )
        PENDING = (
            "PENDING",
            "Pending Verification",
        )
        VERIFIED = (
            "VERIFIED",
            "Verified",
        )
        REJECTED = (
            "REJECTED",
            "Rejected",
        )

    class PartnerStatus(models.TextChoices):
        NONE = (
            "NONE",
            "Not a Partner",
        )
        ACTIVE = (
            "ACTIVE",
            "Active",
        )
        SUSPENDED = (
            "SUSPENDED",
            "Suspended",
        )
        FORMER = (
            "FORMER",
            "Former Partner",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    name = models.CharField(
        max_length=255,
    )

    slug = models.SlugField(
        max_length=255,
        unique=True,
    )

    description = models.TextField(
        blank=True,
        null=True,
    )

    website = models.URLField(
        max_length=2000,
        blank=True,
        null=True,
    )

    logo_url = models.URLField(
        max_length=2000,
        blank=True,
        null=True,
    )

    organization_type = models.CharField(
        max_length=30,
        choices=OrganizationType.choices,
        default=OrganizationType.OTHER,
    )

    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.UNVERIFIED,
        db_index=True,
    )

    partner_status = models.CharField(
        max_length=20,
        choices=PartnerStatus.choices,
        default=PartnerStatus.NONE,
        db_index=True,
    )

    expertise_areas = models.JSONField(
        default=list,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["name"]

        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                name="unique_organization_name_ci",
            ),
        ]

    def __str__(self):
        return self.name


class OrganizationMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner"
        ADMIN = "ADMIN", "Administrator"
        LEAD_VERIFIER = (
            "LEAD_VERIFIER",
            "Lead Verifier",
        )
        MODERATOR = (
            "MODERATOR",
            "Moderator",
        )
        RESEARCHER = (
            "RESEARCHER",
            "Researcher",
        )
        CONTRIBUTOR = (
            "CONTRIBUTOR",
            "Contributor",
        )

    class Status(models.TextChoices):
        PENDING = (
            "PENDING",
            "Pending",
        )
        ACTIVE = (
            "ACTIVE",
            "Active",
        )
        SUSPENDED = (
            "SUSPENDED",
            "Suspended",
        )
        LEFT = (
            "LEFT",
            "Left Organization",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )

    user = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="organization_memberships",
    )

    role = models.CharField(
        max_length=30,
        choices=Role.choices,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    joined_at = models.DateTimeField(
        auto_now_add=True,
    )

    approved_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    approved_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name=(
            "approved_organization_memberships"
        ),
    )

    class Meta:
        ordering = [
            "organization_id",
            "user_id",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "organization",
                    "user",
                ],
                name=(
                    "unique_user_organization_membership"
                ),
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "organization",
                    "status",
                ],
                name="org_member_org_status_idx",
            ),
            models.Index(
                fields=[
                    "user",
                    "status",
                ],
                name="org_member_user_status_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.user.username} - "
            f"{self.organization.name} "
            f"({self.role})"
        )


class Claim(models.Model):
    class VerificationSource(models.TextChoices):
        AI_EXTENSION = "AI_EXTENSION", "AI Extension"
        COMMUNITY = "COMMUNITY", "Community Platform"
        PENDING = "PENDING", "Pending"

    class ClaimType(models.TextChoices):
        TEXT = "TEXT", "Text"
        IMAGE = "IMAGE", "Image"
        VIDEO = "VIDEO", "Video"
        URL = "URL", "URL"
        FILE = "FILE", "File"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    claim_type = models.CharField(max_length=20, choices=ClaimType.choices, default=ClaimType.TEXT)
    media_url = models.CharField(max_length=2000, blank=True, null=True)
    image = models.ImageField(upload_to='claims/images/', null=True, blank=True)
    media_hash = models.CharField(max_length=64, blank=True, null=True)
    url_link = models.URLField(max_length=2000, blank=True, null=True)
    context_text = models.TextField(blank=True, null=True)

    ai_summary = models.TextField(blank=True, null=True)
    ai_reasoning = models.TextField(blank=True, null=True)
    ai_verdict = models.CharField(max_length=20, blank=True, null=True)
    final_verdict = models.CharField(max_length=20, blank=True, null=True)
    consensus_score = models.FloatField(blank=True, null=True)
    score_context = models.CharField(max_length=255, null=True, blank=True)
    source_type = models.CharField(max_length=50, blank=True, null=True)
    verified_via = models.CharField(
        max_length=20,
        choices=VerificationSource.choices,
        default=VerificationSource.PENDING,
    )

    source_link = models.URLField(max_length=2000, blank=True, null=True)
    top_verdict_source = models.URLField(max_length=2000, blank=True, null=True)
    ai_sources = models.JSONField(default=list, blank=True, null=True)

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
        return f"Claim {self.id} - Type: {self.claim_type} - Final Verdict: {self.final_verdict or self.ai_verdict}"
    
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
        indexes = _claim_vector_indexes()

class CanonicalSource(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    name = models.CharField(max_length=255)

    domain = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    source_type = models.CharField(
        max_length=50,
        blank=True,
        null=True,
    )

    canonical_url = models.URLField(
        max_length=2000,
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class EvidenceSource(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    canonical_source = models.ForeignKey(
        CanonicalSource,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidence_sources",
    )

    provider = models.CharField(
        max_length=50
    )

    url = models.URLField(
        max_length=2000,
        blank=True,
        null=True,
    )

    canonical_url = models.URLField(
        max_length=2000,
        blank=True,
        null=True,
    )

    title = models.TextField(
        blank=True,
        null=True,
    )

    publisher = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    source_type = models.CharField(
        max_length=50,
        blank=True,
        null=True,
    )

    authority_score = models.FloatField(
        null=True,
        blank=True,
    )

    content = models.TextField(
        blank=True,
        null=True,
    )

    content_hash = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        db_index=True,
    )

    published_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    retrieved_at = models.DateTimeField(
        auto_now_add=True,
    )

    raw_reference = models.JSONField(
        null=True,
        blank=True,
        help_text=(
            "Provider-specific identifiers only. "
            "Not for general content storage."
            "Example: {'gfc_claim_id': '...', 'tavily_result_index': 2}"
        ),
    )

    class Meta:
        indexes = [
            models.Index(
                fields=["provider"],
                name="evidence_provider_idx",
            ),
            models.Index(
                fields=["publisher"],
                name="evidence_publisher_idx",
            ),
        ]
        ordering = ["-retrieved_at"]

    def __str__(self):
        return self.title or self.url or str(self.id)

class VerificationRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        COMPLETED = "COMPLETED", "Completed"
        ABSTAINED = "ABSTAINED", "Abstained"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    claim = models.ForeignKey(
        Claim,
        on_delete=models.CASCADE,
        related_name="verification_runs",
    )

    triggered_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verification_runs",
        help_text="User who triggered this verification run, if authenticated.",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    pipeline_version = models.CharField(
        max_length=32,
        default="1.0.0",
        help_text=(
            "Version of the verification pipeline used for this run."
        ),
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    failure_stage = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    failure_code = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    failure_message = models.TextField(
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"VerificationRun {self.id} - {self.status}"

class VerificationEvidence(models.Model):
    class Stance(models.TextChoices):
        SUPPORTS = "SUPPORTS", "Supports"
        REFUTES = "REFUTES", "Refutes"
        CONTEXT = "CONTEXT", "Context"
        UNKNOWN = "UNKNOWN", "Unknown"

    class EvidenceRole(models.TextChoices):
        PRIMARY = "PRIMARY", "Primary Source"
        SECONDARY = "SECONDARY", "Secondary Source"
        FACT_CHECK = "FACT_CHECK", "Fact Check"
        CONTEXTUAL = "CONTEXTUAL", "Contextual"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    verification_run = models.ForeignKey(
        VerificationRun,
        on_delete=models.CASCADE,
        related_name="evidence",
    )

    evidence_source = models.ForeignKey(
        EvidenceSource,
        on_delete=models.CASCADE,
        related_name="verification_evidence",
    )

    relevance_score = models.FloatField(
        null=True,
        blank=True,
    )

    directness_score = models.FloatField(
        null=True,
        blank=True,
    )

    recency_score = models.FloatField(
        null=True,
        blank=True,
    )

    stance = models.CharField(
        max_length=20,
        choices=Stance.choices,
        default=Stance.UNKNOWN,
    )

    evidence_role = models.CharField(
        max_length=20,
        choices=EvidenceRole.choices,
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["verification_run", "evidence_source"],
                name="unique_evidence_per_verification_run",
            )
        ]   
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"VerificationEvidence {self.id} "
            f"- {self.stance}"
        )    

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
    display_id = models.PositiveIntegerField(unique=True, editable=False, null=True)
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


class ClaimCheckHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE, related_name="claim_check_history")
    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name="check_history")
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-checked_at"]

    def __str__(self):
        return f"ClaimCheckHistory {self.id} - User: {self.user.username} - Claim ID: {self.claim.id}"

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

    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    resolution_case = models.ForeignKey(
        "ModerationCase",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports",
    )
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["thread", "flagged_by"],
                condition=Q(resolved_at__isnull=True),
                name="unique_active_flag_per_thread_user",
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

    class RejectionReason(models.TextChoices):
        IRRELEVANT = (
            "IRRELEVANT",
            "Irrelevant",
        )
        UNRELIABLE_SOURCE = (
            "UNRELIABLE_SOURCE",
            "Unreliable Source",
        )
        INACCESSIBLE_SOURCE = (
            "INACCESSIBLE_SOURCE",
            "Inaccessible Source",
        )
        DUPLICATE = (
            "DUPLICATE",
            "Duplicate",
        )
        OUTDATED = (
            "OUTDATED",
            "Outdated",
        )
        MISREPRESENTS_SOURCE = (
            "MISREPRESENTS_SOURCE",
            "Misrepresents Source",
        )
        INSUFFICIENT_CONTEXT = (
            "INSUFFICIENT_CONTEXT",
            "Insufficient Context",
        )
        FABRICATED = (
            "FABRICATED",
            "Fabricated",
        )
        OTHER = (
            "OTHER",
            "Other",
        )

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
    rejection_reason = models.CharField(
        max_length=30,
        choices=RejectionReason.choices,
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"EvidenceSubmission {self.id} - Thread ID: {self.thread.id} - Contributor: {self.contributor.username}"


class ModerationCase(models.Model):
    class CaseType(models.TextChoices):
        SAFETY = "SAFETY", "Safety Review"
        EVIDENCE = "EVIDENCE", "Evidence Review"
        ADJUDICATION = "ADJUDICATION", "Verdict Adjudication"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        IN_REVIEW = "IN_REVIEW", "In Review"
        ESCALATED = "ESCALATED", "Escalated"
        RESOLVED = "RESOLVED", "Resolved"
        REOPENED = "REOPENED", "Reopened"
        CANCELLED = "CANCELLED", "Cancelled"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        NORMAL = "NORMAL", "Normal"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    class Source(models.TextChoices):
        USER_REPORT = "USER_REPORT", "User Report"
        EVIDENCE_SUBMISSION = "EVIDENCE_SUBMISSION", "Evidence Submission"
        COMMUNITY_ESCALATION = "COMMUNITY_ESCALATION", "Community Escalation"
        SYSTEM = "SYSTEM", "System Generated"
        MODERATOR = "MODERATOR", "Moderator Created"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    case_type = models.CharField(
        max_length=20,
        choices=CaseType.choices,
        db_index=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
    )

    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.NORMAL,
        db_index=True,
    )

    source = models.CharField(
        max_length=30,
        choices=Source.choices,
        default=Source.SYSTEM,
    )

    thread = models.ForeignKey(
        Thread,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderation_cases",
    )

    claim = models.ForeignKey(
        Claim,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderation_cases",
    )

    evidence_submission = models.ForeignKey(
        EvidenceSubmission,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderation_cases",
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderation_cases",
    )

    assigned_to = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_moderation_cases",
    )

    assigned_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    resolution_code = models.CharField(
        max_length=50,
        blank=True,
        null=True,
    )

    resolution_summary = models.TextField(
        blank=True,
        null=True,
    )

    resolved_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_moderation_cases",
    )

    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def clean(self):
        super().clean()

        targets = {
            self.CaseType.SAFETY: self.thread_id,
            self.CaseType.EVIDENCE: self.evidence_submission_id,
            self.CaseType.ADJUDICATION: self.claim_id,
        }

        expected_target = targets.get(self.case_type)

        if expected_target is None:
            raise ValidationError(
                {
                    "case_type":
                        "This moderation case does not have its required target."
                }
            )

        if self.case_type == self.CaseType.SAFETY:
            invalid_extra_target = (
                self.claim_id is not None
                or self.evidence_submission_id is not None
            )

        elif self.case_type == self.CaseType.EVIDENCE:
            invalid_extra_target = (
                self.thread_id is not None
                or self.claim_id is not None
            )

        else:
            invalid_extra_target = (
                self.thread_id is not None
                or self.evidence_submission_id is not None
            )

        if invalid_extra_target:
            raise ValidationError(
                {
                    "case_type":
                        "A moderation case must use only the target "
                        "appropriate for its case type."
                }
            )

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=["case_type", "status", "-created_at"],
                name="mod_case_type_status_idx",
            ),
            models.Index(
                fields=["assigned_to", "status"],
                name="mod_case_assignee_idx",
            ),
            models.Index(
                fields=["priority", "status", "-created_at"],
                name="mod_case_priority_idx",
            ),
            models.Index(
                fields=["organization", "status"],
                name="mod_case_org_status_idx",
            ),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["thread"],
                condition=Q(
                    case_type="SAFETY",
                    status__in=[
                        "OPEN",
                        "IN_REVIEW",
                        "ESCALATED",
                        "REOPENED",
                    ],
                ),
                name="uniq_active_safety_case_thread",
            ),
            models.UniqueConstraint(
                fields=["evidence_submission"],
                condition=Q(
                    case_type="EVIDENCE",
                    status__in=[
                        "OPEN",
                        "IN_REVIEW",
                        "ESCALATED",
                        "REOPENED",
                    ],
                ),
                name="uniq_active_evidence_case",
            ),
            models.UniqueConstraint(
                fields=["claim"],
                condition=Q(
                    case_type="ADJUDICATION",
                    status__in=[
                        "OPEN",
                        "IN_REVIEW",
                        "ESCALATED",
                        "REOPENED",
                    ],
                ),
                name="uniq_active_adjudication_case",
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_case_type_display()} "
            f"{self.id} - {self.status}"
        )


class ModerationEvent(models.Model):
    class EventType(models.TextChoices):
        CASE_CREATED = "CASE_CREATED", "Case Created"
        CASE_CLAIMED = "CASE_CLAIMED", "Case Claimed"
        CASE_ASSIGNED = "CASE_ASSIGNED", "Case Assigned"
        CASE_UNASSIGNED = "CASE_UNASSIGNED", "Case Unassigned"

        REVIEW_STARTED = "REVIEW_STARTED", "Review Started"

        CASE_ESCALATED = "CASE_ESCALATED", "Case Escalated"
        CASE_RESOLVED = "CASE_RESOLVED", "Case Resolved"
        CASE_REOPENED = "CASE_REOPENED", "Case Reopened"
        CASE_CANCELLED = "CASE_CANCELLED", "Case Cancelled"

        SAFETY_DISMISSED = (
            "SAFETY_DISMISSED",
            "Safety Report Dismissed",
        )
        SAFETY_VIOLATION_CONFIRMED = (
            "SAFETY_VIOLATION_CONFIRMED",
            "Safety Violation Confirmed",
        )
        CONTENT_REMOVED = (
            "CONTENT_REMOVED",
            "Content Removed",
        )

        EVIDENCE_VERIFIED = (
            "EVIDENCE_VERIFIED",
            "Evidence Verified",
        )
        EVIDENCE_REJECTED = (
            "EVIDENCE_REJECTED",
            "Evidence Rejected",
        )
        EVIDENCE_REOPENED = (
            "EVIDENCE_REOPENED",
            "Evidence Review Reopened",
        )

        ADJUDICATION_STARTED = (
            "ADJUDICATION_STARTED",
            "Adjudication Started",
        )
        VERDICT_ISSUED = (
            "VERDICT_ISSUED",
            "Verdict Issued",
        )
        VERDICT_REOPENED = (
            "VERDICT_REOPENED",
            "Verdict Reopened",
        )
        VERDICT_REVISED = (
            "VERDICT_REVISED",
            "Verdict Revised",
        )

        ARTICLE_DRAFT_CREATED = (
            "ARTICLE_DRAFT_CREATED",
            "Article Draft Created",
        )
        ARTICLE_SUBMITTED = (
            "ARTICLE_SUBMITTED",
            "Article Submitted for Review",
        )
        ARTICLE_PUBLISHED = (
            "ARTICLE_PUBLISHED",
            "Article Published",
        )
        ARTICLE_REVISED = (
            "ARTICLE_REVISED",
            "Article Revised",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    case = models.ForeignKey(
        ModerationCase,
        on_delete=models.CASCADE,
        related_name="events",
    )

    actor = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderation_events",
    )

    event_type = models.CharField(
        max_length=50,
        choices=EventType.choices,
        db_index=True,
    )

    from_status = models.CharField(
        max_length=20,
        blank=True,
        null=True,
    )

    to_status = models.CharField(
        max_length=20,
        blank=True,
        null=True,
    )

    reason_code = models.CharField(
        max_length=50,
        blank=True,
        null=True,
    )

    notes = models.TextField(
        blank=True,
        null=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["created_at"]

        indexes = [
            models.Index(
                fields=["case", "created_at"],
                name="mod_event_case_time_idx",
            ),
            models.Index(
                fields=["event_type", "-created_at"],
                name="mod_event_type_time_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(
                "Moderation events are append-only and cannot be modified."
            )

        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Moderation events are append-only and cannot be deleted directly."
        )

    def __str__(self):
        return (
            f"{self.event_type} - "
            f"Case {self.case_id}"
        )


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

class OfficialFactCheck(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # 1. The Core Data (ClaimReview Standard)
    canonical_claim = models.TextField(
        help_text="A clean, third-person statement of the rumor (e.g., 'The Pope wore a white puffer jacket.')"
    )
    verdict = models.CharField(max_length=20) # FACT, FAKE, MISLEADING, SATIRE
    summary = models.TextField(help_text="The official explanation approved by a moderator.")
    sources = models.JSONField(default=list, blank=True, help_text="List of verified URL strings.")
    
    # 2. Hybrid Search Fields
    embedding = VectorField(
        dimensions=384, null=True, blank=True, 
        help_text="Sentence transformer embedding for Semantic Search"
    )
    search_vector = SearchVectorField(
        null=True, blank=True, 
        help_text="PostgreSQL tsvector for BM25 Keyword Search"
    )

    # 3. Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    published_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, related_name="published_fact_checks"
    )
    source_thread = models.ForeignKey(
        'Thread', on_delete=models.SET_NULL, null=True, blank=True,
        help_text="Links back to the community thread if auto-published."
    )

    class Meta:
        indexes = [
            HnswIndex(
                name="official_claim_hnsw_idx",
                fields=["embedding"],
                m=16,
                ef_construction=128,
                opclasses=["vector_cosine_ops"],
            ),
            GinIndex(fields=["search_vector"], name="official_claim_gin_idx"),
        ]

    def save(self, *args, **kwargs):
        # Automatically generate the PostgreSQL Search Vector when saving
        super().save(*args, **kwargs)
        if self.canonical_claim:
            # We assign Weight 'A' to the claim, and 'B' to the summary so keywords in the claim rank higher.
            OfficialFactCheck.objects.filter(pk=self.pk).update(
                search_vector=SearchVector('canonical_claim', weight='A') + SearchVector('summary', weight='B')
            )

    def __str__(self):
        return f"[{self.verdict}] {self.canonical_claim[:50]}..."