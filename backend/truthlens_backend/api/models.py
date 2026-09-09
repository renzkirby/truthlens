from django.db import models
from django.db.models import Prefetch, Q
from django.db.models.functions import Lower
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.contrib.auth.models import User
from django.conf import settings
from django.contrib.postgres.search import SearchVectorField, SearchVector
from django.contrib.postgres.indexes import GinIndex
from pgvector.django import VectorField, HnswIndex
from django.utils import timezone
import uuid

from .evidence_snapshot_schema import (
    CURRENT_SCHEMA_VERSION as EVIDENCE_SNAPSHOT_SCHEMA_VERSION,
    EVIDENCE_RECORD_FIELDS as EVIDENCE_SNAPSHOT_RECORD_FIELDS,
    EvidenceSnapshotSchemaError,
    validate_evidence_snapshot,
)
from .publication_snapshot_schema import (
    CURRENT_SCHEMA_VERSION as PUBLICATION_SNAPSHOT_SCHEMA_VERSION,
    PublicationSnapshotSchemaError,
    validate_publication_snapshot,
)


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
    followers = models.ManyToManyField(
        User, related_name="following_profiles", blank=True
    )
    saved_claims = models.ManyToManyField(
        "Claim", related_name="saved_by_users", blank=True
    )
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

    public_profile_enabled = models.BooleanField(
        default=False,
    )

    public_logo_enabled = models.BooleanField(
        default=False,
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
        related_name=("approved_organization_memberships"),
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
                name=("unique_user_organization_membership"),
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
        return f"{self.user.username} - " f"{self.organization.name} " f"({self.role})"


class OrganizationInvitation(models.Model):
    class Status(models.TextChoices):
        PENDING = (
            "PENDING",
            "Pending",
        )
        ACCEPTED = (
            "ACCEPTED",
            "Accepted",
        )
        CANCELLED = (
            "CANCELLED",
            "Cancelled",
        )
        EXPIRED = (
            "EXPIRED",
            "Expired",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="invitations",
    )

    email = models.EmailField(
        max_length=254,
        db_index=True,
    )

    invited_role = models.CharField(
        max_length=30,
        choices=(OrganizationMembership.Role.choices),
    )

    invited_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name=("sent_organization_invitations"),
    )

    # Store only the digest. The raw invitation
    # token must never be persisted.
    token_digest = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    expires_at = models.DateTimeField(
        db_index=True,
    )

    last_sent_at = models.DateTimeField()

    send_count = models.PositiveIntegerField(
        default=1,
    )

    accepted_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name=("accepted_organization_invitations"),
    )

    accepted_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    cancelled_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name=("cancelled_organization_invitations"),
    )

    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "-created_at",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "organization",
                    "email",
                ],
                condition=Q(
                    status="PENDING",
                ),
                name=("unique_pending_org_" "invitation_email"),
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "organization",
                    "status",
                ],
                name=("org_invite_org_status_idx"),
            ),
            models.Index(
                fields=[
                    "email",
                    "status",
                ],
                name=("org_invite_email_status_idx"),
            ),
        ]

    def save(
        self,
        *args,
        **kwargs,
    ):
        self.email = str(self.email or "").strip().lower()

        super().save(
            *args,
            **kwargs,
        )

    def __str__(self):
        return f"{self.email} → " f"{self.organization.name} " f"({self.invited_role})"


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

    claim_type = models.CharField(
        max_length=20, choices=ClaimType.choices, default=ClaimType.TEXT
    )
    media_url = models.CharField(max_length=2000, blank=True, null=True)
    image = models.ImageField(upload_to="claims/images/", null=True, blank=True)
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
        max_length=128,
        db_index=True,
        blank=True,
        null=True,
        help_text="Canonical fingerprint for deduplication (pHash for images, normalized URL hash, or text hash)",
    )

    # Semantic similarity embedding for paraphrase detection
    claim_embedding = VectorField(
        dimensions=384,
        null=True,
        blank=True,
        help_text="384-dim embedding vector from all-MiniLM-L6-v2 for semantic claim matching",
    )

    def __str__(self):
        return (
            f"Claim {self.id} - Type: {self.claim_type} - "
            f"Cached Final Verdict: {self.final_verdict or 'None'} - "
            f"AI Verdict: {self.ai_verdict or 'None'}"
        )

    def compute_final_verdict(self):
        """
        Legacy evidence-consensus calculation retained for compatibility.

        This result is not an authoritative claim adjudication and must not be
        written to final_verdict.  Only the adjudication service establishes a
        human claim verdict.

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
            thread__in=threads, evidence_status="VERIFIED"
        ).select_related("thread")

        if not verified_evidence.exists():
            return None

        # Count evidence types
        supports_count = verified_evidence.filter(
            evidence_type="SUPPORTS CLAIM"
        ).count()
        contradicts_count = verified_evidence.filter(
            evidence_type="CONTRADICTS CLAIM"
        ).count()
        context_count = verified_evidence.filter(
            evidence_type="PROVIDES CONTEXT"
        ).count()
        verification_count = verified_evidence.filter(
            evidence_type="SOURCE VERIFICATION"
        ).count()

        # Determine verdict based on evidence
        if contradicts_count == 0 and supports_count > 0:
            return "FACT"  # All verified evidence supports the claim
        elif supports_count == 0 and contradicts_count > 0:
            return "FAKE"  # All verified evidence contradicts the claim
        elif supports_count > 0 and contradicts_count > 0:
            return "MISLEADING"  # Mixed evidence - partially accurate
        else:
            return None  # Not enough decisive evidence

    class Meta:
        indexes = _claim_vector_indexes()


class VerificationAssignment(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        ACTIVE = "ACTIVE", "Active"
        RELEASED = "RELEASED", "Released"
        COMPLETED = "COMPLETED", "Completed"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    claim = models.ForeignKey(
        Claim,
        on_delete=models.CASCADE,
        related_name="verification_assignments",
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verification_assignments",
    )

    claimed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="claimed_verification_assignments",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AVAILABLE,
        db_index=True,
    )

    claimed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    released_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["claim"],
                condition=Q(
                    status__in=[
                        "AVAILABLE",
                        "ACTIVE",
                    ]
                ),
                name=("unique_open_verification_" "assignment_per_claim"),
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "status",
                    "-created_at",
                ],
                name="verify_assign_status_idx",
            ),
            models.Index(
                fields=[
                    "organization",
                    "status",
                ],
                name="verify_assign_org_idx",
            ),
        ]

    def clean(self):
        super().clean()

        if self.status == self.Status.AVAILABLE and self.organization_id is not None:
            raise ValidationError(
                {
                    "organization": "Available verification work "
                    "must not already belong to an "
                    "organization."
                }
            )

        if self.status == self.Status.ACTIVE and self.organization_id is None:
            raise ValidationError(
                {
                    "organization": "Active verification work must "
                    "belong to an organization."
                }
            )

        if self.status == self.Status.ACTIVE and self.claimed_by_id is None:
            raise ValidationError(
                {
                    "claimed_by": "Active verification work must "
                    "record who claimed it."
                }
            )

    def __str__(self):
        organization_name = (
            self.organization.name if self.organization else "Unassigned"
        )

        return f"{self.claim_id} - " f"{organization_name} " f"({self.status})"


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

    provider = models.CharField(max_length=50)

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
        help_text=("Version of the verification pipeline used for this run."),
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
        return f"VerificationEvidence {self.id} " f"- {self.stance}"


class Thread(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"
        REJECTED = "REJECTED", "Rejected"

    class EscalationReason(models.TextChoices):
        INCORRECT_VERDICT = (
            "INCORRECT_VERDICT",
            "AI gave an incorrect or unverified verdict",
        )
        LOW_CONFIDENCE = "LOW_CONFIDENCE", "AI confidence score is too low"
        MISSING_CONTEXT = (
            "MISSING_CONTEXT",
            "The context provided is incomplete or missing",
        )
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
    escalation_reason = models.CharField(
        max_length=20, choices=EscalationReason.choices, blank=True, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    moderator_verdict = models.CharField(max_length=20, blank=True, null=True)
    moderator_notes = models.TextField(blank=True, null=True)
    moderated_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderated_threads",
    )
    moderated_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Thread {self.id} - Claim ID: {self.claim.id} - Author: {self.author.username}"


class ClaimCheckHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="claim_check_history"
    )
    claim = models.ForeignKey(
        Claim, on_delete=models.CASCADE, related_name="check_history"
    )
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
    thread = models.ForeignKey(
        Thread, on_delete=models.CASCADE, related_name="flag_resolution_logs"
    )
    flagged_by = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="resolved_thread_flags"
    )
    reason = models.CharField(max_length=20, choices=ThreadFlag.Reason.choices)
    notes = models.TextField(blank=True, null=True)
    flagged_at = models.DateTimeField()
    resolved_action = models.CharField(max_length=20, choices=ResolutionAction.choices)
    is_valid_report = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_flags_moderated",
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
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_evidence",
        help_text="Moderator who verified this evidence",
    )
    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when evidence was verified by moderator",
    )
    moderator_notes = models.TextField(
        blank=True,
        null=True,
        help_text="Notes from moderator why evidence was verified/rejected",
    )
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
                {"case_type": "This moderation case does not have its required target."}
            )

        if self.case_type == self.CaseType.SAFETY:
            invalid_extra_target = (
                self.claim_id is not None or self.evidence_submission_id is not None
            )

        elif self.case_type == self.CaseType.EVIDENCE:
            invalid_extra_target = (
                self.thread_id is not None or self.claim_id is not None
            )

        else:
            invalid_extra_target = (
                self.thread_id is not None or self.evidence_submission_id is not None
            )

        if invalid_extra_target:
            raise ValidationError(
                {
                    "case_type": "A moderation case must use only the target "
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
        return f"{self.get_case_type_display()} " f"{self.id} - {self.status}"


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
        return f"{self.event_type} - " f"Case {self.case_id}"


class AdjudicationDecision(models.Model):
    class Verdict(models.TextChoices):
        FACT = "FACT", "Fact"
        FAKE = "FAKE", "Fake"
        MISLEADING = "MISLEADING", "Misleading"
        SATIRE = "SATIRE", "Satire"
        UNVERIFIED = "UNVERIFIED", "Unverified"

    class DecisionSource(models.TextChoices):
        HUMAN_REVIEW = (
            "HUMAN_REVIEW",
            "Human Review",
        )
        LEGACY_MIGRATION = (
            "LEGACY_MIGRATION",
            "Legacy Migration",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    claim = models.ForeignKey(
        Claim,
        on_delete=models.PROTECT,
        related_name="adjudication_decisions",
    )

    moderation_case = models.ForeignKey(
        ModerationCase,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adjudication_decisions",
    )

    verdict = models.CharField(
        max_length=20,
        choices=Verdict.choices,
    )

    canonical_claim = models.TextField(
        blank=True,
    )

    rationale = models.TextField(
        blank=True,
    )

    decided_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adjudication_decisions",
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adjudication_decisions",
    )

    verification_run = models.ForeignKey(
        VerificationRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adjudication_decisions",
    )

    ai_verdict_snapshot = models.CharField(
        max_length=20,
        null=True,
        blank=True,
    )

    ai_confidence_snapshot = models.FloatField(
        null=True,
        blank=True,
    )

    ai_summary_snapshot = models.TextField(
        null=True,
        blank=True,
    )

    ai_pipeline_version_snapshot = models.CharField(
        max_length=32,
        null=True,
        blank=True,
    )

    decision_source = models.CharField(
        max_length=30,
        choices=DecisionSource.choices,
        default=DecisionSource.HUMAN_REVIEW,
    )

    revision_number = models.PositiveIntegerField(
        default=1,
    )

    supersedes = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="superseded_by",
    )

    is_current = models.BooleanField(
        default=True,
        db_index=True,
    )

    decided_at = models.DateTimeField(
        default=timezone.now,
    )

    class Meta:
        ordering = [
            "-decided_at",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["claim"],
                condition=Q(is_current=True),
                name=("uniq_current_adjudication_" "decision_claim"),
            ),
            models.UniqueConstraint(
                fields=[
                    "claim",
                    "revision_number",
                ],
                name=("uniq_adjudication_" "claim_revision"),
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "claim",
                    "is_current",
                ],
                name="adj_dec_claim_current_idx",
            ),
            models.Index(
                fields=[
                    "organization",
                    "-decided_at",
                ],
                name="adj_dec_org_time_idx",
            ),
        ]

    def clean(self):
        super().clean()

        if self.supersedes_id and self.supersedes.claim_id != self.claim_id:
            raise ValidationError(
                {
                    "supersedes": "An adjudication decision "
                    "may only supersede a "
                    "decision for the same claim."
                }
            )

    @property
    def ai_agrees(self):
        if not self.ai_verdict_snapshot:
            return None

        return self.ai_verdict_snapshot == self.verdict

    def __str__(self):
        return (
            f"{self.verdict} - "
            f"Claim {self.claim_id} "
            f"(revision {self.revision_number})"
        )


class AdjudicationDecisionEvidenceSnapshot(models.Model):
    CURRENT_SCHEMA_VERSION = EVIDENCE_SNAPSHOT_SCHEMA_VERSION
    EVIDENCE_RECORD_FIELDS = EVIDENCE_SNAPSHOT_RECORD_FIELDS

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    decision = models.OneToOneField(
        AdjudicationDecision,
        on_delete=models.PROTECT,
        related_name="evidence_snapshot",
    )
    claim_id = models.UUIDField(
        editable=False,
    )
    schema_version = models.PositiveSmallIntegerField(
        default=CURRENT_SCHEMA_VERSION,
        editable=False,
    )
    captured_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
    )
    evidence_records = models.JSONField(
        default=list,
        editable=False,
    )

    class Meta:
        ordering = ["-captured_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(
                "Decision evidence snapshots are immutable and cannot be modified."
            )
        if str(self.claim_id) != str(self.decision.claim_id):
            raise ValidationError(
                "Snapshot claim identity must match its adjudication decision."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Decision evidence snapshots cannot be deleted directly.")

    def __str__(self):
        return f"Evidence snapshot for decision {self.decision_id}"


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
    class PublicationStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        IN_REVIEW = "IN_REVIEW", "In Review"
        PUBLISHED = "PUBLISHED", "Published"
        ARCHIVED = "ARCHIVED", "Archived"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    # ---------------------------------
    # Authoritative provenance
    # ---------------------------------

    claim = models.ForeignKey(
        Claim,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="official_fact_checks",
    )

    adjudication_decision = models.ForeignKey(
        AdjudicationDecision,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="official_fact_checks",
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="official_fact_checks",
    )

    # ---------------------------------
    # Fact-check content
    # ---------------------------------

    canonical_claim = models.TextField(
        help_text=(
            "The authoritative canonical claim " "from the adjudication decision."
        )
    )

    verdict = models.CharField(
        max_length=20,
        choices=AdjudicationDecision.Verdict.choices,
    )

    headline = models.CharField(
        max_length=300,
        blank=True,
    )

    summary = models.TextField(
        help_text=("Concise public-facing summary of " "the fact-check.")
    )

    article_body = models.TextField(
        blank=True,
        help_text=("Full public-facing fact-check " "analysis."),
    )

    # Temporary compatibility cache.
    #
    # OfficialFactCheckSource becomes the
    # normalized source of truth.
    sources = models.JSONField(
        default=list,
        blank=True,
    )

    # ---------------------------------
    # Search / knowledge reuse
    # ---------------------------------

    embedding = VectorField(
        dimensions=384,
        null=True,
        blank=True,
        help_text=("Sentence-transformer embedding " "for semantic search."),
    )

    search_vector = SearchVectorField(
        null=True,
        blank=True,
        help_text=("PostgreSQL full-text search vector."),
    )

    # ---------------------------------
    # Publication lifecycle
    # ---------------------------------

    publication_status = models.CharField(
        max_length=20,
        choices=PublicationStatus.choices,
        default=PublicationStatus.DRAFT,
        db_index=True,
    )

    version = models.PositiveIntegerField(
        default=1,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    drafted_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drafted_fact_checks",
    )

    submitted_for_review_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    reviewed_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_fact_checks",
    )

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    published_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_fact_checks",
    )

    published_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    archived_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    # ---------------------------------
    # Legacy compatibility
    # ---------------------------------

    source_thread = models.ForeignKey(
        "Thread",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=(
            "Legacy link to the community " "thread that produced this fact-check."
        ),
    )

    class Meta:
        ordering = [
            "-published_at",
            "-created_at",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "claim",
                    "version",
                ],
                condition=Q(claim__isnull=False),
                name=("uniq_fact_check_" "claim_version"),
            ),
            models.UniqueConstraint(
                fields=["claim"],
                condition=Q(
                    publication_status=("PUBLISHED"),
                    claim__isnull=False,
                ),
                name=("uniq_published_" "fact_check_claim"),
            ),
        ]

        indexes = [
            HnswIndex(
                name="official_claim_hnsw_idx",
                fields=["embedding"],
                m=16,
                ef_construction=128,
                opclasses=["vector_cosine_ops"],
            ),
            GinIndex(
                fields=["search_vector"],
                name="official_claim_gin_idx",
            ),
            models.Index(
                fields=[
                    "publication_status",
                    "-published_at",
                ],
                name=("factcheck_status_" "published_idx"),
            ),
            models.Index(
                fields=[
                    "organization",
                    "publication_status",
                ],
                name=("factcheck_org_" "status_idx"),
            ),
        ]

    SEALED_CONTENT_FIELDS = (
        "claim_id",
        "adjudication_decision_id",
        "organization_id",
        "canonical_claim",
        "verdict",
        "headline",
        "summary",
        "article_body",
        "sources",
        "version",
        "created_at",
        "drafted_by_id",
        "submitted_for_review_at",
        "reviewed_by_id",
        "reviewed_at",
        "published_by_id",
        "published_at",
        "source_thread_id",
    )

    def _validate_sealed_update(self):
        if self._state.adding or not self.pk:
            return
        if not OfficialFactCheckPublicationSnapshot.objects.filter(
            fact_check_id=self.pk
        ).exists():
            return

        stored = (
            OfficialFactCheck.objects.filter(pk=self.pk)
            .values(
                *self.SEALED_CONTENT_FIELDS,
                "publication_status",
            )
            .first()
        )
        if stored is None:
            return
        for field in self.SEALED_CONTENT_FIELDS:
            if getattr(self, field) != stored[field]:
                raise ValidationError(
                    "Sealed fact-check publication content cannot be modified."
                )
        if self.publication_status != stored["publication_status"] and not (
            stored["publication_status"] == self.PublicationStatus.PUBLISHED
            and self.publication_status == self.PublicationStatus.ARCHIVED
        ):
            raise ValidationError(
                "A sealed fact-check only permits the archival lifecycle transition."
            )

    def clean(self):
        super().clean()

        if self.adjudication_decision_id:
            decision = self.adjudication_decision

            if self.claim_id and decision.claim_id != self.claim_id:
                raise ValidationError(
                    {
                        "adjudication_decision": "The adjudication "
                        "decision belongs to "
                        "a different claim."
                    }
                )

            if self.organization_id != decision.organization_id:
                raise ValidationError(
                    {
                        "organization": "The publication "
                        "organization must "
                        "match the "
                        "adjudication "
                        "decision."
                    }
                )

            if self.verdict != decision.verdict:
                raise ValidationError(
                    {
                        "verdict": "The publication "
                        "verdict must match "
                        "the adjudication "
                        "decision."
                    }
                )

        if (
            self.source_thread_id
            and self.claim_id
            and self.source_thread.claim_id != self.claim_id
        ):
            raise ValidationError(
                {
                    "source_thread": "The source thread "
                    "belongs to a different "
                    "claim."
                }
            )

    def save(self, *args, **kwargs):
        self._validate_sealed_update()
        super().save(*args, **kwargs)

        if self.canonical_claim:
            OfficialFactCheck.objects.filter(pk=self.pk).update(
                search_vector=(
                    SearchVector(
                        "canonical_claim",
                        weight="A",
                    )
                    + SearchVector(
                        "headline",
                        weight="A",
                    )
                    + SearchVector(
                        "summary",
                        weight="B",
                    )
                    + SearchVector(
                        "article_body",
                        weight="C",
                    )
                )
            )

    def __str__(self):
        return f"[{self.verdict}] " f"{self.canonical_claim[:50]}..."


class OfficialFactCheckSource(models.Model):
    class SourceType(models.TextChoices):
        VERIFIED_EVIDENCE = (
            "VERIFIED_EVIDENCE",
            "Verified Community Evidence",
        )

        MODERATOR_ADDED = (
            "MODERATOR_ADDED",
            "Moderator Added",
        )

        LEGACY_IMPORT = (
            "LEGACY_IMPORT",
            "Legacy Import",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    fact_check = models.ForeignKey(
        OfficialFactCheck,
        on_delete=models.CASCADE,
        related_name="source_items",
    )

    url = models.URLField(
        max_length=2000,
    )

    title = models.TextField(
        blank=True,
        null=True,
    )

    evidence_submission = models.ForeignKey(
        EvidenceSubmission,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name=("official_fact_check_sources"),
    )

    added_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name=("added_fact_check_sources"),
    )

    source_type = models.CharField(
        max_length=30,
        choices=SourceType.choices,
        default=SourceType.MODERATOR_ADDED,
    )

    is_editorially_selected = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            "Whether an editor explicitly selected this source. Null preserves "
            "unknown provenance for records created before this field existed."
        ),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "fact_check",
                    "url",
                ],
                name=("unique_fact_check_" "source_url"),
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "fact_check",
                    "source_type",
                ],
                name=("factcheck_source_" "type_idx"),
            ),
        ]

    SEALED_CONTENT_FIELDS = (
        "fact_check_id",
        "url",
        "title",
        "evidence_submission_id",
        "added_by_id",
        "source_type",
        "is_editorially_selected",
        "created_at",
    )

    def _fact_check_is_sealed(self, fact_check_id=None):
        fact_check_id = self.fact_check_id if fact_check_id is None else fact_check_id
        return bool(
            fact_check_id
            and OfficialFactCheckPublicationSnapshot.objects.filter(
                fact_check_id=fact_check_id
            ).exists()
        )

    def _validate_sealed_write(self):
        stored = (
            OfficialFactCheckSource.objects.filter(pk=self.pk)
            .values(*self.SEALED_CONTENT_FIELDS)
            .first()
            if self.pk is not None
            else None
        )

        previous_sealed = bool(
            stored and self._fact_check_is_sealed(stored["fact_check_id"])
        )
        target_sealed = self._fact_check_is_sealed()

        if not previous_sealed and not target_sealed:
            return

        if stored is None:
            raise ValidationError(
                "Sources cannot be added to a sealed fact-check publication."
            )

        if any(
            getattr(self, field) != stored[field]
            for field in self.SEALED_CONTENT_FIELDS
        ):
            raise ValidationError(
                "Sealed fact-check publication sources cannot be modified."
            )

    def delete(self, *args, **kwargs):
        stored_fact_check_id = (
            OfficialFactCheckSource.objects.filter(pk=self.pk)
            .values_list("fact_check_id", flat=True)
            .first()
        )

        if stored_fact_check_id and self._fact_check_is_sealed(stored_fact_check_id):
            raise ValidationError(
                "Sealed fact-check publication sources cannot be deleted."
            )

        return super().delete(*args, **kwargs)

    def clean(self):
        super().clean()

        if (
            self.evidence_submission_id
            and self.fact_check.claim_id
            and (self.evidence_submission.thread.claim_id != self.fact_check.claim_id)
        ):
            raise ValidationError(
                {
                    "evidence_submission": "The evidence source "
                    "belongs to a different "
                    "claim."
                }
            )

    def save(self, *args, **kwargs):
        self._validate_sealed_write()
        return super().save(*args, **kwargs)


class OfficialFactCheckSourceEvidenceLink(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    source = models.ForeignKey(
        OfficialFactCheckSource,
        on_delete=models.CASCADE,
        related_name="evidence_links",
        editable=False,
    )
    snapshot = models.ForeignKey(
        AdjudicationDecisionEvidenceSnapshot,
        on_delete=models.PROTECT,
        related_name="source_links",
        editable=False,
    )
    captured_evidence_id = models.UUIDField(
        editable=False,
    )

    class Meta:
        ordering = ["source_id", "captured_evidence_id", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "captured_evidence_id"],
                name="unique_source_captured_evidence",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        source_fact_check = self.source.fact_check
        snapshot = self.snapshot
        if OfficialFactCheckPublicationSnapshot.objects.filter(
            fact_check_id=source_fact_check.id
        ).exists():
            errors["source"] = (
                "Evidence lineage cannot be added to a sealed publication."
            )
        if source_fact_check.adjudication_decision_id != snapshot.decision_id:
            errors["snapshot"] = (
                "Source and snapshot must belong to the same adjudication decision."
            )
        if str(source_fact_check.claim_id) != str(snapshot.claim_id):
            errors["snapshot"] = (
                "Snapshot claim identity must match the fact-check claim."
            )
        record = None
        try:
            evidence_records = validate_evidence_snapshot(
                schema_version=snapshot.schema_version,
                evidence_records=snapshot.evidence_records,
            )
        except EvidenceSnapshotSchemaError as error:
            errors["snapshot"] = str(error)
        else:
            record = next(
                (
                    item
                    for item in evidence_records
                    if item["id"] == str(self.captured_evidence_id)
                ),
                None,
            )
        if record is None:
            errors["captured_evidence_id"] = (
                "The captured evidence record is not present in the snapshot."
            )
        else:
            if record.get("evidence_status") != (
                EvidenceSubmission.EvidenceStatus.VERIFIED
            ):
                errors["captured_evidence_id"] = (
                    "Only captured VERIFIED evidence may be linked as a source."
                )
            captured_url = record.get("evidence_url")
            captured_url = captured_url.strip() if isinstance(captured_url, str) else ""
            source_url = (self.source.url or "").strip()
            validator = URLValidator(schemes=["http", "https"])
            try:
                if len(captured_url) > 2000:
                    raise ValidationError("The captured URL is too long.")
                validator(captured_url)
            except ValidationError:
                captured_url = ""
            if not captured_url or captured_url != source_url:
                errors["captured_evidence_id"] = (
                    "The captured evidence URL must match the source URL."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(
                "Evidence source lineage links are immutable and cannot be modified."
            )
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Evidence source lineage links cannot be deleted directly."
        )

    def __str__(self):
        return f"{self.source_id}: evidence {self.captured_evidence_id}"


def _publication_snapshot_timestamp(value):
    return value.isoformat() if value is not None else None


def _publication_snapshot_user(user):
    if user is None:
        return None
    return {
        "id": str(user.pk),
        "username": user.username,
    }


class OfficialFactCheckPublicationSnapshot(models.Model):
    CURRENT_SCHEMA_VERSION = PUBLICATION_SNAPSHOT_SCHEMA_VERSION

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    fact_check = models.OneToOneField(
        OfficialFactCheck,
        on_delete=models.PROTECT,
        related_name="publication_snapshot",
    )
    decision_snapshot = models.ForeignKey(
        AdjudicationDecisionEvidenceSnapshot,
        on_delete=models.PROTECT,
        related_name="publication_snapshots",
    )
    schema_version = models.PositiveSmallIntegerField(
        default=CURRENT_SCHEMA_VERSION,
        editable=False,
    )
    captured_at = models.DateTimeField(
        editable=False,
    )
    payload = models.JSONField(
        default=dict,
        editable=False,
    )

    class Meta:
        ordering = ["-captured_at", "id"]

    @classmethod
    def build_payload(cls, *, fact_check, decision_snapshot):
        if (
            fact_check.adjudication_decision_id != decision_snapshot.decision_id
            or str(fact_check.claim_id) != str(decision_snapshot.claim_id)
            or fact_check.organization_id is None
            or fact_check.published_at is None
        ):
            raise ValidationError(
                "The publication and decision evidence snapshot identities differ."
            )
        try:
            evidence_records = validate_evidence_snapshot(
                schema_version=decision_snapshot.schema_version,
                evidence_records=decision_snapshot.evidence_records,
            )
        except EvidenceSnapshotSchemaError as error:
            raise ValidationError(
                "The decision evidence snapshot is malformed."
            ) from error
        evidence_by_id = {record["id"]: record for record in evidence_records}

        source_queryset = (
            OfficialFactCheckSource.objects.filter(fact_check=fact_check)
            .select_related("added_by")
            .prefetch_related(
                Prefetch(
                    "evidence_links",
                    queryset=OfficialFactCheckSourceEvidenceLink.objects.order_by(
                        "captured_evidence_id",
                        "id",
                    ),
                )
            )
            .order_by("created_at", "id")
        )
        sources = []
        validator = URLValidator(schemes=["http", "https"])
        for source in source_queryset:
            lineage = []
            for link in source.evidence_links.all():
                record = evidence_by_id.get(str(link.captured_evidence_id))
                captured_url = record.get("evidence_url") if record else None
                captured_url = (
                    captured_url.strip() if isinstance(captured_url, str) else ""
                )
                try:
                    if len(captured_url) > 2000:
                        raise ValidationError("The captured URL is too long.")
                    validator(captured_url)
                except ValidationError:
                    captured_url = ""
                if (
                    link.snapshot_id != decision_snapshot.id
                    or record is None
                    or record["evidence_status"]
                    != EvidenceSubmission.EvidenceStatus.VERIFIED
                    or not captured_url
                    or captured_url != source.url
                ):
                    raise ValidationError(
                        "Publication source lineage is malformed or inconsistent."
                    )
                lineage.append(
                    {
                        "id": str(link.id),
                        "decision_evidence_snapshot_id": str(link.snapshot_id),
                        "captured_evidence_id": str(link.captured_evidence_id),
                    }
                )
            sources.append(
                {
                    "id": str(source.id),
                    "url": source.url,
                    "title": source.title,
                    "source_type": source.source_type,
                    "is_editorially_selected": source.is_editorially_selected,
                    "added_by": _publication_snapshot_user(source.added_by),
                    "created_at": _publication_snapshot_timestamp(source.created_at),
                    "legacy_evidence_submission_id": (
                        str(source.evidence_submission_id)
                        if source.evidence_submission_id is not None
                        else None
                    ),
                    "lineage": lineage,
                }
            )

        organization = fact_check.organization
        return {
            "claim_id": str(fact_check.claim_id),
            "fact_check_id": str(fact_check.id),
            "decision_id": str(fact_check.adjudication_decision_id),
            "decision_evidence_snapshot_id": str(decision_snapshot.id),
            "organization": {
                "id": str(organization.id),
                "name": organization.name,
                "slug": organization.slug,
            },
            "article_version": fact_check.version,
            "published_at": _publication_snapshot_timestamp(fact_check.published_at),
            "canonical_claim": fact_check.canonical_claim,
            "verdict": fact_check.verdict,
            "headline": fact_check.headline,
            "summary": fact_check.summary,
            "article_body": fact_check.article_body,
            "drafted_by": _publication_snapshot_user(fact_check.drafted_by),
            "drafted_at": _publication_snapshot_timestamp(fact_check.created_at),
            "submitted_for_review_at": _publication_snapshot_timestamp(
                fact_check.submitted_for_review_at
            ),
            "reviewed_by": _publication_snapshot_user(fact_check.reviewed_by),
            "reviewed_at": _publication_snapshot_timestamp(fact_check.reviewed_at),
            "published_by": _publication_snapshot_user(fact_check.published_by),
            "sources": sources,
        }

    def clean(self):
        super().clean()
        try:
            validate_publication_snapshot(
                schema_version=self.schema_version,
                payload=self.payload,
            )
        except PublicationSnapshotSchemaError as error:
            raise ValidationError({"payload": str(error)}) from error

        fact_check = self.fact_check
        if fact_check.publication_status != (
            OfficialFactCheck.PublicationStatus.PUBLISHED
        ):
            raise ValidationError(
                {"fact_check": "Only a published fact-check may be sealed."}
            )
        if fact_check.published_at != self.captured_at:
            raise ValidationError(
                {"captured_at": "The seal must use the publication timestamp."}
            )
        expected_payload = self.build_payload(
            fact_check=fact_check,
            decision_snapshot=self.decision_snapshot,
        )
        if self.payload != expected_payload:
            raise ValidationError(
                {"payload": "The sealed payload does not match publication state."}
            )

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(
                "Publication snapshots are immutable and cannot be modified."
            )
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Publication snapshots cannot be deleted directly.")

    def __str__(self):
        return f"Publication snapshot for fact-check {self.fact_check_id}"


class KnowledgeReuseEvent(models.Model):
    class ReuseType(models.TextChoices):
        USER_RESPONSE = (
            "USER_RESPONSE",
            "User-Facing Reuse",
        )

        VERIFICATION_CONTEXT = (
            "VERIFICATION_CONTEXT",
            "Verification Context Reuse",
        )

    class MatchMethod(models.TextChoices):
        EXACT_TEXT = (
            "EXACT_TEXT",
            "Exact Text Match",
        )

        SEMANTIC = (
            "SEMANTIC",
            "Semantic Match",
        )

        FULL_TEXT = (
            "FULL_TEXT",
            "Full-Text Match",
        )

        CLAIM_CACHE = (
            "CLAIM_CACHE",
            "Claim Cache Match",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    fact_check = models.ForeignKey(
        OfficialFactCheck,
        on_delete=models.PROTECT,
        related_name="reuse_events",
    )

    target_claim = models.ForeignKey(
        Claim,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knowledge_reuse_events",
    )

    triggered_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knowledge_reuse_events",
    )

    reuse_type = models.CharField(
        max_length=30,
        choices=ReuseType.choices,
        db_index=True,
    )

    match_method = models.CharField(
        max_length=30,
        choices=MatchMethod.choices,
        db_index=True,
    )

    similarity_score = models.FloatField(
        null=True,
        blank=True,
    )

    # We intentionally avoid storing the
    # user's raw search/claim text here.
    #
    # A normalized SHA-256 fingerprint gives
    # us future deduplication/analytics
    # capability without retaining another
    # copy of potentially sensitive text.
    query_fingerprint = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        db_index=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "-created_at",
        ]

        indexes = [
            models.Index(
                fields=[
                    "fact_check",
                    "reuse_type",
                    "-created_at",
                ],
                name="reuse_fact_type_time_idx",
            ),
            models.Index(
                fields=[
                    "target_claim",
                    "-created_at",
                ],
                name="reuse_target_time_idx",
            ),
            models.Index(
                fields=[
                    "match_method",
                    "-created_at",
                ],
                name="reuse_method_time_idx",
            ),
        ]

    def __str__(self):
        return f"{self.reuse_type} - " f"Fact Check {self.fact_check_id}"
