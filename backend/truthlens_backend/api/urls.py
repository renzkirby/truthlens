from django.urls import path, include
from . import views

urlpatterns = [
    path("analyze/", views.receive_snippet, name="analyze_snippet"),
]
