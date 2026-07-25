from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("set_password/", views.password_set, name="set-password"),
    path("", views.main_page, name="main-page"),
    path("introduction/", views.introduction, name="introduction"),
    # notifications
    path("notifications/", views.notifications, name="notifications"),
    path(
        "notifications/mark_all_read/",
        views.mark_all_notifications_as_read,
        name="mark-all-notifications-as-read",
    ),
    path(
        "notifications/<int:notification_id>/read/",
        views.mark_notification_as_read,
        name="mark-notification-as-read",
    ),
    # events
    path("calendar/", views.calendar, name="calendar"),
    path("events/", views.events, {"mode": "all"}, name="events"),
    path(
        "events/upcoming/",
        views.events,
        {"mode": "upcoming"},
        name="events-upcoming",
    ),
    path("events/own/", views.events, {"mode": "own"}, name="events-own"),
    path("events/create/", views.create_event, name="event-create"),
    path("events/<int:event_id>/", views.event_details, name="event-details"),
    path("events/<int:event_id>/edit/", views.edit_event, name="event-edit"),
    path("events/<int:event_id>/join/", views.join_event, name="event-join"),
    path("events/<int:event_id>/leave/", views.leave_event, name="event-leave"),
    path("events/<int:event_id>/delete/", views.delete_event, name="event-delete"),
    path(
        "events/<int:event_id>/set-earnings/",
        views.set_event_earnings,
        name="set-earnings",
    ),
    path(
        "events/<int:event_id>/set-earnings-received/",
        views.set_earnings_received,
        name="set-earnings-received",
    ),
    # users
    path("users/", views.users, name="users"),
    path("users/<int:user_id>/", views.user_details, name="user-details"),
    path("users/<int:user_id>/edit/", views.edit_user, name="user-edit"),
    path(
        "users/<int:user_id>/change_password_popup/",
        views.change_password_popup,
        name="change-password-popup",
    ),
    # contact
    path("contact/", views.contact, name="contact"),
    # polls
    path("polls/", views.polls, name="polls"),
]
