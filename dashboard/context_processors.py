from .notifications import get_unread_notifications


def unread_notifications(request):
    if not request.user.is_authenticated:
        return {"unread_count": 0}

    return {"unread_count": get_unread_notifications(request.user).count()}
