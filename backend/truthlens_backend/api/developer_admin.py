from django.contrib import admin

from .models import (
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
)


def _organization_role_label(role):
    if role == OrganizationMembership.Role.OWNER:
        return "Primary Admin"

    return dict(OrganizationMembership.Role.choices).get(role, role)


class DeveloperAdminSite(admin.AdminSite):
    site_header = "TruthLens Developer Console"
    site_title = "TruthLens Developer Console"
    index_title = "Partner Organization Governance"
    site_url = None

    def has_permission(self, request):
        user = request.user

        return bool(
            user.is_authenticated
            and user.is_active
            and user.is_superuser
        )


developer_admin_site = DeveloperAdminSite(name="developer_admin")


class MembershipRoleFilter(admin.SimpleListFilter):
    title = "role"
    parameter_name = "role"

    def lookups(self, request, model_admin):
        return [
            (value, _organization_role_label(value))
            for value, _label in OrganizationMembership.Role.choices
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(role=self.value())

        return queryset


class InvitationRoleFilter(MembershipRoleFilter):
    title = "invited role"
    parameter_name = "invited_role"

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(invited_role=self.value())

        return queryset


class ReadOnlyInspectionAdmin(admin.ModelAdmin):
    change_form_template = (
        "admin/developer_console/read_only_change_form.html"
    )

    def get_inspection_label(self, obj):
        return str(obj)

    def change_view(
        self,
        request,
        object_id,
        form_url="",
        extra_context=None,
    ):
        obj = self.get_object(request, object_id)
        context = dict(extra_context or {})

        if obj is not None:
            context["subtitle"] = self.get_inspection_label(obj)

        return super().change_view(
            request,
            object_id,
            form_url,
            context,
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Organization, site=developer_admin_site)
class DeveloperOrganizationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "organization_type",
        "verification_status",
        "partner_status",
        "public_profile_enabled",
        "updated_at",
    )
    list_filter = (
        "verification_status",
        "partner_status",
        "organization_type",
        "public_profile_enabled",
    )
    search_fields = (
        "name",
        "slug",
    )
    fields = (
        "name",
        "slug",
        "organization_type",
        "verification_status",
        "partner_status",
        "description",
        "website",
        "logo_url",
        "expertise_areas",
        "public_profile_enabled",
        "public_logo_enabled",
        "created_at",
        "updated_at",
    )
    readonly_fields = (
        "description",
        "website",
        "logo_url",
        "expertise_areas",
        "public_profile_enabled",
        "public_logo_enabled",
        "created_at",
        "updated_at",
    )

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))

        if obj is not None:
            readonly_fields.extend(
                (
                    "name",
                    "slug",
                    "organization_type",
                )
            )

        return tuple(readonly_fields)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OrganizationMembership, site=developer_admin_site)
class DeveloperOrganizationMembershipAdmin(ReadOnlyInspectionAdmin):
    list_display = (
        "organization",
        "user",
        "role_label",
        "status",
        "joined_at",
        "approved_at",
    )
    list_filter = (
        "organization",
        MembershipRoleFilter,
        "status",
    )
    search_fields = (
        "organization__name",
        "user__username",
        "user__email",
    )
    fields = (
        "id",
        "organization",
        "user",
        "role_label",
        "status",
        "joined_at",
        "approved_at",
        "approved_by",
    )
    readonly_fields = fields

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "organization",
            "user",
            "approved_by",
        )

    @admin.display(description="Role", ordering="role")
    def role_label(self, obj):
        return _organization_role_label(obj.role)

    def get_inspection_label(self, obj):
        return (
            f"{obj.user.username} - {obj.organization.name} "
            f"({_organization_role_label(obj.role)})"
        )


@admin.register(OrganizationInvitation, site=developer_admin_site)
class DeveloperOrganizationInvitationAdmin(ReadOnlyInspectionAdmin):
    list_display = (
        "organization",
        "email",
        "invited_role_label",
        "status",
        "invited_by",
        "expires_at",
        "created_at",
    )
    list_filter = (
        "organization",
        "status",
        InvitationRoleFilter,
    )
    search_fields = (
        "organization__name",
        "email",
        "invited_by__username",
        "invited_by__email",
    )
    fields = (
        "id",
        "organization",
        "email",
        "invited_role_label",
        "status",
        "invited_by",
        "token_digest",
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
    readonly_fields = fields

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "organization",
            "invited_by",
            "accepted_by",
            "cancelled_by",
        )

    @admin.display(description="Invited role", ordering="invited_role")
    def invited_role_label(self, obj):
        return _organization_role_label(obj.invited_role)

    def get_inspection_label(self, obj):
        return (
            f"{obj.email} → {obj.organization.name} "
            f"({_organization_role_label(obj.invited_role)})"
        )
