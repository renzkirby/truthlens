from django.urls import path, include
from . import views

urlpatterns = [
    path("analyze/", views.receive_snippet, name="analyze_snippet"),
    path("claims/<claim_id>/status", views.claim_polling_endpoint, name="claim_status"),
    path("verify-url/", views.verify_url, name="verify_url"),
]
