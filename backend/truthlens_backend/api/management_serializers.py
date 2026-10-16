from rest_framework import serializers

from .models import (
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
)


def management_role_label(role):
    if role == OrganizationMembership.Role.OWNER:
        return "Primary Admin"

    return dict(OrganizationMembership.Role.choices).get(role, role)


class ManagementOrganizationIdentitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ("id", "name")
        read_only_fields = fields


class ManagementUserIdentitySerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)


class ManagementUserSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)


class ManagementOrganizationListSerializer(serializers.ModelSerializer):
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
            "verification_status",
            "verification_status_label",
            "partner_status",
            "partner_status_label",
            "public_profile_enabled",
            "updated_at",
        )
        read_only_fields = fields


class ManagementPrimaryAdminMembershipSerializer(serializers.ModelSerializer):
    user = ManagementUserIdentitySerializer(read_only=True)
    role_label = serializers.SerializerMethodField()

    def get_role_label(self, obj):
        return management_role_label(obj.role)

    class Meta:
        model = OrganizationMembership
        fields = (
            "id",
            "user",
            "role",
            "role_label",
            "status",
            "joined_at",
            "approved_at",
        )
        read_only_fields = fields


class ManagementPrimaryAdminInvitationSerializer(serializers.ModelSerializer):
    role_label = serializers.SerializerMethodField()

    def get_role_label(self, obj):
        return management_role_label(obj.invited_role)

    class Meta:
        model = OrganizationInvitation
        fields = (
            "id",
            "email",
            "role_label",
            "status",
            "last_sent_at",
            "expires_at",
            "send_count",
        )
        read_only_fields = fields


class ManagementOrganizationDetailSerializer(ManagementOrganizationListSerializer):
    primary_admin = serializers.SerializerMethodField()

    def get_primary_admin(self, obj):
        membership = (
            obj.memberships.select_related("user")
            .filter(role=OrganizationMembership.Role.OWNER)
            .exclude(status=OrganizationMembership.Status.LEFT)
            .first()
        )
        if membership is not None:
            return {
                "state": "CURRENT",
                "membership": ManagementPrimaryAdminMembershipSerializer(
                    membership
                ).data,
                "invitation": None,
            }

        invitation = (
            obj.invitations.filter(
                purpose=(
                    OrganizationInvitation.InvitationPurpose.PRIMARY_ADMIN_ONBOARDING
                ),
                invited_role=OrganizationMembership.Role.OWNER,
                status=OrganizationInvitation.Status.PENDING,
                expires_at__gt=self.context["now"],
            )
            .order_by("-created_at")
            .first()
        )
        if invitation is not None:
            return {
                "state": "PENDING",
                "membership": None,
                "invitation": ManagementPrimaryAdminInvitationSerializer(
                    invitation
                ).data,
            }

        return {"state": "NONE", "membership": None, "invitation": None}

    class Meta(ManagementOrganizationListSerializer.Meta):
        fields = ManagementOrganizationListSerializer.Meta.fields + (
            "description",
            "website",
            "logo_url",
            "expertise_areas",
            "public_logo_enabled",
            "primary_admin",
            "created_at",
        )
        read_only_fields = fields


class ManagementMembershipSerializer(serializers.ModelSerializer):
    organization = ManagementOrganizationIdentitySerializer(read_only=True)
    user = ManagementUserIdentitySerializer(read_only=True)
    role_label = serializers.SerializerMethodField()
    approved_by = ManagementUserSummarySerializer(read_only=True)

    def get_role_label(self, obj):
        return management_role_label(obj.role)

    class Meta:
        model = OrganizationMembership
        fields = (
            "id",
            "organization",
            "user",
            "role",
            "role_label",
            "status",
            "joined_at",
            "approved_at",
            "approved_by",
        )
        read_only_fields = fields


class ManagementInvitationSerializer(serializers.ModelSerializer):
    organization = ManagementOrganizationIdentitySerializer(read_only=True)
    invited_role_label = serializers.SerializerMethodField()
    purpose_label = serializers.CharField(
        source="get_purpose_display",
        read_only=True,
    )
    invited_by = ManagementUserSummarySerializer(read_only=True)
    accepted_by = ManagementUserSummarySerializer(read_only=True)
    cancelled_by = ManagementUserSummarySerializer(read_only=True)

    def get_invited_role_label(self, obj):
        return management_role_label(obj.invited_role)

    class Meta:
        model = OrganizationInvitation
        fields = (
            "id",
            "organization",
            "email",
            "invited_role",
            "invited_role_label",
            "purpose",
            "purpose_label",
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
        )
        read_only_fields = fields
