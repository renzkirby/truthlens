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
    AccountabilityEvent,
)
from .accountability_query_service import (
    AccountabilityDomain,
    DOMAIN_LABELS as ACCOUNTABILITY_DOMAIN_LABELS,
    DOMAIN_RESOURCES as ACCOUNTABILITY_DOMAIN_RESOURCES,
    ORGANIZATION_ACTIONS,
    ORGANIZATION_DOMAINS,
    SAFETY_ACTIONS,
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
    get_adjudication_decision_provenance,
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


class AdjudicationCaseDetailQuerySerializer(serializers.Serializer):
    organization_id = serializers.UUIDField(required=True)

    def validate(self, attrs):
        supported_fields = {"organization_id"}
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


class AdjudicationCaseDetailUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username"]
        read_only_fields = fields


class AdjudicationCaseDetailThreadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Thread
        fields = ["id", "caption", "created_at"]
        read_only_fields = fields


class AdjudicationCaseDetailClaimSerializer(serializers.ModelSerializer):
    threads = serializers.SerializerMethodField()

    def get_threads(self, obj):
        return AdjudicationCaseDetailThreadSerializer(
            self.context["case"].adjudication_threads,
            many=True,
        ).data

    class Meta:
        model = Claim
        fields = [
            "id",
            "claim_type",
            "context_text",
            "url_link",
            "source_link",
            "media_url",
            "threads",
        ]
        read_only_fields = fields


class AdjudicationCaseDetailEvidenceSerializer(serializers.ModelSerializer):
    evidence_type_label = serializers.CharField(
        source="get_evidence_type_display",
        read_only=True,
    )
    evidence_status_label = serializers.CharField(
        source="get_evidence_status_display",
        read_only=True,
    )
    contributor = AdjudicationCaseDetailUserSerializer(read_only=True)
    reviewed_by = AdjudicationCaseDetailUserSerializer(
        source="verified_by",
        read_only=True,
    )
    reviewed_at = serializers.DateTimeField(
        source="verified_at",
        read_only=True,
    )
    review_notes = serializers.CharField(
        source="moderator_notes",
        read_only=True,
    )
    rejection_reason_label = serializers.CharField(
        source="get_rejection_reason_display",
        read_only=True,
    )
    is_current_user_contributor = serializers.SerializerMethodField()

    def get_is_current_user_contributor(self, obj):
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
            "thread_id",
            "evidence_caption",
            "evidence_type",
            "evidence_type_label",
            "evidence_status",
            "evidence_status_label",
            "evidence_url",
            "submitted_at",
            "contributor",
            "reviewed_by",
            "reviewed_at",
            "review_notes",
            "rejection_reason",
            "rejection_reason_label",
            "is_current_user_contributor",
        ]
        read_only_fields = fields


class AdjudicationCaseDetailDecisionSerializer(serializers.ModelSerializer):
    verdict_label = serializers.CharField(
        source="get_verdict_display",
        read_only=True,
    )
    decided_by = serializers.SerializerMethodField()
    organization = serializers.SerializerMethodField()
    moderation_case_id = serializers.SerializerMethodField()
    verification_run_id = serializers.UUIDField(
        read_only=True,
        allow_null=True,
    )
    supersedes_id = serializers.SerializerMethodField()
    provenance = serializers.SerializerMethodField()

    @staticmethod
    def _provenance(obj):
        provenance = getattr(obj, "adjudication_provenance", None)
        if provenance is None:
            provenance = get_adjudication_decision_provenance(
                obj.claim,
                obj,
            )
        return provenance

    def get_decided_by(self, obj):
        if not self._provenance(obj)["is_attributable"]:
            return None
        if obj.decided_by is None:
            return None
        return AdjudicationCaseDetailUserSerializer(obj.decided_by).data

    def get_organization(self, obj):
        if obj.organization is None:
            return None
        return AdjudicationCaseQueueOrganizationSerializer(
            obj.organization
        ).data

    def get_moderation_case_id(self, obj):
        return str(obj.moderation_case_id) if obj.moderation_case_id else None

    def get_supersedes_id(self, obj):
        visible_ids = self.context.get("visible_decision_ids", set())
        if obj.supersedes_id in visible_ids:
            return str(obj.supersedes_id)
        return None

    def get_provenance(self, obj):
        provenance = self._provenance(obj)
        return {
            "status": provenance["status"],
            "is_attributable": provenance["is_attributable"],
        }

    class Meta:
        model = AdjudicationDecision
        fields = [
            "id",
            "moderation_case_id",
            "verification_run_id",
            "verdict",
            "verdict_label",
            "canonical_claim",
            "rationale",
            "decided_by",
            "organization",
            "revision_number",
            "supersedes_id",
            "is_current",
            "decided_at",
            "provenance",
        ]
        read_only_fields = fields


class AdjudicationCaseDetailEventSerializer(serializers.ModelSerializer):
    event_type_label = serializers.CharField(
        source="get_event_type_display",
        read_only=True,
    )
    actor = AdjudicationCaseDetailUserSerializer(read_only=True)

    class Meta:
        model = ModerationEvent
        fields = [
            "event_type",
            "event_type_label",
            "actor",
            "from_status",
            "to_status",
            "reason_code",
            "notes",
            "created_at",
        ]
        read_only_fields = fields


class AdjudicationCaseDetailSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    workflow_state = serializers.SerializerMethodField()
    priority_label = serializers.CharField(
        source="get_priority_display",
        read_only=True,
    )
    source_label = serializers.CharField(
        source="get_source_display",
        read_only=True,
    )
    organization = AdjudicationCaseQueueOrganizationSerializer(read_only=True)
    claim = serializers.SerializerMethodField()
    evidence_review = serializers.SerializerMethodField()
    assignment = serializers.SerializerMethodField()
    resolution = serializers.SerializerMethodField()
    current_decision = serializers.SerializerMethodField()
    decision_history = serializers.SerializerMethodField()
    events = serializers.SerializerMethodField()
    action_state = serializers.SerializerMethodField()

    def get_workflow_state(self, obj):
        if obj.status == ModerationCase.Status.RESOLVED:
            return "RESOLVED"
        if obj.status == ModerationCase.Status.CANCELLED:
            return "CANCELLED"
        return "ACTIVE"

    def get_claim(self, obj):
        return AdjudicationCaseDetailClaimSerializer(
            obj.claim,
            context={"case": obj},
        ).data

    def get_evidence_review(self, obj):
        evidence = obj.adjudication_evidence
        verified = sum(
            item.evidence_status == EvidenceSubmission.EvidenceStatus.VERIFIED
            for item in evidence
        )
        rejected = sum(
            item.evidence_status == EvidenceSubmission.EvidenceStatus.REJECTED
            for item in evidence
        )
        unreviewed = sum(
            item.evidence_status == EvidenceSubmission.EvidenceStatus.UNVERIFIED
            for item in evidence
        )
        return {
            "basis": "CURRENT_EVIDENCE_RECORDS",
            "total": len(evidence),
            "verified": verified,
            "rejected": rejected,
            "unreviewed": unreviewed,
            "active_evidence_cases": (
                obj.adjudication_active_evidence_case_count
            ),
            "all_reviewed": bool(evidence and unreviewed == 0),
            "items": AdjudicationCaseDetailEvidenceSerializer(
                evidence,
                many=True,
                context={"request": self.context.get("request")},
            ).data,
        }

    def get_assignment(self, obj):
        assignment = obj.adjudication_assignment
        if assignment is None:
            return None
        return {
            "id": str(assignment.id),
            "status": assignment.status,
            "claimed_by": (
                AdjudicationCaseDetailUserSerializer(
                    assignment.claimed_by
                ).data
                if assignment.claimed_by is not None
                else None
            ),
        }

    def get_resolution(self, obj):
        if not any(
            [
                obj.resolution_code,
                obj.resolution_summary,
                obj.resolved_by_id,
                obj.resolved_at,
            ]
        ):
            return None
        return {
            "code": obj.resolution_code,
            "summary": obj.resolution_summary,
            "resolved_by": (
                AdjudicationCaseDetailUserSerializer(obj.resolved_by).data
                if obj.resolved_by is not None
                else None
            ),
            "resolved_at": obj.resolved_at,
        }

    def _serialize_decision(self, obj, decision):
        if decision is None:
            return None
        return AdjudicationCaseDetailDecisionSerializer(
            decision,
            context={
                "visible_decision_ids": obj.adjudication_visible_decision_ids,
            },
        ).data

    def get_current_decision(self, obj):
        return self._serialize_decision(
            obj,
            obj.adjudication_current_decision,
        )

    def get_decision_history(self, obj):
        history = [
            decision
            for decision in obj.adjudication_visible_decisions
            if not decision.is_current
        ]
        return {
            "count": obj.adjudication_visible_history_count,
            "truncated": obj.adjudication_visible_history_count > len(history),
            "has_restricted_records": obj.adjudication_has_restricted_history,
            "results": AdjudicationCaseDetailDecisionSerializer(
                history,
                many=True,
                context={
                    "visible_decision_ids": (
                        obj.adjudication_visible_decision_ids
                    ),
                },
            ).data,
        }

    def get_events(self, obj):
        events = obj.adjudication_events
        return {
            "count": obj.adjudication_event_count,
            "truncated": obj.adjudication_event_count > len(events),
            "results": AdjudicationCaseDetailEventSerializer(
                events,
                many=True,
            ).data,
        }

    def get_action_state(self, obj):
        state = obj.adjudication_action_state
        return {
            "can_issue_first_decision": state["can_issue_first_decision"],
            "expected_revision": state["expected_revision"],
            "preconditions": {
                "case_id": str(state["preconditions"]["case_id"]),
                "organization_id": str(
                    state["preconditions"]["organization_id"]
                ),
                "expected_revision": state["preconditions"][
                    "expected_revision"
                ],
            },
            "blockers": state["blockers"],
        }

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
            "source_label",
            "created_at",
            "updated_at",
            "resolved_at",
            "organization",
            "claim",
            "evidence_review",
            "assignment",
            "resolution",
            "current_decision",
            "decision_history",
            "events",
            "action_state",
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
        "edit_generation",
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
    organization_id = serializers.UUIDField()

    expected_decision_revision = serializers.IntegerField(
        min_value=1,
    )

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

class FactCheckDraftUpdateSerializer(
    FactCheckInputProtectionMixin,
    serializers.Serializer,
):
    organization_id = serializers.UUIDField()

    expected_edit_generation = serializers.IntegerField(
        min_value=1,
    )

    expected_decision_revision = serializers.IntegerField(
        min_value=1,
    )

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

        editable_fields = {
            "headline",
            "summary",
            "article_body",
            "source_urls",
        }
        if not editable_fields.intersection(attrs):
            raise serializers.ValidationError(
                "At least one editable field " "must be provided."
            )

        return attrs


class EditorialRevisionDraftCreateSerializer(
    FactCheckInputProtectionMixin,
    serializers.Serializer,
):
    organization_id = serializers.UUIDField()
    expected_predecessor_version = serializers.IntegerField(min_value=1)
    expected_decision_revision = serializers.IntegerField(min_value=1)
    revision_reason = serializers.CharField(
        max_length=2000,
        allow_blank=False,
        trim_whitespace=True,
    )
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
        child=serializers.URLField(max_length=2000),
        required=False,
        allow_empty=True,
    )


class EditorialRevisionPublishSerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()
    expected_predecessor_version = serializers.IntegerField(min_value=1)
    expected_revision_version = serializers.IntegerField(min_value=1)
    expected_edit_generation = serializers.IntegerField(min_value=1)
    expected_decision_revision = serializers.IntegerField(min_value=1)


class FactCheckTransitionSerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()
    expected_edit_generation = serializers.IntegerField(min_value=1)
    expected_decision_revision = serializers.IntegerField(min_value=1)


class FactCheckRecoverySerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()
    expected_edit_generation = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(
        max_length=2000,
        allow_blank=False,
        trim_whitespace=True,
    )


class PublicationWorkflowQueueQuerySerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()
    queue = serializers.ChoiceField(choices=["DRAFTING", "REVIEW"])
    workflow_kind = serializers.ChoiceField(
        choices=["INITIAL", "EDITORIAL_REVISION", "ALL"],
        default="INITIAL",
    )
    limit = serializers.IntegerField(default=20, min_value=1, max_value=100)
    offset = serializers.IntegerField(default=0, min_value=0)


class PublicationWorkflowDetailQuerySerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()
    workflow_kind = serializers.ChoiceField(
        choices=["INITIAL", "EDITORIAL_REVISION", "ALL"],
        default="INITIAL",
    )


class PublicationWorkflowActorSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()


class PublicationWorkflowOrganizationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.SlugField()


class PublicationWorkflowClaimSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    claim_type = serializers.CharField()
    context_text = serializers.CharField(allow_blank=True, allow_null=True)
    url_link = serializers.URLField(allow_null=True, required=False)
    source_link = serializers.URLField(allow_null=True, required=False)
    media_url = serializers.CharField(allow_null=True, required=False)


class PublicationWorkflowDecisionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    revision_number = serializers.IntegerField()
    canonical_claim = serializers.CharField(allow_blank=True)
    verdict = serializers.CharField()
    rationale = serializers.CharField(allow_blank=True)
    decided_at = serializers.DateTimeField()
    decided_by = PublicationWorkflowActorSerializer(allow_null=True)
    is_current = serializers.BooleanField()


class PublicationWorkflowBlockerSerializer(serializers.Serializer):
    code = serializers.CharField()
    detail = serializers.CharField()


class PublicationWorkflowSourceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    url = serializers.URLField()
    title = serializers.CharField(allow_blank=True, allow_null=True)
    source_type = serializers.CharField()
    source_origin = serializers.ChoiceField(
        choices=[
            "DECISION_EVIDENCE",
            "ORGANIZATION_EDITORIAL",
            "LEGACY_IMPORT",
            "UNKNOWN",
        ]
    )
    provenance = serializers.ChoiceField(choices=["SEALED_EVIDENCE", "EDITORIAL"])
    immutable = serializers.BooleanField()
    is_editorially_selected = serializers.BooleanField(allow_null=True)
    added_by = PublicationWorkflowActorSerializer(allow_null=True)
    captured_evidence_ids = serializers.ListField(
        child=serializers.UUIDField(),
    )


class PublicationWorkflowSealedEvidenceEntrySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    thread_id = serializers.UUIDField()
    evidence_status = serializers.CharField()
    evidence_type = serializers.CharField(allow_blank=True, allow_null=True)
    evidence_caption = serializers.CharField(allow_blank=True, allow_null=True)
    evidence_url = serializers.CharField(allow_blank=True, allow_null=True)
    contributor_id = serializers.CharField()
    reviewer_id = serializers.CharField(allow_null=True)
    submitted_at = serializers.CharField(allow_null=True)
    reviewed_at = serializers.CharField(allow_null=True)
    moderator_notes = serializers.CharField(allow_blank=True, allow_null=True)
    rejection_reason = serializers.CharField(allow_blank=True, allow_null=True)


class PublicationWorkflowSealedEvidenceSerializer(serializers.Serializer):
    basis = serializers.ChoiceField(choices=["SEALED_DECISION_EVIDENCE"])
    decision_snapshot_id = serializers.UUIDField()
    schema_version = serializers.IntegerField()
    captured_at = serializers.DateTimeField()
    count = serializers.IntegerField()
    entries = PublicationWorkflowSealedEvidenceEntrySerializer(many=True)


class PublicationWorkflowConcurrencySerializer(serializers.Serializer):
    edit_generation = serializers.IntegerField(allow_null=True)
    article_version = serializers.IntegerField(allow_null=True)
    decision_revision = serializers.IntegerField()
    predecessor_version = serializers.IntegerField(allow_null=True)


class PublicationWorkflowRevisionPredecessorSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    version = serializers.IntegerField()
    headline = serializers.CharField(allow_blank=True)
    published_at = serializers.DateTimeField(allow_null=True)


class PublicationWorkflowRevisionSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["EDITORIAL_REVISION"])
    reason = serializers.CharField()
    requested_by = PublicationWorkflowActorSerializer(allow_null=True)
    requested_at = serializers.DateTimeField()
    predecessor = PublicationWorkflowRevisionPredecessorSerializer()


class PublicationWorkflowListArticleSerializer(serializers.Serializer):
    publication_status = serializers.CharField()
    version = serializers.IntegerField()
    edit_generation = serializers.IntegerField()
    headline = serializers.CharField(allow_blank=True)
    summary = serializers.CharField(allow_blank=True)


class PublicationWorkflowDetailArticleSerializer(
    PublicationWorkflowListArticleSerializer
):
    article_body = serializers.CharField(allow_blank=True)


class PublicationWorkflowLifecycleSerializer(serializers.Serializer):
    actionable_at = serializers.DateTimeField()
    created_at = serializers.DateTimeField(allow_null=True)
    updated_at = serializers.DateTimeField(allow_null=True)
    drafted_at = serializers.DateTimeField(allow_null=True)
    drafted_by = PublicationWorkflowActorSerializer(allow_null=True)
    submitted_for_review_at = serializers.DateTimeField(allow_null=True)
    reviewed_at = serializers.DateTimeField(allow_null=True)
    reviewed_by = PublicationWorkflowActorSerializer(allow_null=True)
    published_at = serializers.DateTimeField(allow_null=True)
    published_by = PublicationWorkflowActorSerializer(allow_null=True)
    archived_at = serializers.DateTimeField(allow_null=True)


class PublicationWorkflowListItemSerializer(serializers.Serializer):
    resource_type = serializers.ChoiceField(
        choices=["ELIGIBLE_CLAIM", "FACT_CHECK"]
    )
    resource_id = serializers.UUIDField()
    workflow_kind = serializers.ChoiceField(
        choices=["INITIAL", "EDITORIAL_REVISION"]
    )
    revision = PublicationWorkflowRevisionSerializer(allow_null=True)
    fact_check_id = serializers.UUIDField(allow_null=True)
    organization = PublicationWorkflowOrganizationSerializer()
    claim = PublicationWorkflowClaimSerializer()
    decision = PublicationWorkflowDecisionSerializer()
    article = PublicationWorkflowListArticleSerializer(allow_null=True)
    lifecycle = PublicationWorkflowLifecycleSerializer()
    concurrency = PublicationWorkflowConcurrencySerializer()
    allowed_actions = serializers.ListField(child=serializers.CharField())
    blockers = PublicationWorkflowBlockerSerializer(many=True)


class PublicationWorkflowDetailSerializer(PublicationWorkflowListItemSerializer):
    article = PublicationWorkflowDetailArticleSerializer(allow_null=True)
    id = serializers.UUIDField(allow_null=True)
    claim_id = serializers.UUIDField()
    adjudication_decision_id = serializers.UUIDField()
    canonical_claim = serializers.CharField(allow_blank=True)
    verdict = serializers.CharField()
    headline = serializers.CharField(allow_blank=True, allow_null=True)
    summary = serializers.CharField(allow_blank=True, allow_null=True)
    article_body = serializers.CharField(allow_blank=True, allow_null=True)
    publication_status = serializers.CharField(allow_null=True)
    version = serializers.IntegerField(allow_null=True)
    edit_generation = serializers.IntegerField(allow_null=True)
    sources = serializers.ListField(child=serializers.URLField())
    source_items = PublicationWorkflowSourceSerializer(many=True)
    drafted_by = PublicationWorkflowActorSerializer(allow_null=True)
    submitted_for_review_at = serializers.DateTimeField(allow_null=True)
    reviewed_by = PublicationWorkflowActorSerializer(allow_null=True)
    reviewed_at = serializers.DateTimeField(allow_null=True)
    published_by = PublicationWorkflowActorSerializer(allow_null=True)
    published_at = serializers.DateTimeField(allow_null=True)
    archived_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField(allow_null=True)
    updated_at = serializers.DateTimeField(allow_null=True)
    sealed_evidence = PublicationWorkflowSealedEvidenceSerializer(allow_null=True)


class PublicationWorkflowPageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    limit = serializers.IntegerField()
    offset = serializers.IntegerField()
    organization = PublicationWorkflowOrganizationSerializer()
    results = PublicationWorkflowListItemSerializer(many=True)


class OrganizationPublicationLibraryQuerySerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()
    search = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        max_length=120,
        default="",
    )
    limit = serializers.IntegerField(default=20, min_value=1, max_value=100)
    offset = serializers.IntegerField(default=0, min_value=0)


class OrganizationPublicationDetailQuerySerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()


class FactualCorrectionCollectionQuerySerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()
    status = serializers.ChoiceField(
        choices=["ACTIVE", "COMPLETED", "CANCELLED", "ALL"],
        default="ACTIVE",
    )
    limit = serializers.IntegerField(default=20, min_value=1, max_value=100)
    offset = serializers.IntegerField(default=0, min_value=0)


class FactualCorrectionDetailQuerySerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()


class FactualCorrectionRequestMutationSerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()
    expected_predecessor_version = serializers.IntegerField(min_value=1)
    expected_decision_revision = serializers.IntegerField(min_value=1)
    correction_reason = serializers.CharField(
        max_length=2000,
        allow_blank=False,
        trim_whitespace=True,
    )


class FactualCorrectionEvidenceReviewSerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()
    evidence_status = serializers.ChoiceField(
        choices=[
            EvidenceSubmission.EvidenceStatus.VERIFIED,
            EvidenceSubmission.EvidenceStatus.REJECTED,
        ]
    )
    expected_evidence_status = serializers.ChoiceField(
        choices=EvidenceSubmission.EvidenceStatus.values
    )
    expected_case_id = serializers.UUIDField(required=False, allow_null=True)
    moderator_notes = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        max_length=2000,
        default="",
    )
    rejection_reason = serializers.ChoiceField(
        choices=EvidenceSubmission.RejectionReason.values,
        required=False,
        allow_null=True,
    )
    expected_predecessor_version = serializers.IntegerField(min_value=1)
    expected_decision_revision = serializers.IntegerField(min_value=1)


class FactualCorrectionProposalSaveSerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()
    expected_proposal_version = serializers.IntegerField(min_value=0)
    expected_predecessor_version = serializers.IntegerField(min_value=1)
    expected_decision_revision = serializers.IntegerField(min_value=1)
    proposed_verdict = serializers.ChoiceField(
        choices=AdjudicationDecision.Verdict.values
    )
    proposed_canonical_claim = serializers.CharField(
        allow_blank=False,
        trim_whitespace=True,
    )
    proposed_rationale = serializers.CharField(
        allow_blank=False,
        trim_whitespace=True,
    )
    headline = serializers.CharField(
        max_length=300,
        allow_blank=False,
        trim_whitespace=True,
    )
    summary = serializers.CharField(allow_blank=False, trim_whitespace=True)
    article_body = serializers.CharField(allow_blank=False, trim_whitespace=True)
    source_urls = serializers.ListField(
        child=serializers.URLField(max_length=2000),
        allow_empty=False,
    )
    verification_run_id = serializers.UUIDField(required=False, allow_null=True)


class FactualCorrectionConcurrencyMutationSerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()
    expected_proposal_version = serializers.IntegerField(min_value=1)
    expected_predecessor_version = serializers.IntegerField(min_value=1)
    expected_decision_revision = serializers.IntegerField(min_value=1)


class FactualCorrectionCancelSerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()
    expected_proposal_version = serializers.IntegerField(min_value=0)
    expected_predecessor_version = serializers.IntegerField(min_value=1)
    expected_decision_revision = serializers.IntegerField(min_value=1)
    cancellation_reason = serializers.CharField(
        max_length=2000,
        allow_blank=False,
        trim_whitespace=True,
    )


class OrganizationPublicationClaimSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    canonical_claim = serializers.CharField(allow_blank=True)


class OrganizationPublicationLineageSummarySerializer(serializers.Serializer):
    has_predecessor = serializers.BooleanField()
    previous_versions_count = serializers.IntegerField(min_value=0)


class OrganizationPublicationConcurrencySerializer(serializers.Serializer):
    predecessor_version = serializers.IntegerField(min_value=1)
    decision_revision = serializers.IntegerField(min_value=1)


class OrganizationPublicationListItemSerializer(serializers.Serializer):
    publication_id = serializers.UUIDField()
    current_publication_id = serializers.UUIDField()
    history_state = serializers.ChoiceField(choices=["CURRENT"])
    record_state = serializers.ChoiceField(
        choices=["SEALED", "LEGACY_UNSEALED", "INVALID_SEAL"]
    )
    publication_status = serializers.ChoiceField(choices=["PUBLISHED"])
    version = serializers.IntegerField(min_value=1)
    revision_kind = serializers.ChoiceField(
        choices=["INITIAL", "EDITORIAL_REVISION", "FACTUAL_CORRECTION"]
    )
    claim = OrganizationPublicationClaimSerializer()
    verdict = serializers.CharField()
    headline = serializers.CharField(allow_blank=True)
    summary = serializers.CharField(allow_blank=True)
    published_at = serializers.DateTimeField(allow_null=True)
    published_by = PublicationWorkflowActorSerializer(allow_null=True)
    lineage = OrganizationPublicationLineageSummarySerializer()
    concurrency = OrganizationPublicationConcurrencySerializer()
    allowed_actions = serializers.ListField(child=serializers.CharField())
    blockers = PublicationWorkflowBlockerSerializer(many=True)


class OrganizationPublicationPageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    limit = serializers.IntegerField()
    offset = serializers.IntegerField()
    organization = PublicationWorkflowOrganizationSerializer()
    results = OrganizationPublicationListItemSerializer(many=True)


class OrganizationPublicationDecisionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    revision_number = serializers.IntegerField(min_value=1)
    canonical_claim = serializers.CharField(allow_blank=True)
    verdict = serializers.CharField()
    rationale = serializers.CharField(allow_blank=True)
    decided_by = PublicationWorkflowActorSerializer(allow_null=True)
    decided_at = serializers.DateTimeField()


class OrganizationPublicationArticleSerializer(serializers.Serializer):
    headline = serializers.CharField(allow_blank=True)
    summary = serializers.CharField(allow_blank=True)
    article_body = serializers.CharField(allow_blank=True)
    version = serializers.IntegerField(min_value=1)
    revision_kind = serializers.ChoiceField(
        choices=["INITIAL", "EDITORIAL_REVISION", "FACTUAL_CORRECTION"]
    )
    publication_status = serializers.ChoiceField(
        choices=["PUBLISHED", "ARCHIVED"]
    )


class OrganizationPublicationLineageItemSerializer(serializers.Serializer):
    publication_id = serializers.UUIDField()
    version = serializers.IntegerField(min_value=1)
    revision_kind = serializers.ChoiceField(
        choices=["INITIAL", "EDITORIAL_REVISION", "FACTUAL_CORRECTION"]
    )
    headline = serializers.CharField(allow_blank=True)
    published_at = serializers.DateTimeField(allow_null=True)
    published_by = PublicationWorkflowActorSerializer(allow_null=True)
    history_state = serializers.ChoiceField(choices=["CURRENT", "SUPERSEDED"])
    revision_reason = serializers.CharField(allow_null=True, allow_blank=True)


class OrganizationPublicationIdentitySerializer(serializers.Serializer):
    publication_id = serializers.UUIDField()
    version = serializers.IntegerField(min_value=1)


class OrganizationPublicationRevisionSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(
        choices=["EDITORIAL_REVISION", "FACTUAL_CORRECTION"]
    )
    reason = serializers.CharField(allow_null=True, allow_blank=True)
    requested_by = PublicationWorkflowActorSerializer(allow_null=True)
    requested_at = serializers.DateTimeField(allow_null=True)
    predecessor = OrganizationPublicationIdentitySerializer(allow_null=True)


class OrganizationPublicationDetailConcurrencySerializer(serializers.Serializer):
    predecessor_version = serializers.IntegerField(min_value=1)
    article_version = serializers.IntegerField(min_value=1)
    edit_generation = serializers.IntegerField(min_value=1)
    decision_revision = serializers.IntegerField(min_value=1)


class FactualCorrectionConcurrencySerializer(serializers.Serializer):
    expected_predecessor_version = serializers.IntegerField(min_value=1)
    expected_decision_revision = serializers.IntegerField(min_value=1)
    expected_proposal_version = serializers.IntegerField(min_value=0)


class FactualCorrectionPublicationWorkflowSerializer(serializers.Serializer):
    active_request_id = serializers.UUIDField(allow_null=True)
    allowed_actions = serializers.ListField(child=serializers.CharField())
    blockers = serializers.DictField(
        child=serializers.ListField(child=PublicationWorkflowBlockerSerializer())
    )
    concurrency = FactualCorrectionConcurrencySerializer()


class OrganizationPublicationDetailSerializer(serializers.Serializer):
    selected_publication_id = serializers.UUIDField()
    current_publication_id = serializers.UUIDField()
    history_state = serializers.ChoiceField(choices=["CURRENT", "SUPERSEDED"])
    record_state = serializers.ChoiceField(
        choices=["SEALED", "LEGACY_UNSEALED", "INVALID_SEAL"]
    )
    organization = PublicationWorkflowOrganizationSerializer()
    claim = OrganizationPublicationClaimSerializer()
    decision = OrganizationPublicationDecisionSerializer()
    article = OrganizationPublicationArticleSerializer()
    source_items = PublicationWorkflowSourceSerializer(many=True)
    sealed_evidence = PublicationWorkflowSealedEvidenceSerializer(allow_null=True)
    published_by = PublicationWorkflowActorSerializer(allow_null=True)
    published_at = serializers.DateTimeField(allow_null=True)
    revision = OrganizationPublicationRevisionSerializer(allow_null=True)
    lineage = OrganizationPublicationLineageItemSerializer(many=True)
    predecessor = OrganizationPublicationIdentitySerializer(allow_null=True)
    successor = OrganizationPublicationIdentitySerializer(allow_null=True)
    concurrency = OrganizationPublicationDetailConcurrencySerializer()
    allowed_actions = serializers.ListField(child=serializers.CharField())
    blockers = PublicationWorkflowBlockerSerializer(many=True)
    factual_correction_workflow = FactualCorrectionPublicationWorkflowSerializer()


class FactualCorrectionRequestReadSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=["ACTIVE", "COMPLETED", "CANCELLED"])
    correction_reason = serializers.CharField()
    requested_at = serializers.DateTimeField()
    requested_by = PublicationWorkflowActorSerializer()
    updated_at = serializers.DateTimeField()


class FactualCorrectionPredecessorPublicationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    version = serializers.IntegerField(min_value=1)
    headline = serializers.CharField(allow_blank=True)
    summary = serializers.CharField(allow_blank=True)
    publication_status = serializers.CharField()
    revision_kind = serializers.CharField(allow_null=True)
    published_at = serializers.DateTimeField(allow_null=True)


class FactualCorrectionCaseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    priority = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    resolved_at = serializers.DateTimeField(allow_null=True)
    resolved_by = PublicationWorkflowActorSerializer(allow_null=True)
    resolution_code = serializers.CharField(allow_blank=True, allow_null=True)
    resolution_summary = serializers.CharField(allow_blank=True, allow_null=True)


class FactualCorrectionReviewProvenanceSerializer(serializers.Serializer):
    review_event_id = serializers.UUIDField()
    evidence_case_id = serializers.UUIDField()
    reviewed_by = PublicationWorkflowActorSerializer(allow_null=True)
    reviewed_at = serializers.DateTimeField()
    previous_evidence_status = serializers.CharField(allow_null=True)
    new_evidence_status = serializers.CharField(allow_null=True)
    is_reaffirmation = serializers.BooleanField()
    moderator_notes = serializers.CharField(allow_blank=True, allow_null=True)
    rejection_reason = serializers.CharField(allow_blank=True, allow_null=True)


class FactualCorrectionEvidenceItemSerializer(serializers.Serializer):
    evidence_id = serializers.UUIDField()
    evidence_case_id = serializers.UUIDField(allow_null=True)
    evidence_caption = serializers.CharField(allow_blank=True, allow_null=True)
    evidence_url = serializers.CharField(allow_blank=True, allow_null=True)
    evidence_type = serializers.CharField(allow_blank=True, allow_null=True)
    evidence_status = serializers.CharField()
    moderator_notes = serializers.CharField(allow_blank=True, allow_null=True)
    rejection_reason = serializers.CharField(allow_blank=True, allow_null=True)
    submitted_at = serializers.DateTimeField()
    contributor = PublicationWorkflowActorSerializer()
    correction_review = FactualCorrectionReviewProvenanceSerializer(allow_null=True)
    has_qualifying_correction_review = serializers.BooleanField()
    is_reaffirmation = serializers.BooleanField()
    allowed_actions = serializers.ListField(child=serializers.CharField())


class FactualCorrectionEvidenceProjectionSerializer(serializers.Serializer):
    count = serializers.IntegerField(min_value=0)
    reviewed_count = serializers.IntegerField(min_value=0)
    is_complete = serializers.BooleanField()
    has_active_evidence_case = serializers.BooleanField()
    items = FactualCorrectionEvidenceItemSerializer(many=True)


class FactualCorrectionEligibleVerificationRunSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    pipeline_version = serializers.CharField()
    completed_at = serializers.DateTimeField()
    evidence_count = serializers.IntegerField(min_value=0)


class FactualCorrectionProposalReadSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=["DRAFT", "PREPARED"])
    version = serializers.IntegerField(min_value=1)
    proposed_verdict = serializers.CharField()
    proposed_canonical_claim = serializers.CharField()
    proposed_rationale = serializers.CharField()
    headline = serializers.CharField()
    summary = serializers.CharField()
    article_body = serializers.CharField()
    source_urls = serializers.ListField(child=serializers.URLField())
    verification_run_id = serializers.UUIDField(allow_null=True)
    prepared_by = PublicationWorkflowActorSerializer(allow_null=True)
    prepared_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class FactualCorrectionDetailSerializer(serializers.Serializer):
    workflow_kind = serializers.ChoiceField(choices=["FACTUAL_CORRECTION"])
    request = FactualCorrectionRequestReadSerializer()
    organization = PublicationWorkflowOrganizationSerializer()
    claim = PublicationWorkflowClaimSerializer()
    predecessor_publication = FactualCorrectionPredecessorPublicationSerializer()
    predecessor_decision = PublicationWorkflowDecisionSerializer()
    current_decision = PublicationWorkflowDecisionSerializer(allow_null=True)
    completed_publication = FactualCorrectionPredecessorPublicationSerializer(
        allow_null=True
    )
    sealed_predecessor_evidence = PublicationWorkflowSealedEvidenceSerializer(
        allow_null=True
    )
    correction_case = FactualCorrectionCaseSerializer()
    evidence_review = FactualCorrectionEvidenceProjectionSerializer()
    proposal = FactualCorrectionProposalReadSerializer(allow_null=True)
    eligible_verification_runs = FactualCorrectionEligibleVerificationRunSerializer(
        many=True
    )
    stage = serializers.ChoiceField(
        choices=[
            "EVIDENCE_REVIEW",
            "PROPOSAL_DRAFT",
            "PREPARED",
            "COMPLETED",
            "CANCELLED",
        ]
    )
    allowed_actions = serializers.ListField(child=serializers.CharField())
    blockers = serializers.DictField(
        child=serializers.ListField(child=PublicationWorkflowBlockerSerializer())
    )
    concurrency = FactualCorrectionConcurrencySerializer()


class FactualCorrectionQueueItemSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    request_status = serializers.ChoiceField(
        choices=["ACTIVE", "COMPLETED", "CANCELLED"]
    )
    workflow_kind = serializers.ChoiceField(choices=["FACTUAL_CORRECTION"])
    stage = serializers.ChoiceField(
        choices=[
            "EVIDENCE_REVIEW",
            "PROPOSAL_DRAFT",
            "PREPARED",
            "COMPLETED",
            "CANCELLED",
        ]
    )
    correction_reason = serializers.CharField()
    requested_at = serializers.DateTimeField()
    requested_by = PublicationWorkflowActorSerializer()
    claim = PublicationWorkflowClaimSerializer()
    predecessor_publication = FactualCorrectionPredecessorPublicationSerializer()
    predecessor_decision = PublicationWorkflowDecisionSerializer()
    current_decision = PublicationWorkflowDecisionSerializer(allow_null=True)
    completed_publication = FactualCorrectionPredecessorPublicationSerializer(
        allow_null=True
    )
    correction_case = FactualCorrectionCaseSerializer()
    proposal = FactualCorrectionProposalReadSerializer(allow_null=True)
    allowed_actions = serializers.ListField(child=serializers.CharField())
    concurrency = FactualCorrectionConcurrencySerializer()


class FactualCorrectionPageSerializer(serializers.Serializer):
    count = serializers.IntegerField(min_value=0)
    limit = serializers.IntegerField(min_value=1)
    offset = serializers.IntegerField(min_value=0)
    organization = PublicationWorkflowOrganizationSerializer()
    results = FactualCorrectionQueueItemSerializer(many=True)


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


class _StrictAccountabilityQuerySerializer(serializers.Serializer):
    resource_id = serializers.CharField(required=False, allow_blank=True)
    actor = serializers.CharField(required=False, allow_blank=True)
    created_after = serializers.DateTimeField(required=False, allow_null=True)
    created_before = serializers.DateTimeField(required=False, allow_null=True)
    limit = serializers.IntegerField(default=25, min_value=1, max_value=100)
    offset = serializers.IntegerField(default=0, min_value=0)

    def to_internal_value(self, data):
        unknown = sorted(set(data.keys()) - set(self.fields))
        if unknown:
            raise serializers.ValidationError(
                {key: ["Unknown query parameter."] for key in unknown}
            )
        return super().to_internal_value(data)

    def validate(self, attrs):
        created_after = attrs.get("created_after")
        created_before = attrs.get("created_before")
        if created_after and created_before and created_after > created_before:
            raise serializers.ValidationError(
                {
                    "created_before": (
                        "created_before must be at or after created_after."
                    )
                }
            )
        return attrs


_ORGANIZATION_RESOURCE_CHOICES = [
    (value, label)
    for value, label in AccountabilityEvent.ResourceType.choices
    if any(
        value in ACCOUNTABILITY_DOMAIN_RESOURCES[domain]
        for domain in ORGANIZATION_DOMAINS
    )
]


class OrganizationAccountabilityQuerySerializer(
    _StrictAccountabilityQuerySerializer
):
    organization_id = serializers.UUIDField()
    domain = serializers.ChoiceField(
        choices=[(value, ACCOUNTABILITY_DOMAIN_LABELS[value]) for value in ORGANIZATION_DOMAINS],
        required=False,
        allow_blank=True,
    )
    action_type = serializers.ChoiceField(
        choices=[
            (value, dict(AccountabilityEvent.ActionType.choices)[value])
            for value in ORGANIZATION_ACTIONS
        ],
        required=False,
        allow_blank=True,
    )
    resource_type = serializers.ChoiceField(
        choices=_ORGANIZATION_RESOURCE_CHOICES,
        required=False,
        allow_blank=True,
    )


class PlatformAccountabilityQuerySerializer(_StrictAccountabilityQuerySerializer):
    domain = serializers.ChoiceField(
        choices=[
            (
                AccountabilityDomain.SAFETY,
                ACCOUNTABILITY_DOMAIN_LABELS[AccountabilityDomain.SAFETY],
            )
        ],
        required=False,
        allow_blank=True,
    )
    action_type = serializers.ChoiceField(
        choices=[
            (value, dict(AccountabilityEvent.ActionType.choices)[value])
            for value in SAFETY_ACTIONS
        ],
        required=False,
        allow_blank=True,
    )
    resource_type = serializers.ChoiceField(
        choices=[AccountabilityEvent.ResourceType.MODERATION_CASE],
        required=False,
        allow_blank=True,
    )


class AccountabilityActorSerializer(serializers.Serializer):
    id = serializers.CharField(allow_null=True, allow_blank=False)
    username = serializers.CharField(allow_null=True, allow_blank=True)
    historical = serializers.BooleanField()


class AccountabilityOrganizationSerializer(serializers.Serializer):
    id = serializers.UUIDField(allow_null=True)
    name = serializers.CharField(allow_null=True, allow_blank=True)


class AccountabilityAuthoritySerializer(serializers.Serializer):
    scope = serializers.ChoiceField(choices=AccountabilityEvent.AuthorityScope.choices)
    capability = serializers.CharField(allow_blank=True)
    organization = AccountabilityOrganizationSerializer(allow_null=True)


class AccountabilityResourceSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=AccountabilityEvent.ResourceType.choices)
    label = serializers.CharField()
    id = serializers.CharField()


class AccountabilityEventSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    action_type = serializers.ChoiceField(choices=AccountabilityEvent.ActionType.choices)
    action_label = serializers.CharField()
    domain = serializers.ChoiceField(choices=list(ACCOUNTABILITY_DOMAIN_LABELS))
    domain_label = serializers.CharField()
    actor = AccountabilityActorSerializer(allow_null=True)
    authority = AccountabilityAuthoritySerializer()
    subject_organization = AccountabilityOrganizationSerializer(allow_null=True)
    resource = AccountabilityResourceSerializer()
    previous_state = serializers.DictField()
    new_state = serializers.DictField()
    reason_code = serializers.CharField(allow_blank=True)
    notes = serializers.CharField(allow_blank=True)
    context = serializers.DictField()
    created_at = serializers.DateTimeField()


class AccountabilityFilterOptionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class AccountabilityActionFilterOptionSerializer(
    AccountabilityFilterOptionSerializer
):
    domain = serializers.ChoiceField(choices=list(ACCOUNTABILITY_DOMAIN_LABELS))


class AccountabilityFilterOptionsSerializer(serializers.Serializer):
    domains = AccountabilityFilterOptionSerializer(many=True)
    actions = AccountabilityActionFilterOptionSerializer(many=True)
    resources = AccountabilityFilterOptionSerializer(many=True)


class AccountabilityPageSerializer(serializers.Serializer):
    count = serializers.IntegerField(min_value=0)
    limit = serializers.IntegerField(min_value=1, max_value=100)
    offset = serializers.IntegerField(min_value=0)
    scope = serializers.ChoiceField(choices=["ORGANIZATION", "PLATFORM"])
    organization = AccountabilityOrganizationSerializer(allow_null=True)
    filter_options = AccountabilityFilterOptionsSerializer()
    results = AccountabilityEventSerializer(many=True)
