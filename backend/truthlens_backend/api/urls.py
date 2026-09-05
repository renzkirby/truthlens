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
    path("users/<str:username>/verdicts/", views.public_user_verdicts),
    path("users/<str:username>/follow/", views.toggle_follow_user),
    path("users/<str:username>/followers/", views.get_user_followers),
    path("users/<str:username>/following/", views.get_user_following),
    path("users/<str:username>/claims/", views.public_user_claims),
    path("users/<str:username>/moderation-stats/", views.moderator_transparency_stats),
    path("partners/", views.public_partner_directory, name="public_partner_directory"),
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
    path("moderation/stats/", views.moderation_stats_view, name="moderation_stats"),
    path("moderation/queue/", views.moderation_queue, name="moderation_queue"),
    path(
        "moderation/evidence-queue/",
        views.evidence_moderation_queue,
        name="moderation_evidence_queue",
    ),
    path(
        "moderation/verdict-queue/",
        views.verdict_queue,
        name="moderation_verdict_queue",
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
        "moderation/threads/<uuid:thread_id>/resolve/",
        views.moderation_resolve_thread,
        name="moderation_resolve_thread",
    ),
    path(
        "moderation/threads/<uuid:thread_id>/safety-action/",
        views.moderation_resolve_safety_thread,
        name="moderation_safety_action",
    ),
    path(
        "moderation/claims/" "<uuid:claim_id>/adjudicate/",
        views.adjudicate_claim,
        name="adjudicate_claim",
    ),
    path(
        "moderation/claims/" "<uuid:claim_id>/" "fact-checks/draft/",
        views.fact_check_draft_create,
        name=("moderation_fact_check_" "draft_create"),
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
