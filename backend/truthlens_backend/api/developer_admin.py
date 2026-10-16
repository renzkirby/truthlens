from django import forms
from django.contrib import admin, messages
from django.http import Http404, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone

from .models import (
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
)
from .organization_provisioning_service import (
    OrganizationProvisioningError,
    create_and_send_primary_admin_invitation,
    resend_primary_admin_invitation,
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


class PrimaryAdminProvisionForm(forms.Form):
    email = forms.EmailField(
        label="Primary Admin Email",
        max_length=254,
        help_text=(
            "The recipient must sign in or create their own TruthLens account "
            "with this verified email address."
        ),
    )


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
    change_form_template = (
        "admin/developer_console/organization_change_form.html"
    )
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

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/primary-admin/provision/",
                self.admin_site.admin_view(
                    self.provision_primary_admin_view,
                ),
                name="api_organization_primary_admin_provision",
            ),
            path(
                "<path:object_id>/primary-admin/resend/",
                self.admin_site.admin_view(
                    self.resend_primary_admin_view,
                ),
                name="api_organization_primary_admin_resend",
            ),
        ]

        return custom_urls + super().get_urls()

    def _get_organization(self, request, object_id):
        organization = self.get_object(request, object_id)

        if organization is None:
            raise Http404("Organization not found.")

        return organization

    def _change_url(self, organization):
        return reverse(
            f"{self.admin_site.name}:api_organization_change",
            args=(organization.pk,),
        )

    def _primary_admin_context(self, organization):
        current_owner = (
            OrganizationMembership.objects.select_related("user")
            .filter(
                organization=organization,
                role=OrganizationMembership.Role.OWNER,
            )
            .exclude(
                status=OrganizationMembership.Status.LEFT,
            )
            .first()
        )

        pending_invitation = None

        if current_owner is None:
            pending_invitation = (
                OrganizationInvitation.objects.filter(
                    organization=organization,
                    purpose=(
                        OrganizationInvitation.InvitationPurpose.PRIMARY_ADMIN_ONBOARDING
                    ),
                    status=OrganizationInvitation.Status.PENDING,
                    expires_at__gt=timezone.now(),
                )
                .order_by("-created_at", "-id")
                .first()
            )

        return {
            "current_owner": current_owner,
            "pending_invitation": pending_invitation,
            "provision_url": reverse(
                (
                    f"{self.admin_site.name}:"
                    "api_organization_primary_admin_provision"
                ),
                args=(organization.pk,),
            ),
            "resend_url": reverse(
                (
                    f"{self.admin_site.name}:"
                    "api_organization_primary_admin_resend"
                ),
                args=(organization.pk,),
            ),
        }

    def change_view(
        self,
        request,
        object_id,
        form_url="",
        extra_context=None,
    ):
        organization = self._get_organization(
            request,
            object_id,
        )
        context = dict(extra_context or {})
        context["primary_admin_state"] = self._primary_admin_context(
            organization,
        )

        return super().change_view(
            request,
            object_id,
            form_url,
            context,
        )

    def _provisioning_view_context(
        self,
        *,
        request,
        organization,
        title,
        **extra_context,
    ):
        request.current_app = self.admin_site.name
        return {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "original": organization,
            "organization": organization,
            "title": title,
            "change_url": self._change_url(organization),
            **extra_context,
        }

    def provision_primary_admin_view(
        self,
        request,
        object_id,
    ):
        organization = self._get_organization(
            request,
            object_id,
        )
        form = PrimaryAdminProvisionForm(
            request.POST or None,
        )

        if request.method == "POST" and form.is_valid():
            try:
                invitation = create_and_send_primary_admin_invitation(
                    organization=organization,
                    email=form.cleaned_data["email"],
                    actor=request.user,
                )
            except OrganizationProvisioningError as error:
                form.add_error(None, str(error))
            else:
                self.message_user(
                    request,
                    (
                        "Primary Admin invitation sent to "
                        f"{invitation.email}."
                    ),
                    level=messages.SUCCESS,
                )

                return HttpResponseRedirect(
                    self._change_url(organization),
                )

        context = self._provisioning_view_context(
            request=request,
            organization=organization,
            title="Provision Primary Admin",
            form=form,
        )

        return TemplateResponse(
            request,
            "admin/developer_console/primary_admin_provision.html",
            context,
        )

    def resend_primary_admin_view(
        self,
        request,
        object_id,
    ):
        organization = self._get_organization(
            request,
            object_id,
        )
        invitation = (
            OrganizationInvitation.objects.filter(
                organization=organization,
                purpose=(
                    OrganizationInvitation.InvitationPurpose.PRIMARY_ADMIN_ONBOARDING
                ),
                status=OrganizationInvitation.Status.PENDING,
                expires_at__gt=timezone.now(),
            )
            .order_by("-created_at", "-id")
            .first()
        )

        if invitation is None:
            self.message_user(
                request,
                (
                    "There is no active Primary Admin invitation to resend. "
                    "Issue a replacement invitation if the previous one expired."
                ),
                level=messages.WARNING,
            )

            return HttpResponseRedirect(
                self._change_url(organization),
            )

        error_message = ""

        if request.method == "POST":
            try:
                invitation = resend_primary_admin_invitation(
                    invitation=invitation,
                    actor=request.user,
                )
            except OrganizationProvisioningError as error:
                error_message = str(error)
            else:
                self.message_user(
                    request,
                    (
                        "A new Primary Admin invitation link was sent to "
                        f"{invitation.email}."
                    ),
                    level=messages.SUCCESS,
                )

                return HttpResponseRedirect(
                    self._change_url(organization),
                )

        context = self._provisioning_view_context(
            request=request,
            organization=organization,
            title="Resend Primary Admin Invitation",
            invitation=invitation,
            error_message=error_message,
        )

        return TemplateResponse(
            request,
            "admin/developer_console/primary_admin_resend.html",
            context,
        )


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
        "purpose",
        "status",
        "invited_by",
        "expires_at",
        "created_at",
    )
    list_filter = (
        "organization",
        "status",
        "purpose",
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
        "purpose",
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
