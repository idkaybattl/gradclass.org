"""Permission checks shared by view modules.

This module may import models only, so view modules can use it without creating
circular imports.
"""


def can_create_event(user):
    # Single hook for the future staff-only restriction; no behavior change yet.
    return True


def can_edit_event(user, event):
    return not event.final and (
        event.creator.id == user.id or event.manager.id == user.id or user.is_staff
    )


def can_manage_join_requests(user, event):
    return user.is_staff or user.pk in {event.manager_id, event.creator_id}


def can_manage_participation_times(user):
    return user.is_staff


def can_view_users(request):
    # currently everybody can view all users
    return True


def can_edit_user(request, user_id):
    return request.user.is_staff or request.user.id == user_id
