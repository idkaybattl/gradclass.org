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
VIEW_ALL_USERS = "dashboard.view_all_users"
MANAGE_USERS = "dashboard.manage_users"
ACCESS_ADMIN = "dashboard.access_admin"


def _can(user, permission):
    return bool(user and user.is_authenticated and user.has_perm(permission))


def can_create_event(user):
    return _can(user, CREATE_EVENT)


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


def can_edit_user(request, user_id):
    return request.user.pk == user_id or _can(request.user, MANAGE_USERS)


def can_change_password(request, user_id):
    return request.user.pk == user_id or _can(request.user, MANAGE_USERS)


def can_access_admin(user):
    # Django still requires is_staff to open /admin/ itself.
    return _can(user, ACCESS_ADMIN)
