from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import forms
from .views import abikasse, auth, core, events, notifications, polls, users

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(authentication_form=forms.LoginForm),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # password reset
    path(
        "passwort-vergessen/",
        auth_views.PasswordResetView.as_view(
            form_class=forms.PasswordResetForm,
            template_name="auth/password_reset/form.html",
            subject_template_name="emails/password_reset_subject.txt",
            email_template_name="emails/password_reset.txt",
            success_url=reverse_lazy("password-reset-done"),
        ),
        name="password-reset",
    ),
    path(
        "passwort-vergessen/gesendet/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="auth/password_reset/done.html",
        ),
        name="password-reset-done",
    ),
    path(
        "passwort-zuruecksetzen/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="auth/password_reset/confirm.html",
            success_url=reverse_lazy("password-reset-complete"),
        ),
        name="password-reset-confirm",
    ),
    path(
        "passwort-zuruecksetzen/fertig/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="auth/password_reset/complete.html",
        ),
        name="password-reset-complete",
    ),
    path("set_password/", auth.password_set, name="set-password"),
    path("", core.main_page, name="main-page"),
    path("introduction/", auth.introduction, name="introduction"),
    # abikasse
    path("abikasse/", abikasse.abikasse, name="abikasse"),
    path(
        "abikasse/entries/create/",
        abikasse.entry_create,
        name="abikasse-entry-create",
    ),
    path(
        "abikasse/entries/<int:entry_id>/edit/",
        abikasse.entry_edit,
        name="abikasse-entry-edit",
    ),
    path(
        "abikasse/entries/<int:entry_id>/delete/",
        abikasse.entry_delete,
        name="abikasse-entry-delete",
    ),
    path("abikasse/export/", abikasse.export, name="abikasse-export"),
    path("abikasse/settings/", abikasse.settings, name="abikasse-settings"),
    path(
        "abikasse/ticket-count/edit/",
        abikasse.ticket_count_edit,
        name="abikasse-ticket-count-edit",
    ),
    # notifications
    path("notifications/", notifications.notifications, name="notifications"),
    path(
        "notifications/mark_all_read/",
        notifications.mark_all_notifications_as_read,
        name="mark-all-notifications-as-read",
    ),
    path(
        "notifications/<int:notification_id>/read/",
        notifications.mark_notification_as_read,
        name="mark-notification-as-read",
    ),
    # events
    path("calendar/", core.calendar, name="calendar"),
    path("events/", events.events, {"mode": "all"}, name="events"),
    path(
        "events/upcoming/",
        events.events,
        {"mode": "upcoming"},
        name="events-upcoming",
    ),
    path("events/own/", events.events, {"mode": "own"}, name="events-own"),
    path("events/create/", events.create_event, name="event-create"),
    path("events/<int:event_id>/", events.event_details, name="event-details"),
    path("events/<int:event_id>/edit/", events.edit_event, name="event-edit"),
    path("events/<int:event_id>/join/", events.join_event, name="event-join"),
    path("events/<int:event_id>/leave/", events.leave_event, name="event-leave"),
    path("events/<int:event_id>/delete/", events.delete_event, name="event-delete"),
    path(
        "events/<int:event_id>/set-earnings/",
        events.set_event_earnings,
        name="set-earnings",
    ),
    path(
        "events/<int:event_id>/set-earnings-received/",
        events.set_earnings_received,
        name="set-earnings-received",
    ),
    path(
        "events/<int:event_id>/participation-times/",
        events.set_participation_times,
        name="set-participation-times",
    ),
    path(
        "events/join-request/<int:join_request_id>/",
        events.join_request_details,
        name="join-request-details",
    ),
    path(
        "events/join-request/<int:join_request_id>/accept/",
        events.accept_join_request,
        name="accept-join-request",
    ),
    path(
        "events/join-request/<int:join_request_id>/decline/",
        events.decline_join_request,
        name="decline-join-request",
    ),
    # users
    path("users/", users.users, name="users"),
    path("users/<int:user_id>/", users.user_details, name="user-details"),
    path("users/<int:user_id>/edit/", users.edit_user, name="user-edit"),
    path(
        "users/<int:user_id>/reset-link/",
        users.user_reset_link,
        name="user-reset-link",
    ),
    path(
        "users/<int:user_id>/change_password_popup/",
        auth.change_password_popup,
        name="change-password-popup",
    ),
    # contact
    path("contact/", core.contact, name="contact"),
    # legal, public
    path("datenschutz/", core.datenschutz, name="datenschutz"),
    # polls
    path("polls/", polls.polls, name="polls"),
    path("polls/create/", polls.poll_create, name="poll-create"),
    path("polls/<int:poll_id>/", polls.poll_details, name="poll-details"),
    path("polls/<int:poll_id>/edit/", polls.poll_edit, name="poll-edit"),
    path(
        "polls/<int:poll_id>/start-suggestions/",
        polls.poll_start_suggestions,
        name="poll-start-suggestions",
    ),
    path(
        "polls/<int:poll_id>/start-voting/",
        polls.poll_start_voting,
        name="poll-start-voting",
    ),
    path(
        "polls/<int:poll_id>/close-suggestions/",
        polls.poll_close_suggestions,
        name="poll-close-suggestions",
    ),
    path(
        "polls/<int:poll_id>/close-voting/",
        polls.poll_close_voting,
        name="poll-close-voting",
    ),
    path("polls/<int:poll_id>/suggest/", polls.poll_suggest, name="poll-suggest"),
    path("polls/<int:poll_id>/vote/", polls.poll_vote, name="poll-vote"),
    path(
        "polls/<int:poll_id>/moderate/",
        polls.poll_moderate,
        name="poll-moderate",
    ),
    path("polls/<int:poll_id>/results/", polls.poll_results, name="poll-results"),
]
