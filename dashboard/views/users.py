from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from ..durations import format_duration
from ..feedback import get_feedback, render_feedback
from ..forms import UserProfileForm
from ..http_helpers import (
    get_safe_back_url,
    get_safe_next_url,
    is_htmx_request,
    render_page_or_partial,
)
from ..intro import introduction_required
from ..permissions import (
    can_change_password,
    can_edit_user,
    can_manage_users,
    can_view_any_points,
    can_view_user_mail,
    can_view_users,
)
from ..services import (
    build_password_reset_url,
    ticket_estimate,
    total_points,
    work_points,
)

User = get_user_model()


def user_details_url(user, *, status=None, back_url=None):
    url = reverse("user-details", kwargs={"user_id": user.pk})
    params = {}
    if status:
        params["status"] = status
    if back_url:
        params["back"] = back_url

    if params:
        url = f"{url}?{urlencode(params)}"
    return url


def user_details_context(request, user, *, back_url=None, status=None, feedback=None):
    next_url = get_safe_next_url(request)
    detail_url = user_details_url(user, back_url=back_url)
    can_edit = can_edit_user(request, user.pk)
    may_change_password = can_change_password(request, user.pk)
    can_reset_link = can_manage_users(request.user) and user.pk != request.user.pk
    can_view_mail = request.user.pk == user.pk or can_view_user_mail(request.user)
    display_name = user.get_full_name() or user.username

    can_view_points = request.user.pk == user.pk or can_view_any_points(request.user)
    points = {}
    if can_view_points:
        points_total = total_points(user)
        points_work = work_points(user)
        points = {
            "points_total": points_total,
            "points_work": points_work,
            "points_earnings": points_total - points_work,
            "user_ticket_estimate": ticket_estimate(user),
        }

    edit_url = ""
    if can_edit:
        params = {"back": detail_url}
        if next_url:
            params["next"] = next_url
        edit_url = (
            f"{reverse('user-edit', kwargs={'user_id': user.pk})}?{urlencode(params)}"
        )

    password_url = ""
    if may_change_password:
        params = {"back": detail_url}
        if next_url:
            params["next"] = next_url
        password_url = (
            f"{reverse('change-password-popup', kwargs={'user_id': user.pk})}"
            f"?{urlencode(params)}"
        )

    now = timezone.now()
    participation_events = []
    for participation in user.event_participations.select_related("event").order_by(
        "event__starting_date"
    ):
        event = participation.event
        event.is_upcoming = event.ending_date > now
        event.is_own = True
        participation_events.append(event)

    if feedback is None:
        feedback = get_feedback(status)

    return {
        "profile_user": user,
        "display_name": display_name,
        "total_hours_display": format_duration(user.profile.total_hours()),
        "participation_events": participation_events,
        "can_edit": can_edit,
        "can_change_password": may_change_password,
        "can_reset_link": can_reset_link,
        "can_view_mail": can_view_mail,
        "can_view_points": can_view_points,
        **points,
        "reset_link_url": reverse("user-reset-link", kwargs={"user_id": user.pk}),
        "next_url": next_url,
        "back_url": back_url,
        "detail_url": detail_url,
        "edit_url": edit_url,
        "password_url": password_url,
        "action_label": "Bearbeiten" if can_edit else "",
        "action_url": edit_url,
        "action_overlay": can_edit,
        "feedback": feedback,
    }


def render_user_details(request, user, **overrides):
    context = user_details_context(request, user, **overrides)
    return render_page_or_partial(
        request,
        "users/detail.html",
        "users/_user_details.html",
        context,
    )


@login_required
@require_GET
@introduction_required
def users(request):
    if not can_view_users(request):
        raise PermissionDenied

    user_list = list(
        User.objects.select_related("profile").order_by(
            "first_name", "last_name", "username"
        )
    )

    return render(
        request,
        "users.html",
        {
            "users": user_list,
            "feedback": get_feedback(request.GET.get("status")),
        },
    )


@login_required
@require_GET
def user_details(request, user_id):
    if not can_view_users(request):
        raise PermissionDenied

    user = get_object_or_404(User.objects.select_related("profile"), pk=user_id)

    return render_user_details(
        request,
        user,
        back_url=get_safe_back_url(request),
        status=request.GET.get("status"),
    )


@login_required
@require_POST
def user_reset_link(request, user_id):
    user = get_object_or_404(User, pk=user_id)

    if not can_manage_users(request.user):
        feedback = get_feedback(
            "reset-link-denied",
            action_url=user_details_url(user),
            action_label="Zum Profil",
            action_htmx=True,
        )
        if is_htmx_request(request):
            return render_feedback(request, feedback)

        return redirect(user_details_url(user, status="reset-link-denied"))

    return render_page_or_partial(
        request,
        "users/reset_link.html",
        "users/_reset_link.html",
        {
            "display_name": user.get_full_name() or user.username,
            "reset_url": build_password_reset_url(user, request),
            "back_url": user_details_url(user),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def edit_user(request, user_id):
    if not can_edit_user(request, user_id):
        feedback = get_feedback(
            "user-edit-denied",
            action_url=reverse("users"),
            action_label="Zur Liste",
        )
        if is_htmx_request(request):
            return render_feedback(request, feedback)

        return redirect(
            f"{reverse('users')}?{urlencode({'status': 'user-edit-denied'})}"
        )

    user = get_object_or_404(User, pk=user_id)
    back_url = get_safe_back_url(request) or user_details_url(user)
    next_url = get_safe_next_url(request)

    if request.method == "POST":
        form = UserProfileForm(request.POST, instance=user.profile)

        if form.is_valid():
            form.save()

            if is_htmx_request(request):
                return render_feedback(
                    request,
                    get_feedback(
                        "profile-updated",
                        action_url=back_url,
                        action_label="Zurück zum Profil",
                        action_htmx=True,
                    ),
                )

            return redirect(user_details_url(user, status="profile-updated"))
    else:
        if not is_htmx_request(request):
            return redirect(user_details_url(user))
        form = UserProfileForm(instance=user.profile)

    template = (
        "users/_user_form.html" if is_htmx_request(request) else "users/form.html"
    )
    return render(
        request,
        template,
        {
            "form": form,
            "user": user,
            "display_name": user.get_full_name() or user.username,
            "back_url": back_url,
            "next_url": next_url,
        },
    )
