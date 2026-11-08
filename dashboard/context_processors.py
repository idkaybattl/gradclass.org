from .notifications import get_unread_notifications
from .permissions import can_access_admin


def admin_access(request):
    return {"can_access_admin": can_access_admin(request.user)}


def unread_notifications(request):
    if not request.user.is_authenticated:
        return {"unread_count": 0}

    return {"unread_count": get_unread_notifications(request.user).count()}
