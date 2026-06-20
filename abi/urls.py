from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.abi, name="abi"),
    path("calendar/", views.calendar, name="calendar"),
    path("projects/", views.projects, {"mode": "all"}, name="projects"),
    path(
        "projects/upcoming/",
        views.projects,
        {"mode": "upcoming"},
        name="projects-upcoming",
    ),
    path("projects/own/", views.projects, {"mode": "own"}, name="projects-own"),
    path("projects/create/", views.create_project, name="project-create"),
    path("projects/<int:project_id>/", views.project_details, name="project-details"),
    path("projects/<int:project_id>/edit/", views.edit_project, name="project-edit"),
    path("projects/<int:project_id>/join/", views.join_project, name="project-join"),
    path("projects/<int:project_id>/leave/", views.leave_project, name="project-leave"),
    path(
        "projects/<int:project_id>/delete/", views.delete_project, name="project-delete"
    ),
]
