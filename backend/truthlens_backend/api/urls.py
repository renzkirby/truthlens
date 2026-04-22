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
    path("claims/<uuid:claim_id>/analysis/", views.get_claim_analysis, name="claim_analysis"),
    path("verify-pdf/", views.verify_pdf, name="verify_pdf"),
    
    #Auth urls
    path('auth/login/', views.login_user),
    path('auth/refresh/', TokenRefreshView.as_view()),
    path('auth/register/', views.register_user),
    path('auth/me/', views.get_current_user),
    path('auth/profile/update/', views.update_profile),
    path('auth/guest-scan-sync/', views.sync_guest_scan),
    path('users/search/', views.search_users),
    path('users/<str:username>/', views.get_public_user_profile),
    path('users/<str:username>/threads/', views.public_user_threads),
    path('users/<str:username>/evidence/', views.public_user_evidence),
    path('users/<str:username>/verdicts/', views.public_user_verdicts),
    path('users/<str:username>/follow/', views.toggle_follow_user),
    path('users/<str:username>/followers/', views.get_user_followers), 
    path('users/<str:username>/following/', views.get_user_following),
    path('users/<str:username>/claims/', views.public_user_claims),
    path('users/<str:username>/moderation-stats/', views.moderator_transparency_stats),
    path('auth/my-claims/', views.my_claims),
    path('auth/send-verification/', views.send_verification_email),
    path('auth/verify-email/', views.verify_email),
    path('moderation/queue/', views.moderation_queue),
    path('moderation/evidence-queue/', views.evidence_moderation_queue),
    path('moderation/verdict-queue/', views.verdict_queue),
    path('moderation/threads/<uuid:thread_id>/resolve/', views.moderation_resolve_thread),
    path('moderation/threads/<uuid:thread_id>/safety-action/', views.moderation_resolve_safety_thread),

    # DashBoard URLs
    path("moderation/stats/", views.moderation_stats_view, name="moderation_stats"),
    path("users/me/dashboard/", views.UserHubView.as_view(), name="user_hub"),
    path("claims/<uuid:claim_id>/toggle-save/", views.toggle_save_claim, name="toggle_save_claim"),
]

router = DefaultRouter()
router.register(r'threads', views.ThreadViewSet, basename='thread')
router.register(r'claims', views.ClaimViewSet, basename='claim')
router.register(r'evidence', views.EvidenceSubmissionViewSet, basename='evidence')
router.register(r'votes', views.VoteViewSet, basename='vote')
router.register(r'comments', views.ThreadCommentViewSet, basename='comment')
router.register(r'thread-flags', views.ThreadFlagViewSet, basename='thread-flag')

urlpatterns += router.urls
