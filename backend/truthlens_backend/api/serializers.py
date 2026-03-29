from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Claim, Thread, UserProfile, EvidenceSubmission, Vote, ThreadComment, ThreadFlag
from .services import validate_public_url, check_url_threat_reputation
from .trust_service import calculate_trust_components

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password']

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already taken.")
        return value

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        UserProfile.objects.create(user=user)
        return user

class UserSerializer(serializers.ModelSerializer):
    trust_score = serializers.FloatField(source="profile.trust_score", read_only=True)
    trust_breakdown = serializers.SerializerMethodField()
    is_email_verified = serializers.BooleanField(
        source="profile.is_email_verified", read_only=True
    )
    date_joined = serializers.DateTimeField(read_only=True)
    role = serializers.CharField(source="profile.role", read_only=True)

    def get_trust_breakdown(self, obj):
        return calculate_trust_components(obj)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "trust_score",
            "trust_breakdown",
            "is_email_verified",
            "date_joined",
            "role",
        ]


class CurrentUserSerializer(UserSerializer):
    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields


class UserProfileSerializer(serializers.ModelSerializer):
    trust_score = serializers.FloatField(read_only=True)
    role = serializers.CharField(read_only=True)
    class Meta:
        model = UserProfile
        fields = ["id", "user", "trust_score", "bio", "is_email_verified", "role"]
        read_only_fields = ["id", "user", "trust_score", "is_email_verified", "role"]


class ClaimSerializer(serializers.ModelSerializer):
    effective_verdict = serializers.SerializerMethodField()
    has_moderator_verdict = serializers.SerializerMethodField()
    verified_evidence_count = serializers.SerializerMethodField()
    moderator_verdict_info = serializers.SerializerMethodField()

    def get_effective_verdict(self, obj):
        return obj.final_verdict or obj.verdict or obj.ai_verdict
    
    def get_has_moderator_verdict(self, obj):
        """Check if moderators have set a final verdict on this claim"""
        # Direct check: final_verdict is only set when moderators have verified evidence
        return bool(obj.final_verdict)
    
    def get_verified_evidence_count(self, obj):
        """Get count of verified evidence for this claim"""
        from .models import EvidenceSubmission
        return EvidenceSubmission.objects.filter(
            thread__claim=obj,
            evidence_status='VERIFIED'
        ).count()
    
    def get_moderator_verdict_info(self, obj):
        """Return moderator verdict status and supporting evidence"""
        if obj.final_verdict:
            return {
                "verdict": obj.final_verdict,
                "source": "MODERATORS",
                "verified_evidence_count": self.get_verified_evidence_count(obj)
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
            "verdict",
            "ai_summary",
            "source_type",
            "consensus_score",
            "verified_via",
            "source_link",
            "media_url",
            "has_moderator_verdict",
            "verified_evidence_count",
            "moderator_verdict_info",
            "last_updated",
        ]


class ThreadSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    claim = ClaimSerializer(read_only=True)
    claim_id = serializers.UUIDField(write_only=True)
    evidence_count = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    flag_count = serializers.SerializerMethodField()

    def get_flag_count(self, obj):
        return obj.flags.count()

    def get_evidence_count(self, obj):
        return obj.evidence_submissions.count()

    def get_comment_count(self, obj):
        return obj.comments.count()

    def validate(self, attrs):
        if self.instance and "claim_id" in attrs:
            raise serializers.ValidationError(
                {"claim_id": "Cannot be changed after thread creation."}
            )
        return attrs

    class Meta:
        model = Thread
        fields = [
            "id",
            "claim",
            "claim_id",
            "author",
            "caption",
            "status",
            "flag_reason",
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
            "claim",
            "author",
            "status",
            "flag_reason",
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

    def get_thread(self, obj):
        """Return full thread with nested claim for moderation queue display."""
        if obj.thread:
            return {
                "id": str(obj.thread.id),
                "caption": obj.thread.caption,
                "status": obj.thread.status,
                "created_at": obj.thread.created_at,
                "claim": {
                    "id": str(obj.thread.claim.id),
                    "context_text": obj.thread.claim.context_text,
                    "verdict": obj.thread.claim.verdict,
                } if obj.thread.claim else None,
            }
        return None

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
        ]

    def validate(self, attrs):
        if self.instance and "thread_id" in attrs:
            raise serializers.ValidationError(
                {"thread_id": "Cannot be changed after evidence creation."}
            )
        return attrs


class ThreadDetailSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
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
            "claim",
            "claim_id",
            "author",
            "caption",
            "status",
            "flag_reason",
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
        choices=["FACT", "FAKE", "MISLEADING", "SATIRE", "UNVERIFIED"]
    )
    moderator_notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    status = serializers.ChoiceField(choices=["OPEN", "CLOSED", "REJECTED"], required=False)


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
