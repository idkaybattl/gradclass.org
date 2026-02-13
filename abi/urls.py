from django.urls import path

from . import views

urlpatterns = [
    path("", views.abi, name="abi"),
    path("calendar/", views.calendar, name="calendar"),
    path("upcoming/", views.upcoming_projects, name="upcoming-projects"),
    path(
        "upcoming/<int:project_id>/add-participant/",
        views.add_participant,
        name="add-participant",
    ),
    path(
        "upcoming/<int:project_id>/update/",
        views.update_project,
        name="update-project",
    ),
    path("upcoming/<int:project_id>/join/", views.join_project, name="join-project"),
]
