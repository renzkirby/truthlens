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
    
    #Auth urls
    path('auth/login/', views.login_user),
    path('auth/refresh/', TokenRefreshView.as_view()),
    path('auth/register/', views.register_user),
    path('auth/me/', views.get_current_user),
    path('auth/my-claims/', views.my_claims),
    path('auth/send-verification/', views.send_verification_email),
    path('auth/verify-email/', views.verify_email),
    path('moderation/queue/', views.moderation_queue),
    path('moderation/evidence-queue/', views.evidence_moderation_queue),
    path('moderation/verdict-queue/', views.verdict_queue),
    path('moderation/threads/<uuid:thread_id>/resolve/', views.moderation_resolve_thread),
    path('moderation/threads/<uuid:thread_id>/safety-action/', views.moderation_resolve_safety_thread),
]

router = DefaultRouter()
router.register(r'threads', views.ThreadViewSet, basename='thread')
router.register(r'claims', views.ClaimViewSet, basename='claim')
router.register(r'evidence', views.EvidenceSubmissionViewSet, basename='evidence')
router.register(r'votes', views.VoteViewSet, basename='vote')
router.register(r'comments', views.ThreadCommentViewSet, basename='comment')
router.register(r'thread-flags', views.ThreadFlagViewSet, basename='thread-flag')

urlpatterns += router.urls
