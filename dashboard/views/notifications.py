from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from ..http_helpers import is_htmx_request, redirect_next_or
from ..notifications import Notification, get_unread_notifications


def render_notifications(request):
    notifications = list(get_unread_notifications(request.user))
    return render(
        request,
        "components/notifications.html",
        {
            "notifications": notifications,
            "unread_count": len(notifications),
            "oob": is_htmx_request(request),
        },
    )


def notification_action_response(request):
    if is_htmx_request(request):
        return render_notifications(request)

    return redirect_next_or(request, "main-page")


@login_required
@require_GET
def notifications(request):
    return render_notifications(request)


@login_required
@require_POST
def mark_all_notifications_as_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return notification_action_response(request)


@login_required
@require_POST
def mark_notification_as_read(request, notification_id):
    notification = get_object_or_404(
        Notification, id=notification_id, user=request.user
    )
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])

    return notification_action_response(request)
