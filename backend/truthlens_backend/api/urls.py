from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.routers import DefaultRouter
from . import views

urlpatterns = [
    path("analyze/", views.receive_snippet, name="analyze_snippet"),
    path("claims/<claim_id>/status", views.claim_polling_endpoint, name="claim_status"),
    path("verify-url/", views.verify_url, name="verify_url"),
    
    #Auth urls
    path('auth/login/', TokenObtainPairView.as_view()),
    path('auth/refresh/', TokenRefreshView.as_view()),
    path('auth/register/', views.register_user),
    path('auth/me/', views.get_current_user),
    path('auth/my-claims/', views.my_claims), 
]

router = DefaultRouter()
router.register(r'threads', views.ThreadViewSet, basename='thread')
router.register(r'claims', views.ClaimViewSet, basename='claim')
router.register(r'evidence', views.EvidenceSubmissionViewSet, basename='evidence')
router.register(r'comments', views.ThreadCommentViewSet, basename='comment')

urlpatterns += router.urls
