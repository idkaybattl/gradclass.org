from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.abi, name="abi"),
    path("calendar/", views.calendar, name="calendar"),
    path("projects/", views.projects, name="upcoming-projects"),
    path("upcoming/<int:project_id>/join/", views.join_project, name="join-project"),
]
