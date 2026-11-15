from rest_framework import serializers

from .models import Organization, PartnershipApplication
from .services import check_url_threat_reputation, validate_public_url
from .url_safety import normalize_url_safety_result, url_safety_is_known_threat


def _validate_partnership_public_url(value, *, field_label):
    normalized_url, validation_error = validate_public_url(
        value,
        strip_tracking=False,
    )
    if validation_error:
        raise serializers.ValidationError(validation_error)

    safety_result = check_url_threat_reputation(normalized_url)
    normalized_safety = normalize_url_safety_result(safety_result)

    if url_safety_is_known_threat(safety_result):
        threat_types = normalized_safety.get("threat_types") or []
        threat_suffix = (
            f" ({', '.join(threat_types)})"
            if threat_types
            else ""
        )
        raise serializers.ValidationError(
            f"{field_label} was identified as potentially unsafe"
            f"{threat_suffix} and cannot be submitted. "
            "Remove or replace this link."
        )

    return normalized_url


class PartnershipApplicationCreateSerializer(serializers.Serializer):
    organization_name = serializers.CharField(
        max_length=255,
        allow_blank=False,
        trim_whitespace=True,
    )
    organization_type = serializers.ChoiceField(
        choices=Organization.OrganizationType.choices,
    )
    website = serializers.URLField(
        max_length=2000,
    )
    official_contact_email = serializers.EmailField()
    applicant_full_name = serializers.CharField(
        max_length=255,
        allow_blank=False,
        trim_whitespace=True,
    )
    applicant_position = serializers.CharField(
        max_length=255,
        allow_blank=False,
        trim_whitespace=True,
    )
    applicant_email = serializers.EmailField()
    organization_description = serializers.CharField(
        max_length=4000,
        allow_blank=False,
        trim_whitespace=True,
    )
    partnership_reason = serializers.CharField(
        max_length=4000,
        allow_blank=False,
        trim_whitespace=True,
    )
    supporting_links = serializers.ListField(
        child=serializers.URLField(max_length=2000),
        required=False,
        allow_empty=True,
        max_length=5,
    )
    authorized_to_represent = serializers.BooleanField()
    agrees_to_partner_responsibilities = serializers.BooleanField()

    def validate_website(self, value):
        return _validate_partnership_public_url(
            value,
            field_label="The official website or social media link",
        )

    def validate_supporting_links(self, values):
        validated_links = []
        for index, value in enumerate(values, start=1):
            try:
                validated_links.append(
                    _validate_partnership_public_url(
                        value,
                        field_label=f"Supporting link {index}",
                    )
                )
            except serializers.ValidationError as error:
                detail = error.detail
                if isinstance(detail, list) and detail:
                    message = str(detail[0])
                else:
                    message = str(detail)
                raise serializers.ValidationError(message) from error

        return validated_links

    def validate_organization_description(self, value):
        if len(value.strip()) < 30:
            raise serializers.ValidationError(
                "Provide at least 30 characters describing the organization."
            )
        return value

    def validate_partnership_reason(self, value):
        if len(value.strip()) < 30:
            raise serializers.ValidationError(
                "Provide at least 30 characters explaining the partnership request."
            )
        return value


class PartnershipApplicationOrganizationSerializer(serializers.ModelSerializer):
    organization_type_label = serializers.CharField(
        source="get_organization_type_display",
        read_only=True,
    )
    verification_status_label = serializers.CharField(
        source="get_verification_status_display",
        read_only=True,
    )
    partner_status_label = serializers.CharField(
        source="get_partner_status_display",
        read_only=True,
    )

    class Meta:
        model = Organization
        fields = (
            "id",
            "name",
            "slug",
            "organization_type",
            "organization_type_label",
            "description",
            "website",
            "governance_contact_email",
            "verification_status",
            "verification_status_label",
            "partner_status",
            "partner_status_label",
            "public_profile_enabled",
        )
        read_only_fields = fields


class ManagementPartnershipApplicationSerializer(serializers.ModelSerializer):
    organization = PartnershipApplicationOrganizationSerializer(read_only=True)
    status_label = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    reviewer_username = serializers.CharField(
        source="reviewer.username",
        read_only=True,
        allow_null=True,
    )
    decided_by_username = serializers.CharField(
        source="decided_by.username",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = PartnershipApplication
        fields = (
            "id",
            "organization",
            "applicant_full_name",
            "applicant_position",
            "applicant_email",
            "official_contact_email",
            "organization_description",
            "partnership_reason",
            "supporting_links",
            "authorized_to_represent",
            "agrees_to_partner_responsibilities",
            "status",
            "status_label",
            "reviewer_username",
            "review_started_at",
            "decided_by_username",
            "decided_at",
            "decision_notes",
            "approved_admin_email",
            "onboarding_completed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class PartnershipApplicationApprovalSerializer(serializers.Serializer):
    approved_admin_email = serializers.EmailField()
    decision_notes = serializers.CharField(
        max_length=4000,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )


class PartnershipApplicationRejectionSerializer(serializers.Serializer):
    decision_notes = serializers.CharField(
        max_length=4000,
        allow_blank=False,
        trim_whitespace=True,
    )


class PartnershipApplicationEmptySerializer(serializers.Serializer):
    pass
