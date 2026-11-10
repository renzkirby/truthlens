from rest_framework import serializers

from .models import OrganizationGovernanceReconsideration
from .organization_governance_reconsideration_service import (
    RECONSIDERATION_GROUND_CHOICES,
)


class StrictReconsiderationSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            unexpected = sorted(set(data.keys()) - set(self.fields))
            if unexpected:
                raise serializers.ValidationError(
                    {field: "This field is not supported." for field in unexpected}
                )
        return super().to_internal_value(data)


class GovernanceReconsiderationSubmitSerializer(StrictReconsiderationSerializer):
    grounds = serializers.ListField(
        child=serializers.ChoiceField(choices=RECONSIDERATION_GROUND_CHOICES),
        allow_empty=False,
        max_length=4,
    )
    request_statement = serializers.CharField(
        min_length=20,
        max_length=5000,
        allow_blank=False,
        trim_whitespace=True,
    )
    supporting_references = serializers.ListField(
        child=serializers.CharField(
            max_length=500,
            allow_blank=False,
            trim_whitespace=True,
        ),
        required=False,
        allow_empty=True,
        max_length=10,
        default=list,
    )

    def validate_grounds(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Select each ground only once.")
        return value


class ManagementReconsiderationReviewStartSerializer(
    StrictReconsiderationSerializer
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


class ManagementReconsiderationResolveSerializer(StrictReconsiderationSerializer):
    outcome = serializers.ChoiceField(
        choices=OrganizationGovernanceReconsideration.Outcome.choices,
    )
    resolution_rationale = serializers.CharField(
        min_length=20,
        max_length=5000,
        allow_blank=False,
        trim_whitespace=True,
    )
    internal_supporting_basis = serializers.CharField(
        min_length=20,
        max_length=6000,
        allow_blank=False,
        trim_whitespace=True,
    )
