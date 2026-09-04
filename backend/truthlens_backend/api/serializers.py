from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    Claim,
    Thread,
    UserProfile,
    EvidenceSubmission,
    Vote,
    ThreadComment,
    ThreadFlag,
    AdjudicationDecision,
    ModerationCase,
    OfficialFactCheck,
    OfficialFactCheckSource,
    VerificationAssignment,
    OrganizationMembership,
    OrganizationInvitation,
)
from .services import validate_public_url, check_url_threat_reputation
from .trust_service import calculate_trust_components
from django.contrib.auth.password_validation import validate_password
import json, ast
from .organization_service import (
    get_workspace_access_context,
)


class PublicIdentityProfileSerializer(serializers.ModelSerializer):
    trust_score = serializers.FloatField(source="profile.trust_score", read_only=True)
    role = serializers.CharField(source="profile.role", read_only=True)
    organization_name = serializers.CharField(
        source="profile.organization_name", read_only=True
    )
    avatar_url = serializers.CharField(source="profile.avatar_url", read_only=True)
    bio = serializers.CharField(source="profile.bio", read_only=True)
    followers_count = serializers.SerializerMethodField()
    following_count = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()

    def get_followers_count(self, obj):
        return obj.profile.followers.count()

    def get_following_count(self, obj):
        return obj.following_profiles.count()

    def get_is_following(self, obj):
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            return obj.profile.followers.filter(id=request.user.id).exists()
        return False

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "trust_score",
            "role",
            "organization_name",
            "avatar_url",
            "bio",
            "date_joined",
            "followers_count",
            "following_count",
            "is_following",
        ]


class PublicUserThreadSerializer(serializers.ModelSerializer):
    claim_id = serializers.UUIDField(read_only=True)
    evidence_count = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()

    def get_evidence_count(self, obj):
        return obj.evidence_submissions.count()

    def get_comment_count(self, obj):
        return obj.comments.count()

    class Meta:
        model = Thread
        fields = [
            "id",
            "claim_id",
            "caption",
            "status",
            "escalation_reason",
            "created_at",
            "evidence_count",
            "comment_count",
        ]


class PublicThreadSummarySerializer(serializers.ModelSerializer):
    claim_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Thread
        fields = ["id", "claim_id", "caption", "status", "created_at"]


class PublicUserEvidenceSerializer(serializers.ModelSerializer):
    activity_type = serializers.CharField(default="EVIDENCE", read_only=True)
    activity_at = serializers.DateTimeField(source="submitted_at", read_only=True)
    thread = PublicThreadSummarySerializer(read_only=True)

    class Meta:
        model = EvidenceSubmission
        fields = [
            "id",
            "activity_type",
            "activity_at",
            "evidence_caption",
            "evidence_url",
            "evidence_type",
            "evidence_verdict",
            "evidence_status",
            "thread",
        ]


class PublicUserCommentSerializer(serializers.ModelSerializer):
    activity_type = serializers.CharField(default="COMMENT", read_only=True)
    activity_at = serializers.DateTimeField(source="commented_at", read_only=True)
    thread = PublicThreadSummarySerializer(read_only=True)

    class Meta:
        model = ThreadComment
        fields = [
            "id",
            "activity_type",
            "activity_at",
            "comment_text",
            "thread",
        ]


class PublicModeratorVerdictSerializer(serializers.ModelSerializer):
    thread_id = serializers.UUIDField(source="id", read_only=True)
    claim_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Thread
        fields = [
            "thread_id",
            "claim_id",
            "caption",
            "status",
            "moderator_verdict",
            "moderator_notes",
            "moderated_at",
        ]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
    )

    class Meta:
        model = User
        fields = ["username", "email", "password"]

    def validate_username(self, value):
        value = value.strip()

        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("This username is already taken.")

        return value

    def validate_email(self, value):
        value = value.strip().lower()

        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "An account with this email already exists."
            )

        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    trust_score = serializers.FloatField(source="profile.trust_score", read_only=True)
    is_email_verified = serializers.BooleanField(
        source="profile.is_email_verified", read_only=True
    )
    has_completed_onboarding = serializers.BooleanField(
        source="profile.has_completed_onboarding",
        read_only=True,
    )
    date_joined = serializers.DateTimeField(read_only=True)
    role = serializers.CharField(source="profile.role", read_only=True)
    organization_name = serializers.CharField(
        source="profile.organization_name", read_only=True
    )
    followers_count = serializers.SerializerMethodField()
    following_count = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()
    avatar_url = serializers.CharField(source="profile.avatar_url", read_only=True)
    bio = serializers.CharField(source="profile.bio", read_only=True)

    def get_followers_count(self, obj):
        return obj.profile.followers.count()

    def get_following_count(self, obj):
        # Counts how many profiles this specific user is following
        return obj.following_profiles.count()

    def get_is_following(self, obj):
        # Checks if the CURRENT logged-in user is in the target user's followers list
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.profile.followers.filter(id=request.user.id).exists()
        return False

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "trust_score",
            "is_email_verified",
            "has_completed_onboarding",
            "date_joined",
            "role",
            "organization_name",
            "followers_count",
            "following_count",
            "is_following",
            "avatar_url",
            "bio",
        ]


class PublicUserSearchSerializer(serializers.ModelSerializer):
    trust_score = serializers.FloatField(source="profile.trust_score", read_only=True)
    role = serializers.CharField(source="profile.role", read_only=True)
    organization_name = serializers.CharField(
        source="profile.organization_name", read_only=True
    )
    avatar_url = serializers.CharField(source="profile.avatar_url", read_only=True)
    bio = serializers.CharField(source="profile.bio", read_only=True)
    followers_count = serializers.SerializerMethodField()

    def get_followers_count(self, obj):
        return obj.profile.followers.count()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "trust_score",
            "role",
            "organization_name",
            "avatar_url",
            "bio",
            "followers_count",
        ]


class UserWithTrustBreakdownSerializer(UserSerializer):
    trust_breakdown = serializers.SerializerMethodField()

    def get_trust_breakdown(self, obj):
        return calculate_trust_components(obj)

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ["trust_breakdown"]


class CurrentUserSerializer(UserWithTrustBreakdownSerializer):
    workspace = serializers.SerializerMethodField()

    def get_workspace(self, obj):
        return get_workspace_access_context(obj)

    class Meta(UserWithTrustBreakdownSerializer.Meta):
        fields = UserWithTrustBreakdownSerializer.Meta.fields + ["workspace"]


class UserProfileSerializer(serializers.ModelSerializer):
    trust_score = serializers.FloatField(read_only=True)
    role = serializers.CharField(read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            "id",
            "user",
            "trust_score",
            "bio",
            "is_email_verified",
            "role",
            "organization_name",
        ]
        read_only_fields = ["id", "user", "trust_score", "is_email_verified", "role"]


class ClaimSerializer(serializers.ModelSerializer):
    effective_verdict = serializers.SerializerMethodField()
    has_moderator_verdict = serializers.SerializerMethodField()
    verified_evidence_count = serializers.SerializerMethodField()
    moderator_verdict_info = serializers.SerializerMethodField()
    canonical_source_url = serializers.SerializerMethodField()
    activity_at = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()

    def get_is_saved(self, obj):
        saved_claim_ids = self.context.get("saved_claim_ids")

        if saved_claim_ids is not None:
            return obj.id in saved_claim_ids

        request = self.context.get("request")

        if request and request.user and request.user.is_authenticated:
            return request.user.profile.saved_claims.filter(id=obj.id).exists()

        return False

    def get_activity_at(self, obj):
        activity_at = getattr(
            obj,
            "activity_at",
            None,
        )

        return activity_at or obj.last_updated

    def get_canonical_source_url(self, obj):
        def extract_url(value):
            if not value:
                return None

            if isinstance(value, dict):
                url = value.get("url")
                if isinstance(url, str) and url.startswith(("http://", "https://")):
                    return url
                return None

            if not isinstance(value, str):
                return None

            value = value.strip()

            # Normal URL
            if value.startswith(("http://", "https://")):
                return value

            # Legacy serialized dictionary
            if value.startswith("{"):
                parsed = None

                # Newer/JSON-style records
                try:
                    parsed = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    pass

                # Older Python-dict-style records:
                # {'url': 'https://...', 'title': '...'}
                if parsed is None:
                    try:
                        parsed = ast.literal_eval(value)
                    except (ValueError, SyntaxError):
                        pass

                if isinstance(parsed, dict):
                    url = parsed.get("url")

                    if isinstance(url, str) and url.startswith(("http://", "https://")):
                        return url

            return None

        if obj.claim_type == Claim.ClaimType.URL:
            url = extract_url(obj.url_link)
            if url:
                return url

        url = extract_url(obj.source_link)
        if url:
            return url

        url = extract_url(obj.top_verdict_source)
        if url:
            return url

        if obj.ai_sources:
            for source in obj.ai_sources:
                url = extract_url(source)
                if url:
                    return url

        return None

    def get_effective_verdict(self, obj):
        return obj.final_verdict or obj.ai_verdict

    def get_has_moderator_verdict(self, obj):
        """Check if moderators have set a final verdict on this claim"""
        # Direct check: final_verdict is only set when moderators have verified evidence
        return bool(obj.final_verdict)

    def get_verified_evidence_count(self, obj):
        """Get count of verified evidence for this claim"""
        from .models import EvidenceSubmission

        return EvidenceSubmission.objects.filter(
            thread__claim=obj, evidence_status="VERIFIED"
        ).count()

    def get_moderator_verdict_info(self, obj):
        """Return moderator verdict status and supporting evidence"""
        if obj.final_verdict:
            return {
                "verdict": obj.final_verdict,
                "source": "MODERATORS",
                "verified_evidence_count": self.get_verified_evidence_count(obj),
            }
        return None

    class Meta:
        model = Claim
        fields = [
            "id",
            "claim_type",
            "context_text",
            "ai_verdict",
            "final_verdict",
            "effective_verdict",
            "ai_summary",
            "source_type",
            "consensus_score",
            "verified_via",
            "url_link",
            "source_link",
            "media_url",
            "has_moderator_verdict",
            "verified_evidence_count",
            "moderator_verdict_info",
            "activity_at",
            "last_updated",
            "score_context",
            "top_verdict_source",
            "is_ai_generated",
            "canonical_source_url",
            "is_saved",
        ]


class ClaimDeepAnalysisSerializer(ClaimSerializer):
    class Meta(ClaimSerializer.Meta):
        fields = ClaimSerializer.Meta.fields + [
            "ai_reasoning",
            "ai_sources",
            "context_text",
            "url_link",
            "claim_fingerprint",
        ]


class VerificationIntakeClaimSerializer(serializers.ModelSerializer):
    """
    Lightweight claim representation for the
    professional verification workspace.

    Keep this intentionally smaller than ClaimSerializer
    because intake/workload endpoints may return many
    assignments at once.
    """

    community_threads = PublicThreadSummarySerializer(
        source="threads",
        many=True,
        read_only=True,
    )

    class Meta:
        model = Claim

        fields = [
            "id",
            "claim_type",
            "context_text",
            "ai_verdict",
            "final_verdict",
            "ai_summary",
            "consensus_score",
            "source_type",
            "url_link",
            "source_link",
            "media_url",
            "last_updated",
            "community_threads",
        ]

        read_only_fields = fields


class VerificationAssignmentUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User

        fields = [
            "id",
            "username",
        ]

        read_only_fields = fields


class OrganizationAdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User

        fields = [
            "id",
            "username",
            "email",
        ]

        read_only_fields = fields


class OrganizationInvitationActorSerializer(serializers.ModelSerializer):
    class Meta:
        model = User

        fields = [
            "id",
            "username",
        ]

        read_only_fields = fields


class OrganizationInvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()

    invited_role = serializers.ChoiceField(
        choices=(OrganizationMembership.Role.choices),
    )


class OrganizationInvitationAdminSerializer(serializers.ModelSerializer):
    organization = serializers.SerializerMethodField()

    invited_by = OrganizationInvitationActorSerializer(
        read_only=True,
    )

    accepted_by = OrganizationInvitationActorSerializer(
        read_only=True,
    )

    cancelled_by = OrganizationInvitationActorSerializer(
        read_only=True,
    )

    def get_organization(
        self,
        obj,
    ):
        return {
            "id": str(obj.organization.id),
            "name": obj.organization.name,
            "slug": obj.organization.slug,
        }

    class Meta:
        model = OrganizationInvitation

        fields = [
            "id",
            "organization",
            "email",
            "invited_role",
            "status",
            "invited_by",
            "expires_at",
            "last_sent_at",
            "send_count",
            "accepted_by",
            "accepted_at",
            "cancelled_by",
            "cancelled_at",
            "created_at",
            "updated_at",
        ]

        read_only_fields = fields


class OrganizationInvitationPublicSerializer(serializers.ModelSerializer):
    organization = serializers.SerializerMethodField()

    invited_by = OrganizationInvitationActorSerializer(
        read_only=True,
    )

    invited_role_label = serializers.CharField(
        source="get_invited_role_display",
        read_only=True,
    )

    def get_organization(
        self,
        obj,
    ):
        return {
            "id": str(obj.organization.id),
            "name": obj.organization.name,
            "slug": obj.organization.slug,
            "logo_url": obj.organization.logo_url,
        }

    class Meta:
        model = OrganizationInvitation

        fields = [
            "organization",
            "invited_role",
            "invited_role_label",
            "status",
            "expires_at",
            "invited_by",
        ]

        read_only_fields = fields


class OrganizationMembershipAdminSerializer(serializers.ModelSerializer):
    user = OrganizationAdminUserSerializer(
        read_only=True,
    )

    approved_by = serializers.SerializerMethodField()

    def get_approved_by(
        self,
        obj,
    ):
        if not obj.approved_by:
            return None

        return {
            "id": obj.approved_by.id,
            "username": obj.approved_by.username,
        }

    class Meta:
        model = OrganizationMembership

        fields = [
            "id",
            "user",
            "role",
            "status",
            "joined_at",
            "approved_at",
            "approved_by",
        ]

        read_only_fields = fields


class VerificationAssignmentSerializer(serializers.ModelSerializer):
    claim = VerificationIntakeClaimSerializer(read_only=True)

    claimed_by = VerificationAssignmentUserSerializer(read_only=True)

    organization = serializers.SerializerMethodField()

    def get_organization(
        self,
        obj,
    ):
        if not obj.organization:
            return None

        return {
            "id": str(obj.organization.id),
            "name": obj.organization.name,
            "slug": obj.organization.slug,
        }

    class Meta:
        model = VerificationAssignment

        fields = [
            "id",
            "claim",
            "organization",
            "claimed_by",
            "status",
            "claimed_at",
            "released_at",
            "completed_at",
            "created_at",
            "updated_at",
        ]

        read_only_fields = fields


class VerificationAssignmentClaimSerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()


class ThreadSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    claim = ClaimSerializer(read_only=True)
    claim_id = serializers.UUIDField(write_only=True)
    evidence_count = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    flag_count = serializers.SerializerMethodField()
    recent_flag_reason = serializers.SerializerMethodField()

    def get_recent_flag_reason(self, obj):
        latest_flag = (
            obj.flags.filter(resolved_at__isnull=True).order_by("-flagged_at").first()
        )

        return latest_flag.reason if latest_flag else None

    def get_flag_count(self, obj):
        return obj.flags.filter(resolved_at__isnull=True).count()

    def get_evidence_count(self, obj):
        return obj.evidence_submissions.count()

    def get_comment_count(self, obj):
        return obj.comments.count()

    def validate(self, attrs):
        if self.instance and "claim_id" in attrs:
            raise serializers.ValidationError(
                {"claim_id": "Cannot be changed after thread creation."}
            )
        if self.instance and "escalation_reason" in attrs:
            raise serializers.ValidationError(
                {"escalation_reason": "Cannot be changed after thread creation."}
            )
        return attrs

    class Meta:
        model = Thread
        fields = [
            "id",
            "display_id",
            "claim",
            "claim_id",
            "author",
            "caption",
            "status",
            "recent_flag_reason",
            "escalation_reason",
            "moderator_verdict",
            "moderator_notes",
            "moderated_at",
            "created_at",
            "evidence_count",
            "comment_count",
            "flag_count",
        ]
        read_only_fields = [
            "id",
            "display_id",
            "claim",
            "author",
            "status",
            # "flag_reason",
            "moderator_verdict",
            "moderator_notes",
            "moderated_at",
            "created_at",
            "evidence_count",
            "comment_count",
            "flag_count",
        ]


class ThreadFlagSerializer(serializers.ModelSerializer):
    flagged_by = UserSerializer(read_only=True)
    thread = ThreadSerializer(read_only=True)
    thread_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = ThreadFlag
        fields = [
            "id",
            "thread_id",
            "flagged_by",
            "thread",
            "reason",
            "notes",
            "flagged_at",
        ]
        read_only_fields = ["id", "flagged_by", "thread"]


class ThreadCommentSerializer(serializers.ModelSerializer):
    commenter = UserSerializer(read_only=True)
    thread_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = ThreadComment
        fields = [
            "id",
            "thread_id",
            "commenter",
            "comment_text",
            "commented_at",
        ]
        read_only_fields = ["id", "commenter", "commented_at"]

    def validate(self, attrs):
        if self.instance and "thread_id" in attrs:
            raise serializers.ValidationError(
                {"thread_id": "Cannot be changed after comment creation."}
            )
        return attrs


class EvidenceSubmissionSerializer(serializers.ModelSerializer):
    contributor = UserSerializer(read_only=True)
    verified_by = UserSerializer(read_only=True)  # Serialize moderator who verified it
    thread_id = serializers.UUIDField(write_only=True)
    # Include full thread and claim for moderation context
    thread = serializers.SerializerMethodField(read_only=True)
    upvotes = serializers.SerializerMethodField(read_only=True)
    downvotes = serializers.SerializerMethodField(read_only=True)
    my_vote = serializers.SerializerMethodField(read_only=True)
    weighted_score = serializers.SerializerMethodField(read_only=True)

    def get_thread(self, obj):
        """Return full thread with nested claim for moderation queue display."""
        if obj.thread:
            return {
                "id": str(obj.thread.id),
                "caption": obj.thread.caption,
                "status": obj.thread.status,
                "created_at": obj.thread.created_at,
                "claim": (
                    {
                        "id": str(obj.thread.claim.id),
                        "context_text": obj.thread.claim.context_text,
                        "verdict": obj.thread.claim.final_verdict
                        or obj.thread.claim.ai_verdict,
                    }
                    if obj.thread.claim
                    else None
                ),
            }
        return None

    def get_upvotes(self, obj):
        prefetched = getattr(obj, "_prefetched_objects_cache", {}).get("votes")
        if prefetched is not None:
            return sum(1 for vote in prefetched if vote.vote_value is True)
        return obj.votes.filter(vote_value=True).count()

    def get_downvotes(self, obj):
        prefetched = getattr(obj, "_prefetched_objects_cache", {}).get("votes")
        if prefetched is not None:
            return sum(1 for vote in prefetched if vote.vote_value is False)
        return obj.votes.filter(vote_value=False).count()

    def get_my_vote(self, obj):
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            return None

        prefetched = getattr(obj, "_prefetched_objects_cache", {}).get("votes")
        if prefetched is not None:
            vote = next(
                (entry for entry in prefetched if entry.voter_id == request.user.id),
                None,
            )
        else:
            vote = obj.votes.filter(voter=request.user).first()
        if not vote:
            return None

        return {
            "id": str(vote.id),
            "vote_value": vote.vote_value,
        }

    def get_weighted_score(self, obj):
        upvotes = self.get_upvotes(obj)
        downvotes = self.get_downvotes(obj)
        contributor_trust = (
            obj.contributor.profile.trust_score
            if hasattr(obj.contributor, "profile")
            else 0
        )
        return round((upvotes * (contributor_trust / 100)) - (downvotes * 0.5), 2)

    def validate_evidence_url(self, value):
        if value in (None, ""):
            return value

        safe_url, url_error = validate_public_url(value)
        if url_error:
            raise serializers.ValidationError(url_error)

        url_safety = check_url_threat_reputation(safe_url)
        if url_safety.get("status") == "UNSAFE":
            raise serializers.ValidationError(
                "This evidence URL is flagged as unsafe and cannot be submitted."
            )

        return safe_url

    class Meta:
        model = EvidenceSubmission
        fields = [
            "id",
            "thread_id",
            "thread",
            "contributor",
            "evidence_caption",
            "evidence_url",
            "evidence_type",
            "evidence_verdict",
            "evidence_status",
            "contributor_trust_snapshot",
            "submitted_at",
            "verified_by",
            "verified_at",
            "moderator_notes",
            "upvotes",
            "downvotes",
            "my_vote",
            "weighted_score",
            "rejection_reason",
        ]
        read_only_fields = [
            "id",
            "contributor",
            "contributor_trust_snapshot",
            "submitted_at",
            "verified_by",
            "verified_at",
            "moderator_notes",
            "thread",
            "evidence_status",
            "rejection_reason",
        ]

    def validate(self, attrs):
        if self.instance and "thread_id" in attrs:
            raise serializers.ValidationError(
                {"thread_id": "Cannot be changed after evidence creation."}
            )
        return attrs


class ThreadDetailSerializer(serializers.ModelSerializer):
    author = UserWithTrustBreakdownSerializer(read_only=True)
    claim = ClaimSerializer(read_only=True)
    evidence_submissions = EvidenceSubmissionSerializer(many=True, read_only=True)
    comments = ThreadCommentSerializer(many=True, read_only=True)
    moderated_by = UserSerializer(read_only=True)

    claim_id = serializers.UUIDField(write_only=True)
    evidence_count = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    flag_count = serializers.SerializerMethodField()

    def get_evidence_count(self, obj):
        return obj.evidence_submissions.count()

    def get_comment_count(self, obj):
        return obj.comments.count()

    def get_flag_count(self, obj):
        return obj.flags.count()

    class Meta:
        model = Thread
        fields = [
            "id",
            "display_id",
            "claim",
            "claim_id",
            "author",
            "caption",
            "status",
            # "flag_reason",
            "escalation_reason",
            "moderator_verdict",
            "moderator_notes",
            "moderated_by",
            "moderated_at",
            "created_at",
            "evidence_submissions",
            "comments",
            "evidence_count",
            "comment_count",
            "flag_count",
        ]


class ModerationDecisionSerializer(serializers.Serializer):
    moderator_verdict = serializers.ChoiceField(
        choices=(AdjudicationDecision.Verdict.choices)
    )

    moderator_notes = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
    )

    canonical_claim = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
    )

    expected_revision = serializers.IntegerField(
        required=False,
        min_value=0,
    )

    verification_run_id = serializers.UUIDField(
        required=False,
        allow_null=True,
    )

    # Temporary compatibility with the
    # existing moderation frontend.
    #
    # Adjudication no longer owns Thread.status.
    status = serializers.ChoiceField(
        choices=[
            Thread.Status.CLOSED,
        ],
        required=False,
        write_only=True,
    )


class AdjudicationDecisionSerializer(serializers.ModelSerializer):
    decided_by = UserSerializer(read_only=True)

    ai_agrees = serializers.BooleanField(read_only=True)

    organization = serializers.SerializerMethodField()

    moderation_case_id = serializers.SerializerMethodField()

    def get_organization(self, obj):
        if not obj.organization:
            return None

        return {
            "id": str(obj.organization.id),
            "name": obj.organization.name,
            "slug": obj.organization.slug,
        }

    def get_moderation_case_id(
        self,
        obj,
    ):
        return str(obj.moderation_case_id) if obj.moderation_case_id else None

    class Meta:
        model = AdjudicationDecision

        fields = [
            "id",
            "claim",
            "moderation_case_id",
            "verdict",
            "canonical_claim",
            "rationale",
            "decided_by",
            "organization",
            "verification_run",
            "ai_verdict_snapshot",
            "ai_confidence_snapshot",
            "ai_summary_snapshot",
            "ai_pipeline_version_snapshot",
            "ai_agrees",
            "revision_number",
            "supersedes",
            "is_current",
            "decided_at",
        ]

        read_only_fields = fields


class AdjudicationQueueCaseSerializer(serializers.ModelSerializer):
    claim = ClaimSerializer(read_only=True)

    assigned_to = UserSerializer(read_only=True)

    organization = serializers.SerializerMethodField()

    total_evidence = serializers.IntegerField(read_only=True)

    verified_evidence = serializers.IntegerField(read_only=True)

    rejected_evidence = serializers.IntegerField(read_only=True)

    def get_organization(
        self,
        obj,
    ):
        if not obj.organization:
            return None

        return {
            "id": str(obj.organization.id),
            "name": obj.organization.name,
            "slug": obj.organization.slug,
        }

    class Meta:
        model = ModerationCase

        fields = [
            "id",
            "claim",
            "status",
            "priority",
            "source",
            "organization",
            "assigned_to",
            "total_evidence",
            "verified_evidence",
            "rejected_evidence",
            "created_at",
            "updated_at",
        ]

        read_only_fields = fields


class FactCheckInputProtectionMixin:
    protected_fields = {
        "claim",
        "canonical_claim",
        "verdict",
        "adjudication_decision",
        "organization",
        "publication_status",
        "version",
        "drafted_by",
        "reviewed_by",
        "published_by",
        "published_at",
        "archived_at",
    }

    def validate(self, attrs):
        supplied_protected_fields = self.protected_fields.intersection(
            self.initial_data.keys()
        )

        if supplied_protected_fields:
            raise serializers.ValidationError(
                {
                    field: ("This field is " "read-only.")
                    for field in sorted(supplied_protected_fields)
                }
            )

        return attrs


class FactCheckDraftCreateSerializer(
    FactCheckInputProtectionMixin,
    serializers.Serializer,
):
    headline = serializers.CharField(
        max_length=300,
        allow_blank=False,
        trim_whitespace=True,
    )

    summary = serializers.CharField(
        allow_blank=False,
        trim_whitespace=True,
    )

    article_body = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        default="",
    )

    source_urls = serializers.ListField(
        child=serializers.URLField(
            max_length=2000,
        ),
        required=False,
        allow_empty=True,
        default=list,
    )

    expected_revision = serializers.IntegerField(
        required=False,
        min_value=1,
    )


class FactCheckDraftUpdateSerializer(
    FactCheckInputProtectionMixin,
    serializers.Serializer,
):
    headline = serializers.CharField(
        max_length=300,
        required=False,
        allow_blank=False,
        trim_whitespace=True,
    )

    summary = serializers.CharField(
        required=False,
        allow_blank=False,
        trim_whitespace=True,
    )

    article_body = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )

    source_urls = serializers.ListField(
        child=serializers.URLField(
            max_length=2000,
        ),
        required=False,
        allow_empty=True,
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)

        if not attrs:
            raise serializers.ValidationError(
                "At least one editable field " "must be provided."
            )

        return attrs


class OfficialFactCheckSourceSerializer(serializers.ModelSerializer):
    added_by = UserSerializer(read_only=True)

    evidence_submission_id = serializers.SerializerMethodField()

    def get_evidence_submission_id(
        self,
        obj,
    ):
        if not obj.evidence_submission_id:
            return None

        return str(obj.evidence_submission_id)

    class Meta:
        model = OfficialFactCheckSource

        fields = [
            "id",
            "url",
            "title",
            "source_type",
            "evidence_submission_id",
            "added_by",
            "created_at",
        ]

        read_only_fields = fields


class OfficialFactCheckSerializer(serializers.ModelSerializer):
    organization = serializers.SerializerMethodField()

    claim_id = serializers.SerializerMethodField()

    adjudication_decision_id = serializers.SerializerMethodField()

    source_thread_id = serializers.SerializerMethodField()

    drafted_by = UserSerializer(read_only=True)

    reviewed_by = UserSerializer(read_only=True)

    published_by = UserSerializer(read_only=True)

    source_items = OfficialFactCheckSourceSerializer(
        many=True,
        read_only=True,
    )

    def get_claim_id(
        self,
        obj,
    ):
        return str(obj.claim_id) if obj.claim_id else None

    def get_adjudication_decision_id(
        self,
        obj,
    ):
        return (
            str(obj.adjudication_decision_id) if obj.adjudication_decision_id else None
        )

    def get_source_thread_id(
        self,
        obj,
    ):
        return str(obj.source_thread_id) if obj.source_thread_id else None

    def get_organization(
        self,
        obj,
    ):
        if not obj.organization:
            return None

        return {
            "id": str(obj.organization.id),
            "name": (obj.organization.name),
            "slug": (obj.organization.slug),
        }

    class Meta:
        model = OfficialFactCheck

        fields = [
            "id",
            "claim_id",
            "adjudication_decision_id",
            "organization",
            "canonical_claim",
            "verdict",
            "headline",
            "summary",
            "article_body",
            "publication_status",
            "version",
            "sources",
            "source_items",
            "drafted_by",
            "submitted_for_review_at",
            "reviewed_by",
            "reviewed_at",
            "published_by",
            "published_at",
            "archived_at",
            "source_thread_id",
            "created_at",
            "updated_at",
        ]

        read_only_fields = fields


class VoteSerializer(serializers.ModelSerializer):
    voter = UserSerializer(read_only=True)

    class Meta:
        model = Vote
        fields = [
            "id",
            "evidence",
            "voter",
            "vote_value",
            "vote_trust_snapshot",
            "voted_at",
        ]
        read_only_fields = ["id", "voter", "vote_trust_snapshot", "voted_at"]

    def validate(self, attrs):
        if self.instance and "evidence" in attrs:
            raise serializers.ValidationError(
                {"evidence": "Cannot be changed after vote creation."}
            )
        return attrs


class ClaimMatchSerializer(serializers.Serializer):
    """Serializer for claim match/deduplication responses."""

    match_type = serializers.ChoiceField(
        choices=[
            "resolved",
            "has_thread",
            "has_verdict",
            "no_verdict",
        ],
        help_text=(
            "Claim-cache state: authoritative "
            "resolution, active community "
            "thread, AI-only result, or no "
            "verdict."
        ),
    )
    claim_id = serializers.CharField()
    claim_type = serializers.CharField()
    verdict = serializers.CharField(allow_null=True)
    ai_verdict = serializers.CharField(allow_null=True)
    final_verdict = serializers.CharField(allow_null=True)
    summary = serializers.CharField(allow_null=True)
    confidence_score = serializers.FloatField(allow_null=True)
    source_type = serializers.CharField(allow_null=True)
    source_url = serializers.CharField(allow_null=True)
    is_ai_generated = serializers.BooleanField()
    thread_id = serializers.CharField(allow_null=True)
    thread_status = serializers.CharField(allow_null=True)
    moderator_notes = serializers.CharField(allow_null=True)
    score_context = serializers.CharField(allow_null=True, required=False)
    sources = serializers.JSONField(
        required=False,
    )

    resolution_source = serializers.ChoiceField(
        choices=[
            "OFFICIAL_FACT_CHECK",
            "ADJUDICATION",
            "COMMUNITY_THREAD",
            "AI",
        ],
        required=False,
        allow_null=True,
    )

    official_fact_check = serializers.JSONField(
        required=False,
        allow_null=True,
    )
