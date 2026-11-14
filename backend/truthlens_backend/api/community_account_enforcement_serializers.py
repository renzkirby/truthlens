from rest_framework import serializers

from .community_account_enforcement_service import TEMPORARY_DURATION_MAP
from .models import (
    CommunityAccountEnforcement,
    CommunityAccountEnforcementReview,
)


class StrictAccountEnforcementSerializer(serializers.Serializer):
    def validate_supported_fields(self, supported):
        unsupported = set(self.initial_data) - set(supported)
        if unsupported:
            raise serializers.ValidationError(
                {
                    field: "This field is not supported."
                    for field in sorted(unsupported)
                }
            )


class AccountEnforcementIssueSerializer(StrictAccountEnforcementSerializer):
    action = serializers.ChoiceField(
        choices=CommunityAccountEnforcement.Action.choices
    )
    duration_code = serializers.ChoiceField(
        choices=[(value, value) for value in TEMPORARY_DURATION_MAP],
        required=False,
        allow_blank=True,
        default="",
    )
    user_rationale = serializers.CharField(
        min_length=20,
        max_length=3000,
        trim_whitespace=True,
    )
    internal_note = serializers.CharField(
        max_length=5000,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        default="",
    )
    confirm_indefinite = serializers.BooleanField(
        required=False,
        default=False,
    )

    def validate(self, attrs):
        self.validate_supported_fields(
            {
                "action",
                "duration_code",
                "user_rationale",
                "internal_note",
                "confirm_indefinite",
            }
        )
        action = attrs["action"]
        duration_code = attrs.get("duration_code", "")
        confirm_indefinite = attrs.get("confirm_indefinite", False)

        if (
            action
            == CommunityAccountEnforcement.Action.TEMPORARY_RESTRICTION
            and not duration_code
        ):
            raise serializers.ValidationError(
                {"duration_code": "Choose 24 hours, 7 days, or 30 days."}
            )
        if (
            action
            != CommunityAccountEnforcement.Action.TEMPORARY_RESTRICTION
            and duration_code
        ):
            raise serializers.ValidationError(
                {"duration_code": "Only temporary restrictions use a duration."}
            )
        if (
            action
            == CommunityAccountEnforcement.Action.INDEFINITE_RESTRICTION
            and not confirm_indefinite
        ):
            raise serializers.ValidationError(
                {
                    "confirm_indefinite": (
                        "Confirm that this restriction has no automatic end date."
                    )
                }
            )
        if (
            action
            != CommunityAccountEnforcement.Action.INDEFINITE_RESTRICTION
            and confirm_indefinite
        ):
            raise serializers.ValidationError(
                {
                    "confirm_indefinite": (
                        "This confirmation applies only to indefinite restrictions."
                    )
                }
            )
        attrs.pop("confirm_indefinite", None)
        return attrs


class AccountEnforcementReviewRequestSerializer(
    StrictAccountEnforcementSerializer
):
    request_statement = serializers.CharField(
        min_length=20,
        max_length=3000,
        trim_whitespace=True,
    )

    def validate(self, attrs):
        self.validate_supported_fields({"request_statement"})
        return attrs


class AccountEnforcementReviewStartSerializer(
    StrictAccountEnforcementSerializer
):
    reviewer_independence_note = serializers.CharField(
        max_length=3000,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        default="",
    )
    independence_override_rationale = serializers.CharField(
        max_length=3000,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        default="",
    )

    def validate(self, attrs):
        self.validate_supported_fields(
            {
                "reviewer_independence_note",
                "independence_override_rationale",
            }
        )
        return attrs


class AccountEnforcementReviewResolveSerializer(
    StrictAccountEnforcementSerializer
):
    outcome = serializers.ChoiceField(
        choices=CommunityAccountEnforcementReview.Outcome.choices,
    )
    resolution_rationale = serializers.CharField(
        min_length=20,
        max_length=3000,
        trim_whitespace=True,
    )
    internal_note = serializers.CharField(
        max_length=5000,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        default="",
    )

    def validate(self, attrs):
        self.validate_supported_fields(
            {
                "outcome",
                "resolution_rationale",
                "internal_note",
            }
        )
        return attrs


class AccountEnforcementLiftSerializer(StrictAccountEnforcementSerializer):
    rationale = serializers.CharField(
        min_length=20,
        max_length=3000,
        trim_whitespace=True,
    )

    def validate(self, attrs):
        self.validate_supported_fields({"rationale"})
        return attrs


class AccountEnforcementListQuerySerializer(StrictAccountEnforcementSerializer):
    status = serializers.ChoiceField(
        choices=["", "ACTIVE", "PENDING_REVIEW", "WARNING"],
        required=False,
        allow_blank=True,
        default="",
    )
    limit = serializers.IntegerField(
        min_value=1,
        max_value=100,
        required=False,
        default=50,
    )

    def validate(self, attrs):
        self.validate_supported_fields({"status", "limit"})
        return attrs
