"""Permission checks shared by view modules.

Capabilities live on auth groups as Django permissions; per-object rules
(creator, manager, self) stay here. This module may import models only, so view
modules can use it without creating circular imports.
"""

CREATE_EVENT = "dashboard.create_event"
EDIT_ANY_EVENT = "dashboard.edit_any_event"
DELETE_ANY_EVENT = "dashboard.delete_any_event"
APPROVE_EVENT = "dashboard.approve_event"
MANAGE_EARNINGS = "dashboard.manage_earnings"
MANAGE_PARTICIPATION_TIMES = "dashboard.manage_participation_times"
MANAGE_JOIN_REQUESTS = "dashboard.manage_join_requests"
BYPASS_EVENT_CREATION_LIMIT = "dashboard.bypass_event_creation_limit"
VIEW_ALL_USERS = "dashboard.view_all_users"
MANAGE_USERS = "dashboard.manage_users"
ACCESS_ADMIN = "dashboard.access_admin"
MANAGE_POLLS = "dashboard.manage_polls"
VIEW_ABIKASSE = "dashboard.view_abikasse"
MANAGE_ABIKASSE = "dashboard.manage_abikasse"
VIEW_ANY_POINTS = "dashboard.view_any_points"
MANAGE_QUOTES = "dashboard.manage_quotes"


def _can(user, permission):
    return bool(user and user.is_authenticated and user.has_perm(permission))


def can_create_event(user):
    return _can(user, CREATE_EVENT)


def can_bypass_event_creation_limit(user):
    return _can(user, BYPASS_EVENT_CREATION_LIMIT)


def can_edit_event(user, event):
    if event.final:
        return False
    return (
        event.creator_id == user.pk
        or event.manager_id == user.pk
        or _can(user, EDIT_ANY_EVENT)
    )


def can_delete_event(user, event):
    if event.final:
        return False
    return (
        event.creator_id == user.pk
        or event.manager_id == user.pk
        or _can(user, DELETE_ANY_EVENT)
    )


def can_manage_join_requests(user, event):
    return user.pk in {event.manager_id, event.creator_id} or _can(
        user, MANAGE_JOIN_REQUESTS
    )


def can_manage_participation_times(user):
    return _can(user, MANAGE_PARTICIPATION_TIMES)


def can_manage_earnings(user):
    return _can(user, MANAGE_EARNINGS)


def can_view_users(request):
    return _can(request.user, VIEW_ALL_USERS)


def can_manage_users(user):
    return _can(user, MANAGE_USERS)


def can_edit_user(request, user_id):
    return request.user.pk == user_id or _can(request.user, MANAGE_USERS)


def can_change_password(request, user_id):
    return request.user.pk == user_id or _can(request.user, MANAGE_USERS)


def can_access_admin(user):
    # Django still requires is_staff to open /admin/ itself.
    return _can(user, ACCESS_ADMIN)


def can_create_poll(user):
    return _can(user, MANAGE_POLLS)


def can_manage_poll(user, poll):
    return poll.creator_id == user.pk or _can(user, MANAGE_POLLS)


def can_view_poll_results(user, poll):
    if poll.phase not in {poll.Phase.VOTING, poll.Phase.CLOSED}:
        return False
    return poll.results_public or can_manage_poll(user, poll)


def can_view_abikasse(user):
    return _can(user, VIEW_ABIKASSE)


def can_manage_abikasse(user):
    return _can(user, MANAGE_ABIKASSE)


def can_view_any_points(user):
    return _can(user, VIEW_ANY_POINTS)


def can_manage_quotes(user):
    return _can(user, MANAGE_QUOTES)


def can_delete_quote(user, quote):
    return quote.uploader_id == user.pk or can_manage_quotes(user)


def can_report_quote(user, quote):
    return quote.uploader_id != user.pk
