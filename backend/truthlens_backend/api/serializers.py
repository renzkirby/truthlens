from rest_framework import serializers
from django.contrib.auth.models import User
from django.core.validators import URLValidator
from .models import (
    Claim,
    Thread,
    UserProfile,
    EvidenceSubmission,
    Vote,
    ThreadComment,
    ThreadFlag,
    ModerationEvent,
    AdjudicationDecision,
    ModerationCase,
    OfficialFactCheck,
    OfficialFactCheckSource,
    VerificationAssignment,
    Organization,
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
from .organization_public_presence_service import (
    is_public_partner_eligible,
)
from .moderation_service import ACTIVE_CASE_STATUSES
from .adjudication_provenance import (
    AdjudicationProvenance,
    get_claim_adjudication_provenance,
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
    final_verdict = serializers.SerializerMethodField()
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

    def _get_adjudication_provenance(self, obj):
        cache = getattr(self, "_adjudication_provenance_cache", None)

        if cache is None:
            cache = {}
            self._adjudication_provenance_cache = cache

        if obj.pk not in cache:
            cache[obj.pk] = get_claim_adjudication_provenance(obj)

        return cache[obj.pk]

    def get_final_verdict(self, obj):
        return self._get_adjudication_provenance(obj)["verdict"]

    def get_effective_verdict(self, obj):
        return self.get_final_verdict(obj) or obj.ai_verdict

    def get_has_moderator_verdict(self, obj):
        """Return whether the current verdict has attributable human provenance."""
        return self._get_adjudication_provenance(obj)["is_attributable"]

    def get_verified_evidence_count(self, obj):
        """Get count of verified evidence for this claim"""
        from .models import EvidenceSubmission

        return EvidenceSubmission.objects.filter(
            thread__claim=obj, evidence_status="VERIFIED"
        ).count()

    def get_moderator_verdict_info(self, obj):
        """Return only a verdict backed by attributable adjudication provenance."""
        provenance = self._get_adjudication_provenance(obj)

        if provenance["is_attributable"]:
            return {
                "verdict": provenance["verdict"],
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
    final_verdict = serializers.SerializerMethodField()

    def get_final_verdict(self, obj):
        return get_claim_adjudication_provenance(obj)["verdict"]

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


class PublicPartnerDirectoryQuerySerializer(serializers.Serializer):
    search = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )

    type = serializers.ChoiceField(
        choices=Organization.OrganizationType.choices,
        required=False,
        allow_blank=True,
    )


class PublicPartnerSummarySerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()

    organization_type_label = serializers.CharField(
        source="get_organization_type_display",
        read_only=True,
    )

    def get_logo_url(
        self,
        obj,
    ):
        if not obj.public_logo_enabled:
            return None

        return obj.logo_url

    class Meta:
        model = Organization

        fields = [
            "id",
            "name",
            "slug",
            "description",
            "website",
            "logo_url",
            "organization_type",
            "organization_type_label",
            "expertise_areas",
        ]

        read_only_fields = fields


class PublicPartnerDetailSerializer(PublicPartnerSummarySerializer):
    pass


class StrictBooleanField(serializers.BooleanField):
    def to_internal_value(
        self,
        data,
    ):
        if type(data) is not bool:
            self.fail("invalid", input=data)

        return data


class StrictCharField(serializers.CharField):
    def to_internal_value(
        self,
        data,
    ):
        if not isinstance(data, str):
            self.fail("invalid")

        return super().to_internal_value(data)


class OrganizationPublicProfileUpdateSerializer(serializers.Serializer):
    description = StrictCharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )

    website = serializers.URLField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=2000,
        validators=[
            URLValidator(
                schemes=[
                    "http",
                    "https",
                ]
            ),
        ],
    )

    expertise_areas = serializers.ListField(
        required=False,
        max_length=20,
        child=StrictCharField(
            allow_blank=False,
            max_length=100,
            trim_whitespace=True,
        ),
    )

    public_profile_enabled = StrictBooleanField(
        required=False,
    )

    public_logo_enabled = StrictBooleanField(
        required=False,
    )

    def to_internal_value(
        self,
        data,
    ):
        if hasattr(data, "keys"):
            unsupported_fields = set(data.keys()) - set(self.fields)

            if unsupported_fields:
                field_list = ", ".join(sorted(unsupported_fields))

                raise serializers.ValidationError(
                    {
                        "detail": f"Unsupported public-profile fields: {field_list}."
                    }
                )

        return super().to_internal_value(data)

    def validate_website(
        self,
        value,
    ):
        return value or None

    def validate_expertise_areas(
        self,
        values,
    ):
        normalized_values = []
        seen_values = set()

        for value in values:
            comparison_value = value.casefold()

            if comparison_value in seen_values:
                continue

            seen_values.add(comparison_value)
            normalized_values.append(value)

        return normalized_values


class OrganizationPublicProfileAdminSerializer(serializers.ModelSerializer):
    organization_type_label = serializers.CharField(
        source="get_organization_type_display",
        read_only=True,
    )

    publicly_visible = serializers.SerializerMethodField()

    def get_publicly_visible(
        self,
        obj,
    ):
        return is_public_partner_eligible(obj)

    class Meta:
        model = Organization

        fields = [
            "id",
            "name",
            "slug",
            "organization_type",
            "organization_type_label",
            "verification_status",
            "partner_status",
            "description",
            "website",
            "logo_url",
            "expertise_areas",
            "public_profile_enabled",
            "public_logo_enabled",
            "publicly_visible",
        ]

        read_only_fields = fields


class OrganizationLogoUploadSerializer(serializers.Serializer):
    logo = serializers.FileField()


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
            "logo_url": (
                obj.organization.logo_url
                if obj.organization.public_logo_enabled
                else None
            ),
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


class OrganizationMembershipRoleUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=[
            (
                OrganizationMembership.Role.ADMIN,
                "Administrator",
            ),
            (
                OrganizationMembership.Role.LEAD_VERIFIER,
                "Lead Verifier",
            ),
            (
                OrganizationMembership.Role.MODERATOR,
                "Moderator",
            ),
            (
                OrganizationMembership.Role.RESEARCHER,
                "Researcher",
            ),
            (
                OrganizationMembership.Role.CONTRIBUTOR,
                "Contributor",
            ),
        ],
    )


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


class SafetyCaseQueueFilterSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[
            ModerationCase.Status.OPEN,
            ModerationCase.Status.IN_REVIEW,
            ModerationCase.Status.ESCALATED,
            ModerationCase.Status.REOPENED,
        ],
        required=False,
        allow_blank=True,
    )
    priority = serializers.ChoiceField(
        choices=ModerationCase.Priority.choices,
        required=False,
        allow_blank=True,
    )
    assigned = serializers.ChoiceField(
        choices=["me", "unassigned"],
        required=False,
        allow_blank=True,
    )


class SafetyCaseActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=["DISMISS", "REMOVE", "ESCALATE"],
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        max_length=2000,
        default="",
    )

    def validate(self, attrs):
        unsupported_fields = set(self.initial_data) - {"action", "notes"}
        if unsupported_fields:
            raise serializers.ValidationError(
                {
                    field: "This field is not supported."
                    for field in sorted(unsupported_fields)
                }
            )

        if attrs["action"] in {"REMOVE", "ESCALATE"} and not attrs["notes"]:
            raise serializers.ValidationError(
                {
                    "notes": (
                        "Notes are required when removing content or "
                        "escalating a Safety case."
                    )
                }
            )

        return attrs


class SafetyUserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username"]
        read_only_fields = fields


class SafetyClaimSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Claim
        fields = ["id", "claim_type", "context_text"]
        read_only_fields = fields


class SafetyThreadSummarySerializer(serializers.ModelSerializer):
    author = SafetyUserSummarySerializer(read_only=True)
    claim = SafetyClaimSummarySerializer(read_only=True)

    class Meta:
        model = Thread
        fields = ["id", "caption", "created_at", "claim", "author"]
        read_only_fields = fields


class SafetyReportDetailSerializer(serializers.ModelSerializer):
    reason_label = serializers.CharField(
        source="get_reason_display",
        read_only=True,
    )

    class Meta:
        model = ThreadFlag
        fields = ["id", "reason", "reason_label", "notes", "flagged_at"]
        read_only_fields = fields


class SafetyModerationEventSerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()

    def get_actor(self, obj):
        if (
            obj.event_type == ModerationEvent.EventType.CASE_CREATED
            and obj.case.source == ModerationCase.Source.USER_REPORT
        ):
            return None

        if not obj.actor:
            return None

        return SafetyUserSummarySerializer(obj.actor).data

    class Meta:
        model = ModerationEvent
        fields = [
            "event_type",
            "actor",
            "from_status",
            "to_status",
            "reason_code",
            "notes",
            "created_at",
        ]
        read_only_fields = fields


class SafetyCaseSummarySerializer(serializers.ModelSerializer):
    assigned_to = SafetyUserSummarySerializer(read_only=True)
    thread = SafetyThreadSummarySerializer(read_only=True)
    report_count = serializers.SerializerMethodField()
    report_reason_summary = serializers.SerializerMethodField()

    @staticmethod
    def _reports(obj):
        if obj.status in ACTIVE_CASE_STATUSES:
            if not obj.thread:
                return []
            return getattr(obj.thread, "unresolved_safety_reports", [])

        return getattr(obj, "case_linked_safety_reports", [])

    def get_report_count(self, obj):
        return len(self._reports(obj))

    def get_report_reason_summary(self, obj):
        from .safety_review_service import summarize_report_reasons

        return summarize_report_reasons(self._reports(obj))

    class Meta:
        model = ModerationCase
        fields = [
            "id",
            "status",
            "priority",
            "source",
            "created_at",
            "updated_at",
            "assigned_at",
            "assigned_to",
            "report_count",
            "report_reason_summary",
            "thread",
        ]
        read_only_fields = fields


class SafetyCaseDetailSerializer(SafetyCaseSummarySerializer):
    reports = serializers.SerializerMethodField()
    events = serializers.SerializerMethodField()

    def get_reports(self, obj):
        return SafetyReportDetailSerializer(
            self._reports(obj),
            many=True,
        ).data

    def get_events(self, obj):
        events = getattr(obj, "recent_safety_events", [])[:50]
        return SafetyModerationEventSerializer(events, many=True).data

    class Meta(SafetyCaseSummarySerializer.Meta):
        fields = SafetyCaseSummarySerializer.Meta.fields + ["reports", "events"]
        read_only_fields = fields


class EvidenceCaseOrganizationQuerySerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()

    def validate(self, attrs):
        unsupported_fields = set(self.initial_data) - {"organization_id"}
        if unsupported_fields:
            raise serializers.ValidationError(
                {
                    field: "This query parameter is not supported."
                    for field in sorted(unsupported_fields)
                }
            )
        return attrs


class EvidenceCaseQueueFilterSerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()
    evidence_status = serializers.ChoiceField(
        choices=EvidenceSubmission.EvidenceStatus.choices,
        required=False,
        default=EvidenceSubmission.EvidenceStatus.UNVERIFIED,
    )
    limit = serializers.IntegerField(
        required=False,
        default=20,
        min_value=1,
        max_value=100,
    )
    offset = serializers.IntegerField(
        required=False,
        default=0,
        min_value=0,
    )

    def validate(self, attrs):
        supported_fields = {
            "organization_id",
            "evidence_status",
            "limit",
            "offset",
        }
        unsupported_fields = set(self.initial_data) - supported_fields
        if unsupported_fields:
            raise serializers.ValidationError(
                {
                    field: "This query parameter is not supported."
                    for field in sorted(unsupported_fields)
                }
            )
        return attrs


class EvidenceCaseActionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=[
            EvidenceSubmission.EvidenceStatus.VERIFIED,
            EvidenceSubmission.EvidenceStatus.REJECTED,
        ]
    )
    expected_status = serializers.ChoiceField(
        choices=[EvidenceSubmission.EvidenceStatus.UNVERIFIED],
    )
    moderator_notes = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        max_length=2000,
        default="",
    )
    rejection_reason = serializers.ChoiceField(
        choices=EvidenceSubmission.RejectionReason.choices,
        required=False,
        allow_null=True,
    )

    def validate(self, attrs):
        supported_fields = {
            "decision",
            "expected_status",
            "moderator_notes",
            "rejection_reason",
        }
        unsupported_fields = set(self.initial_data) - supported_fields
        if unsupported_fields:
            raise serializers.ValidationError(
                {
                    field: "This field is not supported."
                    for field in sorted(unsupported_fields)
                }
            )

        decision = attrs["decision"]
        rejection_reason = attrs.get("rejection_reason")
        if (
            decision == EvidenceSubmission.EvidenceStatus.REJECTED
            and not rejection_reason
        ):
            raise serializers.ValidationError(
                {
                    "rejection_reason": (
                        "A rejection reason is required when rejecting evidence."
                    )
                }
            )
        if (
            decision == EvidenceSubmission.EvidenceStatus.VERIFIED
            and rejection_reason is not None
        ):
            raise serializers.ValidationError(
                {
                    "rejection_reason": (
                        "A rejection reason cannot be supplied when verifying "
                        "evidence."
                    )
                }
            )
        return attrs


class EvidenceReviewOrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name", "slug"]
        read_only_fields = fields


class EvidenceReviewUserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username"]
        read_only_fields = fields


class EvidenceReviewClaimSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Claim
        fields = [
            "id",
            "claim_type",
            "context_text",
            "url_link",
            "source_link",
            "media_url",
        ]
        read_only_fields = fields


class EvidenceReviewThreadSummarySerializer(serializers.ModelSerializer):
    claim = EvidenceReviewClaimSummarySerializer(read_only=True)

    class Meta:
        model = Thread
        fields = ["id", "caption", "created_at", "claim"]
        read_only_fields = fields


class EvidenceReviewEvidenceSerializer(serializers.ModelSerializer):
    contributor = EvidenceReviewUserSummarySerializer(read_only=True)
    evidence_type_label = serializers.CharField(
        source="get_evidence_type_display",
        read_only=True,
    )
    evidence_status = serializers.SerializerMethodField()
    evidence_status_label = serializers.SerializerMethodField()
    is_self_submission = serializers.SerializerMethodField()

    def get_evidence_status(self, obj):
        case = self.context.get("evidence_case")
        if case is None or case.status in ACTIVE_CASE_STATUSES:
            return obj.evidence_status

        if (
            case.status == ModerationCase.Status.RESOLVED
            and case.resolution_code
            in {
                EvidenceSubmission.EvidenceStatus.VERIFIED,
                EvidenceSubmission.EvidenceStatus.REJECTED,
            }
        ):
            return case.resolution_code

        return None

    def get_evidence_status_label(self, obj):
        status_value = self.get_evidence_status(obj)
        return dict(EvidenceSubmission.EvidenceStatus.choices).get(status_value)

    def get_is_self_submission(self, obj):
        request = self.context.get("request")
        return bool(
            request
            and request.user
            and request.user.is_authenticated
            and obj.contributor_id == request.user.id
        )

    class Meta:
        model = EvidenceSubmission
        fields = [
            "id",
            "evidence_caption",
            "evidence_url",
            "evidence_type",
            "evidence_type_label",
            "evidence_verdict",
            "evidence_status",
            "evidence_status_label",
            "submitted_at",
            "contributor",
            "is_self_submission",
        ]
        read_only_fields = fields


class EvidenceModerationEventSerializer(serializers.ModelSerializer):
    actor = EvidenceReviewUserSummarySerializer(read_only=True)

    class Meta:
        model = ModerationEvent
        fields = [
            "event_type",
            "actor",
            "from_status",
            "to_status",
            "reason_code",
            "notes",
            "created_at",
        ]
        read_only_fields = fields


class EvidenceCaseSummarySerializer(serializers.ModelSerializer):
    evidence = serializers.SerializerMethodField()
    thread = EvidenceReviewThreadSummarySerializer(
        source="evidence_submission.thread",
        read_only=True,
    )
    organization = EvidenceReviewOrganizationSerializer(read_only=True)

    def get_evidence(self, obj):
        return EvidenceReviewEvidenceSerializer(
            obj.evidence_submission,
            context={
                **self.context,
                "evidence_case": obj,
            },
        ).data

    class Meta:
        model = ModerationCase
        fields = [
            "id",
            "status",
            "priority",
            "source",
            "created_at",
            "updated_at",
            "evidence",
            "thread",
            "organization",
        ]
        read_only_fields = fields


class EvidenceCaseDetailSerializer(EvidenceCaseSummarySerializer):
    verified_by = serializers.SerializerMethodField()
    verified_at = serializers.SerializerMethodField()
    moderator_notes = serializers.SerializerMethodField()
    rejection_reason = serializers.SerializerMethodField()
    rejection_reason_label = serializers.SerializerMethodField()
    resolved_by = serializers.SerializerMethodField()
    events = serializers.SerializerMethodField()

    @staticmethod
    def _uses_current_evidence_state(obj):
        return obj.status in ACTIVE_CASE_STATUSES

    @staticmethod
    def _historical_review_event(obj):
        event_type = {
            EvidenceSubmission.EvidenceStatus.VERIFIED: (
                ModerationEvent.EventType.EVIDENCE_VERIFIED
            ),
            EvidenceSubmission.EvidenceStatus.REJECTED: (
                ModerationEvent.EventType.EVIDENCE_REJECTED
            ),
        }.get(obj.resolution_code)

        if not event_type:
            return None

        return next(
            (
                event
                for event in getattr(obj, "recent_evidence_events", [])
                if event.event_type == event_type
            ),
            None,
        )

    def get_verified_by(self, obj):
        if self._uses_current_evidence_state(obj):
            reviewer = obj.evidence_submission.verified_by
        elif obj.status == ModerationCase.Status.RESOLVED:
            event = self._historical_review_event(obj)
            reviewer = obj.resolved_by or (event.actor if event else None)
        else:
            reviewer = None

        if reviewer is None:
            return None
        return EvidenceReviewUserSummarySerializer(reviewer).data

    def get_verified_at(self, obj):
        if self._uses_current_evidence_state(obj):
            value = obj.evidence_submission.verified_at
        elif obj.status == ModerationCase.Status.RESOLVED:
            event = self._historical_review_event(obj)
            value = obj.resolved_at or (event.created_at if event else None)
        else:
            value = None

        if value is None:
            return None
        return serializers.DateTimeField().to_representation(value)

    def get_resolved_by(self, obj):
        if obj.resolved_by is None:
            return None
        return EvidenceReviewUserSummarySerializer(obj.resolved_by).data

    def get_moderator_notes(self, obj):
        if self._uses_current_evidence_state(obj):
            return obj.evidence_submission.moderator_notes

        event = self._historical_review_event(obj)
        return event.notes if event else None

    def get_rejection_reason(self, obj):
        if self._uses_current_evidence_state(obj):
            return obj.evidence_submission.rejection_reason

        if (
            obj.status != ModerationCase.Status.RESOLVED
            or obj.resolution_code != EvidenceSubmission.EvidenceStatus.REJECTED
        ):
            return None

        event = self._historical_review_event(obj)
        valid_reasons = {
            value for value, _label in EvidenceSubmission.RejectionReason.choices
        }
        if event and event.reason_code in valid_reasons:
            return event.reason_code
        return None

    def get_rejection_reason_label(self, obj):
        reason = self.get_rejection_reason(obj)
        return dict(EvidenceSubmission.RejectionReason.choices).get(reason)

    def get_events(self, obj):
        events = getattr(obj, "recent_evidence_events", [])[:50]
        return EvidenceModerationEventSerializer(events, many=True).data

    class Meta(EvidenceCaseSummarySerializer.Meta):
        fields = EvidenceCaseSummarySerializer.Meta.fields + [
            "verified_by",
            "verified_at",
            "moderator_notes",
            "rejection_reason",
            "rejection_reason_label",
            "resolved_by",
            "resolved_at",
            "resolution_code",
            "resolution_summary",
            "events",
        ]
        read_only_fields = fields


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
            claim_provenance = (
                get_claim_adjudication_provenance(obj.thread.claim)
                if obj.thread.claim
                else None
            )

            return {
                "id": str(obj.thread.id),
                "caption": obj.thread.caption,
                "status": obj.thread.status,
                "created_at": obj.thread.created_at,
                "claim": (
                    {
                        "id": str(obj.thread.claim.id),
                        "context_text": obj.thread.claim.context_text,
                        "verdict": claim_provenance["verdict"]
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


class _RejectUnsupportedAdjudicationFieldsMixin:
    def validate(self, attrs):
        unsupported_fields = set(self.initial_data) - set(self.fields)
        if unsupported_fields:
            raise serializers.ValidationError(
                {
                    field: "This field is not supported."
                    for field in sorted(unsupported_fields)
                }
            )
        return attrs


class AdjudicationOrganizationQuerySerializer(serializers.Serializer):
    organization_id = serializers.UUIDField(required=True)


class AdjudicationCaseQueueFilterSerializer(serializers.Serializer):
    organization_id = serializers.UUIDField(required=True)
    status = serializers.ChoiceField(
        choices=ModerationCase.Status.choices,
        required=False,
        allow_null=True,
        default=None,
    )
    priority = serializers.ChoiceField(
        choices=ModerationCase.Priority.choices,
        required=False,
        allow_null=True,
        default=None,
    )
    limit = serializers.IntegerField(
        required=False,
        default=20,
        min_value=1,
        max_value=100,
    )
    offset = serializers.IntegerField(
        required=False,
        default=0,
        min_value=0,
    )

    def validate(self, attrs):
        supported_fields = {
            "organization_id",
            "status",
            "priority",
            "limit",
            "offset",
        }
        unsupported_fields = set(self.initial_data) - supported_fields
        errors = {
            field: "This query parameter is not supported."
            for field in sorted(unsupported_fields)
        }

        getlist = getattr(self.initial_data, "getlist", None)
        if getlist is not None:
            duplicate_fields = {
                field
                for field in supported_fields.intersection(self.initial_data)
                if len(getlist(field)) != 1
            }
            errors.update(
                {
                    field: "This query parameter may only be supplied once."
                    for field in sorted(duplicate_fields)
                }
            )

        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class AdjudicationActionSerializer(
    _RejectUnsupportedAdjudicationFieldsMixin,
    serializers.Serializer,
):
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
        required=True,
        min_value=0,
    )

    verification_run_id = serializers.UUIDField(
        required=False,
        allow_null=True,
    )


class ModerationDecisionSerializer(AdjudicationActionSerializer):
    case_id = serializers.UUIDField(required=True)

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


class AdjudicationCaseQueueOrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name"]
        read_only_fields = fields


class AdjudicationCaseQueueClaimSerializer(serializers.ModelSerializer):
    class Meta:
        model = Claim
        fields = ["id", "claim_type", "context_text"]
        read_only_fields = fields


class AdjudicationCaseQueueDecisionSerializer(serializers.ModelSerializer):
    verdict_label = serializers.CharField(
        source="get_verdict_display",
        read_only=True,
    )

    class Meta:
        model = AdjudicationDecision
        fields = [
            "id",
            "verdict",
            "verdict_label",
            "revision_number",
            "decided_at",
        ]
        read_only_fields = fields


class AdjudicationCaseQueueSerializer(serializers.ModelSerializer):
    claim = AdjudicationCaseQueueClaimSerializer(read_only=True)
    status_label = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    workflow_state = serializers.SerializerMethodField()
    priority_label = serializers.CharField(
        source="get_priority_display",
        read_only=True,
    )
    evidence_review = serializers.SerializerMethodField()
    current_decision = serializers.SerializerMethodField()
    adjudication_blocked = serializers.BooleanField(
        source="has_adjudication_history",
        read_only=True,
    )

    def get_workflow_state(self, obj):
        if obj.status == ModerationCase.Status.RESOLVED:
            return "RESOLVED"
        if obj.status == ModerationCase.Status.CANCELLED:
            return "CANCELLED"
        return "ACTIVE"

    def get_evidence_review(self, obj):
        return {
            "total": obj.total_evidence,
            "verified": obj.verified_evidence,
            "rejected": obj.rejected_evidence,
            "unreviewed": obj.unreviewed_evidence,
            "active_evidence_cases": obj.active_evidence_cases,
            "all_reviewed": (
                obj.total_evidence > 0 and obj.unreviewed_evidence == 0
            ),
        }

    def get_current_decision(self, obj):
        provenance = get_claim_adjudication_provenance(obj.claim)
        decision = provenance["decision"]
        organization = self.context.get("organization")

        if (
            decision is None
            or organization is None
            or decision.organization_id != organization.id
            or not provenance["is_attributable"]
        ):
            return None

        if (
            provenance["status"] == AdjudicationProvenance.HUMAN_ADJUDICATION
            and decision.moderation_case.organization_id != organization.id
        ):
            return None

        return AdjudicationCaseQueueDecisionSerializer(decision).data

    class Meta:
        model = ModerationCase
        fields = [
            "id",
            "status",
            "status_label",
            "workflow_state",
            "priority",
            "priority_label",
            "source",
            "created_at",
            "updated_at",
            "resolved_at",
            "claim",
            "evidence_review",
            "current_decision",
            "adjudication_blocked",
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
