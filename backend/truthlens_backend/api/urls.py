from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework.routers import DefaultRouter
from . import views

urlpatterns = [
    path("analyze/", views.receive_snippet, name="analyze_snippet"),
    path("claims/<claim_id>/status", views.claim_polling_endpoint, name="claim_status"),
    path("verify-url/", views.verify_url, name="verify_url"),
    path("test-deepfake/", views.test_deepfake, name="test_deepfake"),
    path("verify-text/", views.verify_text, name="verify_text"),
    path("claims/match/", views.claim_match, name="claim_match"),
    path(
        "claims/<uuid:claim_id>/analysis/",
        views.get_claim_analysis,
        name="claim_analysis",
    ),
    path("verify-file/", views.verify_file, name="verify_file"),
    # Auth urls
    path("auth/login/", views.login_user),
    path("auth/refresh/", TokenRefreshView.as_view()),
    path("auth/register/", views.register_user),
    path("auth/me/", views.get_current_user, name="auth_me"),
    path("auth/profile/update/", views.update_profile),
    path("auth/guest-scan-sync/", views.sync_guest_scan),
    path("users/search/", views.search_users),
    path("users/<str:username>/", views.get_public_user_profile),
    path("users/<str:username>/threads/", views.public_user_threads),
    path("users/<str:username>/evidence/", views.public_user_evidence),
    path("users/<str:username>/follow/", views.toggle_follow_user),
    path("users/<str:username>/followers/", views.get_user_followers),
    path("users/<str:username>/following/", views.get_user_following),
    path("users/<str:username>/claims/", views.public_user_claims),
    path("partners/", views.public_partner_directory, name="public_partner_directory"),
    path(
        "partners/<slug:slug>/fact-checks/",
        views.public_partner_fact_checks,
        name="public_partner_fact_checks",
    ),
    path(
        "partners/<slug:slug>/fact-checks/<uuid:publication_id>/",
        views.public_partner_fact_check_detail,
        name="public_partner_fact_check_detail",
    ),
    path(
        "partners/<slug:slug>/",
        views.public_partner_detail,
        name="public_partner_detail",
    ),
    path("auth/my-claims/", views.my_claims),
    path("auth/send-verification/", views.send_verification_email),
    path("auth/verify-email/", views.verify_email),
    path("auth/password-reset/", views.request_password_reset, name="password_reset"),
    path(
        "auth/password-reset/confirm/",
        views.confirm_password_reset,
        name="password_reset_confirm",
    ),
    path(
        "auth/onboarding/complete/",
        views.complete_onboarding,
        name="complete_onboarding",
    ),
    # DashBoard URLs
    path("users/me/dashboard/", views.UserHubView.as_view(), name="user_hub"),
    path(
        "users/me/fact-checks/",
        views.UserFactCheckLibraryView.as_view(),
        name="user_fact_check_library",
    ),
    path(
        "claims/<uuid:claim_id>/toggle-save/",
        views.toggle_save_claim,
        name="toggle_save_claim",
    ),
    path(
        "accountability/organization/",
        views.organization_accountability,
        name="organization_accountability",
    ),
    path(
        "accountability/platform-safety/",
        views.platform_safety_accountability,
        name="platform_safety_accountability",
    ),
    path(
        "moderation/safety/cases/",
        views.safety_case_queue,
        name="safety_case_queue",
    ),
    path(
        "moderation/safety/cases/<uuid:case_id>/",
        views.safety_case_detail,
        name="safety_case_detail",
    ),
    path(
        "moderation/safety/cases/<uuid:case_id>/claim/",
        views.safety_case_claim,
        name="safety_case_claim",
    ),
    path(
        "moderation/safety/cases/<uuid:case_id>/release/",
        views.safety_case_release,
        name="safety_case_release",
    ),
    path(
        "moderation/safety/cases/<uuid:case_id>/action/",
        views.safety_case_action,
        name="safety_case_action",
    ),
    path(
        "moderation/evidence/cases/",
        views.evidence_case_queue,
        name="evidence_case_queue",
    ),
    path(
        "moderation/evidence/cases/<uuid:case_id>/",
        views.evidence_case_detail,
        name="evidence_case_detail",
    ),
    path(
        "moderation/evidence/cases/<uuid:case_id>/action/",
        views.evidence_case_action,
        name="evidence_case_action",
    ),
    path(
        "moderation/adjudication/cases/",
        views.adjudication_case_queue,
        name="adjudication_case_queue",
    ),
    path(
        "moderation/adjudication/cases/<uuid:case_id>/",
        views.adjudication_case_detail,
        name="adjudication_case_detail",
    ),
    path(
        "moderation/adjudication/cases/<uuid:case_id>/action/",
        views.adjudication_case_action,
        name="adjudication_case_action",
    ),
    # Partner verification intake
    path(
        "verification/intake/",
        views.verification_intake,
        name="verification_intake",
    ),
    path(
        ("verification/assignments/<uuid:assignment_id>/claim/"),
        views.verification_assignment_claim,
        name="verification_assignment_claim",
    ),
    path(
        ("verification/assignments/<uuid:assignment_id>/release/"),
        views.verification_assignment_release,
        name="verification_assignment_release",
    ),
    path(
        "verification/workload/",
        views.verification_workload,
        name="verification_workload",
    ),
    path(
        "organizations/<uuid:organization_id>/analytics/verification/",
        views.organization_verification_metrics,
        name="organization_verification_metrics",
    ),
    path(
        "organizations/" "<uuid:organization_id>/" "public-profile/",
        views.organization_public_profile,
        name="organization_public_profile",
    ),
    path(
        "organizations/" "<uuid:organization_id>/" "public-profile/logo/",
        views.organization_public_profile_logo,
        name="organization_public_profile_logo",
    ),
    path(
        "organizations/" "<uuid:organization_id>/members/",
        views.organization_members,
        name="organization_members",
    ),
    path(
        (
            "organizations/"
            "<uuid:organization_id>/"
            "members/"
            "<uuid:membership_id>/"
            "role/"
        ),
        views.organization_membership_role_update,
        name="organization_membership_role_update",
    ),
    path(
        (
            "organizations/"
            "<uuid:organization_id>/"
            "members/"
            "<uuid:membership_id>/"
            "suspend/"
        ),
        views.organization_membership_suspend,
        name="organization_membership_suspend",
    ),
    path(
        (
            "organizations/"
            "<uuid:organization_id>/"
            "members/"
            "<uuid:membership_id>/"
            "restore/"
        ),
        views.organization_membership_restore,
        name="organization_membership_restore",
    ),
    path(
        (
            "organizations/"
            "<uuid:organization_id>/"
            "members/"
            "<uuid:membership_id>/"
            "remove/"
        ),
        views.organization_membership_remove,
        name="organization_membership_remove",
    ),
    path(
        ("organizations/" "<uuid:organization_id>/" "invitations/"),
        views.organization_invitations,
        name="organization_invitations",
    ),
    path(
        (
            "organizations/"
            "<uuid:organization_id>/"
            "invitations/"
            "<uuid:invitation_id>/"
            "resend/"
        ),
        views.organization_invitation_resend,
        name="organization_invitation_resend",
    ),
    path(
        (
            "organizations/"
            "<uuid:organization_id>/"
            "invitations/"
            "<uuid:invitation_id>/"
            "cancel/"
        ),
        views.organization_invitation_cancel,
        name="organization_invitation_cancel",
    ),
    path(
        "moderation/claims/" "<uuid:claim_id>/" "fact-checks/draft/",
        views.fact_check_draft_create,
        name=("moderation_fact_check_" "draft_create"),
    ),
    path(
        "moderation/publications/work-items/",
        views.publication_work_item_queue,
        name="publication_work_item_queue",
    ),
    path(
        (
            "moderation/publications/work-items/"
            "<str:resource_type>/<uuid:resource_id>/"
        ),
        views.publication_work_item_detail,
        name="publication_work_item_detail",
    ),
    path(
        "moderation/publications/library/",
        views.organization_publication_library,
        name="organization_publication_library",
    ),
    path(
        "moderation/publications/library/<uuid:fact_check_id>/",
        views.organization_publication_detail,
        name="organization_publication_detail",
    ),
    path(
        "moderation/publications/factual-corrections/",
        views.factual_correction_collection,
        name="factual_correction_collection",
    ),
    path(
        "moderation/publications/factual-corrections/<uuid:request_id>/",
        views.factual_correction_detail,
        name="factual_correction_detail",
    ),
    path(
        (
            "moderation/publications/<uuid:predecessor_id>/"
            "factual-corrections/request/"
        ),
        views.factual_correction_request_create,
        name="factual_correction_request_create",
    ),
    path(
        (
            "moderation/publications/factual-corrections/"
            "<uuid:request_id>/evidence/<uuid:evidence_id>/review/"
        ),
        views.factual_correction_evidence_review,
        name="factual_correction_evidence_review",
    ),
    path(
        (
            "moderation/publications/factual-corrections/"
            "<uuid:request_id>/proposal/"
        ),
        views.factual_correction_proposal_save,
        name="factual_correction_proposal_save",
    ),
    path(
        (
            "moderation/publications/factual-corrections/"
            "<uuid:request_id>/proposal/prepare/"
        ),
        views.factual_correction_proposal_prepare,
        name="factual_correction_proposal_prepare",
    ),
    path(
        (
            "moderation/publications/factual-corrections/"
            "<uuid:request_id>/publish/"
        ),
        views.factual_correction_publish,
        name="factual_correction_publish",
    ),
    path(
        (
            "moderation/publications/factual-corrections/"
            "<uuid:request_id>/cancel/"
        ),
        views.factual_correction_cancel,
        name="factual_correction_cancel",
    ),
    path(
        (
            "moderation/publications/<uuid:predecessor_id>/"
            "editorial-revisions/draft/"
        ),
        views.editorial_revision_draft_create,
        name="editorial_revision_draft_create",
    ),
    path(
        (
            "moderation/publications/editorial-revisions/"
            "<uuid:revision_id>/draft/"
        ),
        views.editorial_revision_draft_update,
        name="editorial_revision_draft_update",
    ),
    path(
        (
            "moderation/publications/editorial-revisions/"
            "<uuid:revision_id>/submit/"
        ),
        views.editorial_revision_submit,
        name="editorial_revision_submit",
    ),
    path(
        (
            "moderation/publications/editorial-revisions/"
            "<uuid:revision_id>/return-for-rework/"
        ),
        views.editorial_revision_return_for_rework,
        name="editorial_revision_return_for_rework",
    ),
    path(
        (
            "moderation/publications/editorial-revisions/"
            "<uuid:revision_id>/abandon/"
        ),
        views.editorial_revision_abandon,
        name="editorial_revision_abandon",
    ),
    path(
        (
            "moderation/publications/editorial-revisions/"
            "<uuid:revision_id>/publish/"
        ),
        views.editorial_revision_publish,
        name="editorial_revision_publish",
    ),
    path(
        "moderation/fact-checks/" "<uuid:fact_check_id>/draft/",
        views.fact_check_draft_update,
        name=("moderation_fact_check_" "draft_update"),
    ),
    path(
        "moderation/fact-checks/" "<uuid:fact_check_id>/submit/",
        views.fact_check_submit,
        name=("moderation_fact_check_submit"),
    ),
    path(
        "moderation/fact-checks/" "<uuid:fact_check_id>/publish/",
        views.fact_check_publish,
        name=("moderation_fact_check_publish"),
    ),
    path(
        "moderation/fact-checks/" "<uuid:fact_check_id>/return-for-rework/",
        views.fact_check_return_for_rework,
        name="moderation_fact_check_return_for_rework",
    ),
    path(
        "moderation/fact-checks/" "<uuid:fact_check_id>/abandon/",
        views.fact_check_abandon,
        name="moderation_fact_check_abandon",
    ),
    path(
        ("organization-invitations/" "<str:token>/"),
        views.organization_invitation_detail,
        name="organization_invitation_detail",
    ),
    path(
        ("organization-invitations/" "<str:token>/" "accept/"),
        views.organization_invitation_accept,
        name="organization_invitation_accept",
    ),
    # GoogleLogin URL
    path("auth/google/", views.GoogleLogin.as_view(), name="google_login"),
]

router = DefaultRouter()
router.register(r"threads", views.ThreadViewSet, basename="thread")
router.register(r"claims", views.ClaimViewSet, basename="claim")
router.register(r"evidence", views.EvidenceSubmissionViewSet, basename="evidence")
router.register(r"votes", views.VoteViewSet, basename="vote")
router.register(r"comments", views.ThreadCommentViewSet, basename="comment")
router.register(r"thread-flags", views.ThreadFlagViewSet, basename="thread-flag")

urlpatterns += router.urls
