from rest_framework import serializers

from .accountability_query_service import MANAGEMENT_GOVERNANCE_ACTIONS
from .organization_partnership_lifecycle_service import (
    get_partner_organization_lifecycle_projection,
)
from .models import (
    AccountabilityEvent,
    ClaimInvestigationClassification,
    ClaimInstitutionAssociation,
    Institution,
    Organization,
    OrganizationInstitutionAffiliation,
    OrganizationInvitation,
    OrganizationMembership,
    PlatformStaffInvitation,
    Claim,
    VerificationRun,
)


class StrictFieldsSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            unexpected_fields = sorted(set(data.keys()) - set(self.fields))
            if unexpected_fields:
                raise serializers.ValidationError(
                    {
                        field: "This field is not supported."
                        for field in unexpected_fields
                    }
                )

        return super().to_internal_value(data)


class ManagementOrganizationCreateSerializer(StrictFieldsSerializer):
    name = serializers.CharField(max_length=255, allow_blank=False, trim_whitespace=True)
    slug = serializers.SlugField(max_length=255, allow_blank=False)
    organization_type = serializers.ChoiceField(
        choices=Organization.OrganizationType.choices
    )
    # Backward-compatible rollout: the currently deployed frontend still sends
    # these safe defaults. The governance service rejects any non-default trust
    # value, so old clients remain compatible without regaining trust authority.
    verification_status = serializers.ChoiceField(
        choices=Organization.VerificationStatus.choices,
        default=Organization.VerificationStatus.UNVERIFIED,
    )
    partner_status = serializers.ChoiceField(
        choices=Organization.PartnerStatus.choices,
        default=Organization.PartnerStatus.NONE,
    )


class ManagementInstitutionCreateSerializer(StrictFieldsSerializer):
    name = serializers.CharField(max_length=255, allow_blank=False, trim_whitespace=True)
    slug = serializers.SlugField(max_length=255, allow_blank=False)
    website = serializers.URLField(
        max_length=2000,
        required=False,
        allow_blank=True,
        allow_null=True,
    )


class ManagementInstitutionAffiliationUpdateSerializer(StrictFieldsSerializer):
    institution_id = serializers.UUIDField()
    verification_status = serializers.ChoiceField(
        choices=OrganizationInstitutionAffiliation.VerificationStatus.choices,
    )
    rationale = serializers.CharField(
        max_length=2000,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        default="",
    )


class ManagementPlatformTrustUpdateSerializer(StrictFieldsSerializer):
    verification_status = serializers.ChoiceField(
        choices=Organization.VerificationStatus.choices,
        required=False,
    )
    partner_status = serializers.ChoiceField(
        choices=Organization.PartnerStatus.choices,
        required=False,
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError(
                "Supply verification_status, partner_status, or both."
            )
        return attrs


class ManagementOrganizationAdminProvisionSerializer(StrictFieldsSerializer):
    email = serializers.EmailField()


# Backward-compatible serializer alias for already-deployed clients/tests.
ManagementPrimaryAdminProvisionSerializer = ManagementOrganizationAdminProvisionSerializer


class ManagementEmptyMutationSerializer(StrictFieldsSerializer):
    pass


class ManagementGovernanceAuditQuerySerializer(StrictFieldsSerializer):
    action_type = serializers.ChoiceField(
        choices=[
            (value, dict(AccountabilityEvent.ActionType.choices)[value])
            for value in MANAGEMENT_GOVERNANCE_ACTIONS
        ],
        required=False,
        allow_blank=True,
    )
    organization = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        max_length=255,
    )
    actor = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        max_length=150,
    )
    created_after = serializers.DateTimeField(required=False, allow_null=True)
    created_before = serializers.DateTimeField(required=False, allow_null=True)
    limit = serializers.IntegerField(default=25, min_value=1, max_value=100)
    offset = serializers.IntegerField(default=0, min_value=0)

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


class ManagementGovernanceAuditDetailQuerySerializer(StrictFieldsSerializer):
    pass


class ManagementPipelineOverviewQuerySerializer(StrictFieldsSerializer):
    window = serializers.ChoiceField(
        choices=("24h", "7d", "30d"),
        default="7d",
    )


class ManagementPipelineRunListQuerySerializer(StrictFieldsSerializer):
    window = serializers.ChoiceField(
        choices=("24h", "7d", "30d"),
        default="7d",
    )
    status = serializers.ChoiceField(
        choices=VerificationRun.Status.choices,
        required=False,
        allow_blank=True,
    )
    claim_type = serializers.ChoiceField(
        choices=Claim.ClaimType.choices,
        required=False,
        allow_blank=True,
    )
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100)


class ManagementPipelineRunDetailQuerySerializer(StrictFieldsSerializer):
    pass


def management_role_label(role):
    legacy_labels = {
        "OWNER": "Administrator",
        "MODERATOR": "Verification Reviewer",
        "CONTRIBUTOR": "Former Contributor",
    }
    return dict(OrganizationMembership.Role.choices).get(
        role,
        legacy_labels.get(role, role),
    )


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


class ManagementPlatformStaffSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    platform_role = serializers.SerializerMethodField()
    platform_role_label = serializers.SerializerMethodField()
    access_label = serializers.SerializerMethodField()
    can_revoke = serializers.SerializerMethodField()

    def get_platform_role(self, obj):
        return (
            "PLATFORM_ADMIN"
            if obj.is_superuser
            else "PLATFORM_SAFETY_MODERATOR"
        )

    def get_platform_role_label(self, obj):
        return (
            "Platform Admin"
            if obj.is_superuser
            else "Platform Safety Moderator"
        )

    def get_access_label(self, obj):
        return (
            "Full Management Console"
            if obj.is_superuser
            else "Safety Review and Safety Audit"
        )

    def get_can_revoke(self, obj):
        return not obj.is_superuser


class ManagementPlatformStaffInvitationCreateSerializer(StrictFieldsSerializer):
    email = serializers.EmailField()


class ManagementPlatformStaffInvitationSerializer(serializers.ModelSerializer):
    invited_by = ManagementUserSummarySerializer(read_only=True)
    accepted_by = ManagementUserSummarySerializer(read_only=True)
    cancelled_by = ManagementUserSummarySerializer(read_only=True)
    platform_role_label = serializers.CharField(
        source="get_platform_role_display",
        read_only=True,
    )

    class Meta:
        model = PlatformStaffInvitation
        fields = (
            "id",
            "email",
            "platform_role",
            "platform_role_label",
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


class ManagementPlatformStaffInvitationPublicSerializer(serializers.ModelSerializer):
    invited_by = ManagementUserSummarySerializer(read_only=True)
    platform_role_label = serializers.CharField(
        source="get_platform_role_display",
        read_only=True,
    )
    recipient_matches_current_user = serializers.SerializerMethodField()

    def get_recipient_matches_current_user(self, obj):
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        if not actor or not actor.is_authenticated:
            return None
        actor_email = str(actor.email or "").strip().casefold()
        invited_email = str(obj.email or "").strip().casefold()
        return bool(actor_email and actor_email == invited_email)

    class Meta:
        model = PlatformStaffInvitation
        fields = (
            "platform_role",
            "platform_role_label",
            "recipient_matches_current_user",
            "status",
            "expires_at",
            "invited_by",
        )
        read_only_fields = fields


class ManagementClaimInstitutionAssociationInputSerializer(StrictFieldsSerializer):
    institution_id = serializers.UUIDField()
    rationale = serializers.CharField(
        max_length=2000,
        allow_blank=False,
        trim_whitespace=True,
    )


class ManagementClaimInstitutionContextUpdateSerializer(StrictFieldsSerializer):
    campus_context_state = serializers.ChoiceField(
        choices=ClaimInvestigationClassification.CampusContextState.choices,
        allow_null=True,
    )
    campus_context_rationale = serializers.CharField(
        max_length=2000,
        allow_blank=True,
        trim_whitespace=True,
        default="",
    )
    institutions = ManagementClaimInstitutionAssociationInputSerializer(
        many=True,
        default=list,
    )

    def validate(self, attrs):
        state = attrs.get("campus_context_state")
        campus_context_rationale = str(
            attrs.get("campus_context_rationale") or ""
        ).strip()
        institutions = attrs.get("institutions", [])

        if state is None:
            if campus_context_rationale:
                raise serializers.ValidationError(
                    {"campus_context_rationale": "Unassessed campus context cannot have a rationale."}
                )
        elif not campus_context_rationale:
            raise serializers.ValidationError(
                {"campus_context_rationale": "Campus context rationale is required."}
            )

        if (
            state
            != ClaimInvestigationClassification.CampusContextState.CONFIRMED
            and institutions
        ):
            raise serializers.ValidationError(
                {
                    "institutions": (
                        "Institution associations require confirmed campus context."
                    )
                }
            )

        institution_ids = [
            str(entry["institution_id"])
            for entry in institutions
        ]
        if len(institution_ids) != len(set(institution_ids)):
            raise serializers.ValidationError(
                {"institutions": "Duplicate institution IDs are not allowed."}
            )

        return attrs


class ManagementInstitutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Institution
        fields = (
            "id",
            "name",
            "slug",
            "website",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ManagementClaimInstitutionAssociationSerializer(serializers.ModelSerializer):
    institution = ManagementInstitutionSerializer(read_only=True)
    assigned_by = ManagementUserSummarySerializer(read_only=True)

    class Meta:
        model = ClaimInstitutionAssociation
        fields = (
            "id",
            "institution",
            "rationale",
            "assigned_by",
            "assigned_at",
            "updated_at",
        )
        read_only_fields = fields


class ManagementClaimInstitutionContextSerializer(serializers.ModelSerializer):
    claim_id = serializers.UUIDField(read_only=True)
    campus_context_state_label = serializers.SerializerMethodField()
    campus_context_reviewed_by = ManagementUserSummarySerializer(read_only=True)
    institutions = serializers.SerializerMethodField()

    def get_campus_context_state_label(self, obj):
        if obj.campus_context_state is None:
            return None
        return obj.get_campus_context_state_display()

    def get_institutions(self, obj):
        associations = obj.institution_associations.select_related(
            "institution",
            "assigned_by",
        ).order_by("institution__name", "institution_id")
        return ManagementClaimInstitutionAssociationSerializer(
            associations,
            many=True,
        ).data

    class Meta:
        model = ClaimInvestigationClassification
        fields = (
            "claim_id",
            "campus_context_state",
            "campus_context_state_label",
            "campus_context_rationale",
            "campus_context_reviewed_by",
            "campus_context_reviewed_at",
            "institutions",
        )
        read_only_fields = fields


class ManagementOrganizationInstitutionAffiliationSerializer(serializers.ModelSerializer):
    institution = ManagementInstitutionSerializer(read_only=True)
    reviewed_by = ManagementUserSummarySerializer(read_only=True)
    coverage_scope_label = serializers.CharField(
        source="get_coverage_scope_display",
        read_only=True,
    )
    verification_status_label = serializers.CharField(
        source="get_verification_status_display",
        read_only=True,
    )

    class Meta:
        model = OrganizationInstitutionAffiliation
        fields = (
            "id",
            "institution",
            "coverage_scope",
            "coverage_scope_label",
            "verification_status",
            "verification_status_label",
            "rationale",
            "reviewed_by",
            "reviewed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ManagementOrganizationListSerializer(serializers.ModelSerializer):
    organization_type_label = serializers.CharField(
        source="get_organization_type_display",
        read_only=True,
    )
    organization_subtype_label = serializers.CharField(
        source="get_organization_subtype_display",
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
            "organization_subtype",
            "organization_subtype_label",
            "verification_status",
            "verification_status_label",
            "partner_status",
            "partner_status_label",
            "public_profile_enabled",
            "updated_at",
        )
        read_only_fields = fields


class ManagementOrganizationAdminMembershipSerializer(serializers.ModelSerializer):
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


class ManagementOrganizationAdminInvitationSerializer(serializers.ModelSerializer):
    role_label = serializers.SerializerMethodField()

    def get_role_label(self, obj):
        if (
            obj.purpose
            in {
                OrganizationInvitation.InvitationPurpose.ORGANIZATION_ADMIN_ONBOARDING,
                "PRIMARY_ADMIN_ONBOARDING",
            }
            and obj.invited_role in {OrganizationMembership.Role.ADMIN, "OWNER"}
        ):
            return "Organization Admin"
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
    lifecycle = serializers.SerializerMethodField()
    institution_affiliation = serializers.SerializerMethodField()
    verification_specializations = serializers.ListField(
        child=serializers.CharField(), read_only=True
    )
    approved_verification_domains = serializers.ListField(
        child=serializers.CharField(), read_only=True
    )
    approved_verification_jurisdictions = serializers.ListField(
        child=serializers.CharField(), read_only=True
    )
    organization_admin = serializers.SerializerMethodField()
    # Temporary response alias for clients deployed before the role-model cleanup.
    primary_admin = serializers.SerializerMethodField()

    def get_lifecycle(self, obj):
        return get_partner_organization_lifecycle_projection(obj)

    def get_organization_admin(self, obj):
        current_admins = (
            obj.memberships.select_related("user")
            .filter(role=OrganizationMembership.Role.ADMIN)
            .exclude(status=OrganizationMembership.Status.LEFT)
        )
        membership = current_admins.first()
        if membership is not None:
            return {
                "state": "CURRENT",
                "current_count": current_admins.count(),
                "membership": ManagementOrganizationAdminMembershipSerializer(
                    membership
                ).data,
                "invitation": None,
            }

        invitation = (
            obj.invitations.filter(
                purpose=(
                    OrganizationInvitation.InvitationPurpose.ORGANIZATION_ADMIN_ONBOARDING
                ),
                invited_role=OrganizationMembership.Role.ADMIN,
                status=OrganizationInvitation.Status.PENDING,
                expires_at__gt=self.context["now"],
            )
            .order_by("-created_at")
            .first()
        )
        if invitation is not None:
            return {
                "state": "PENDING",
                "current_count": 0,
                "membership": None,
                "invitation": ManagementOrganizationAdminInvitationSerializer(
                    invitation
                ).data,
            }

        return {
            "state": "NONE",
            "current_count": 0,
            "membership": None,
            "invitation": None,
        }

    def get_primary_admin(self, obj):
        return self.get_organization_admin(obj)

    def get_institution_affiliation(self, obj):
        try:
            affiliation = obj.institution_affiliation
        except OrganizationInstitutionAffiliation.DoesNotExist:
            return None
        return ManagementOrganizationInstitutionAffiliationSerializer(
            affiliation
        ).data

    class Meta(ManagementOrganizationListSerializer.Meta):
        fields = ManagementOrganizationListSerializer.Meta.fields + (
            "description",
            "website",
            "logo_url",
            "expertise_areas",
            "verification_specializations",
            "approved_verification_domains",
            "approved_verification_jurisdictions",
            "requested_verification_domains",
            "requested_verification_jurisdictions",
            "active_verification_domains",
            "active_verification_jurisdictions",
            "active_scope_configured",
            "public_logo_enabled",
            "institution_affiliation",
            "organization_admin",
            "primary_admin",
            "lifecycle",
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


# Backward-compatible class aliases; current product terminology is Organization Admin.
ManagementPrimaryAdminMembershipSerializer = ManagementOrganizationAdminMembershipSerializer
ManagementPrimaryAdminInvitationSerializer = ManagementOrganizationAdminInvitationSerializer
