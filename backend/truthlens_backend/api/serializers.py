from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Claim, Thread, UserProfile, EvidenceSubmission, Vote

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
    date_joined = serializers. DateTimeField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "trust_score", "date_joined"]


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ["id", "user", "trust_score", "bio"]


class ClaimSerializer(serializers.ModelSerializer):
    class Meta:
        model = Claim
        fields = [
            "id",
            "claim_type",
            "context_text",
            "verdict",
            "ai_summary",
            "source_type",
            "consensus_score",
            "verified_via",
            "source_link",
            "last_updated",
        ]


class EvidenceSubmissionSerializer(serializers.ModelSerializer):
    contributor = UserSerializer(read_only=True)

    class Meta:
        model = EvidenceSubmission
        fields = [
            "id",
            "thread",
            "contributor",
            "evidence_caption",
            "evidence_url",
            "evidence_type",
            "contributor_trust_snapshot",
            "submitted_at",
        ]


class ThreadSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    claim = ClaimSerializer(read_only=True)
    claim_id = serializers.UUIDField(write_only=True)
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
            "claim",
            "claim_id",
            "author",
            "caption",
            "status",
            "flag_reason",
            "created_at",
            "evidence_count",
            "comment_count",
        ]


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
