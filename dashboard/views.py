from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse
from django.http.response import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from .forms import (
    EventForm,
    ParticipationTimeFormSet,
    SetEarningsForm,
    SetEarningsReceivedForm,
    UserProfileForm,
)
from .models import Abikasse, Event, EventParticipation, JoinRequest
from .notifications import (
    Notification,
    NotificationVerbChoices,
    get_unread_notifications,
)
from .services import save_event

User = get_user_model()
MAX_PROJECTS_PER_HOUR = 5
MAX_PROJECTS_PER_DAY = 10


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


def _get_safe_url(request, value):
    if not value:
        return None

    if url_has_allowed_host_and_scheme(
        value,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return value

    return None


def get_safe_next_url(request):
    return _get_safe_url(request, request.POST.get("next") or request.GET.get("next"))


def get_safe_back_url(request):
    return _get_safe_url(request, request.GET.get("back"))


def redirect_next_or(request, fallback, **kwargs):
    next_url = get_safe_next_url(request)
    url = next_url or reverse(fallback, kwargs=kwargs)

    if is_htmx_request(request):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = url
        return response

    return redirect(url)


def is_htmx_request(request):
    return request.headers.get("HX-Request") == "true"


def render_page_or_partial(request, page_template, partial_template, context):
    template = partial_template if is_htmx_request(request) else page_template
    return render(request, template, context)


STATUS_FEEDBACK = {
    "joined": ("success", "Du nimmst jetzt teil"),
    "requested": ("success", "Anfrage gesendet"),
    "already-requested": ("info", "Du hast bereits angefragt"),
    "already-participant": ("error", "Du nimmst an diesem Projekt bereits teil."),
    "not-participant": ("error", "Du nimmst an diesem Projekt nicht teil."),
    "final": ("error", "Dieses Projekt ist bereits abgeschlossen."),
    "past": ("error", "Das Projekt liegt in der Vergangenheit."),
    "left": ("success", "Teilnahme beendet."),
    "earnings": ("success", "Einnahmen gesetzt."),
    "earnings-received": ("success", "Einnahmenstatus aktualisiert."),
    "participation-times": ("success", "Arbeitszeiten gespeichert."),
    "request-accepted": ("success", "Anfrage angenommen."),
    "request-declined": ("success", "Anfrage abgelehnt."),
    "deleted": ("success", "Aktion gelöscht."),
    "edit-denied": ("error", "Du bist nicht berechtigt, diese Aktion zu bearbeiten."),
    "delete-denied": ("error", "Du bist nicht berechtigt, diese Aktion zu löschen."),
}


def get_feedback(status):
    entry = STATUS_FEEDBACK.get(status)
    if entry is None:
        return None

    kind, title = entry
    return {"kind": kind, "title": title, "message": ""}


def render_feedback(request, feedback, *, status=200):
    return render(
        request,
        "components/_feedback.html",
        {"feedback": feedback},
        status=status,
    )


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


def get_event_creation_limit_error(user):
    current_time = timezone.now()
    user_events = Event.objects.filter(creator=user)

    events_in_last_hour = user_events.filter(
        created_at__gte=current_time - timedelta(hours=1)
    ).count()
    if events_in_last_hour >= MAX_PROJECTS_PER_HOUR and not user.is_staff:
        return (
            f"Du kannst maximal {MAX_PROJECTS_PER_HOUR} Aktionen pro Stunde erstellen."
        )

    events_in_last_day = user_events.filter(
        created_at__gte=current_time - timedelta(days=1)
    ).count()
    if events_in_last_day >= MAX_PROJECTS_PER_DAY and not user.is_staff:
        return f"Du kannst maximal {MAX_PROJECTS_PER_DAY} Aktionen pro Tag erstellen."

    return None


def redirect_if_introduction_needed(request):
    """
    Helper used by views that should force the user through the introduction
    before accessing the main site.
    """
    # The user is guaranteed to be authenticated (all callers are @login_required)
    profile = request.user.profile
    if not profile.has_had_introduction:
        return redirect("introduction")  # name of the URL pattern
    return None


@login_required
@require_GET
def main_page(request):
    intro_redirect = redirect_if_introduction_needed(request)
    if intro_redirect:
        return intro_redirect

    abikasse, _ = Abikasse.objects.get_or_create(
        pk=1,
        defaults={
            "goal": 30000,
        },
    )
    all_users = User.objects.select_related("profile")
    users_with_hours = [
        {"user": user, "hours": user.profile.total_hours()} for user in all_users
    ]

    # Rank everyone, including 0-hour users, so ranks reflect true standing
    full_ranking = sorted(
        users_with_hours, key=lambda entry: entry.get("hours", 0), reverse=True
    )

    for i, entry in enumerate(full_ranking):
        if i > 0 and full_ranking[i - 1]["hours"] == entry["hours"]:
            entry["rank"] = full_ranking[i - 1]["rank"]
        else:
            entry["rank"] = i + 1

    # Find the request user's true rank before any filtering
    user_entry = next(entry for entry in full_ranking if entry["user"] == request.user)

    # Now filter out 0-hour users and cut to top 10 for display
    ranking = [entry for entry in full_ranking if entry["hours"] > timedelta(0)][:10]

    user_in_ranking = any(entry["user"] == request.user for entry in ranking)
    if not user_in_ranking:
        ranking.append(user_entry)

    return render(
        request,
        "index.html",
        {
            "abikasse_current": abikasse.total_earnings(),
            "abikasse_goal": abikasse.goal,
            "can_view_users": can_view_users(request),
            "ranking": ranking,
        },
    )


@login_required
@require_POST
def password_set(request):
    form = SetPasswordForm(request.user, request.POST)
    if form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        return JsonResponse({"success": True})
    return JsonResponse({"success": False})


@login_required
def change_password_popup(request, user_id):
    if request.method == "POST":
        user = User.objects.get(pk=user_id)
        form = PasswordChangeForm(user, request.POST)
        if form.is_valid():
            print("valid form")
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Dein Passwort wurde erfolgreich geändert.")
            # Build the same context user_details uses
            total_hours = user.profile.total_hours()
            total_earnings = user.profile.total_earnings()
            event_participations = set(user.event_participations.all())
            can_edit = can_edit_user(request, user_id)
            can_change_password = request.user.is_staff or request.user.id == user_id

            html = render_to_string(
                "components/_user_details.html",
                {
                    "user": user,
                    "total_hours": total_hours,
                    "total_earnings": total_earnings,
                    "event_participations": event_participations,
                    "can_edit": can_edit,
                    "can_change_password": can_change_password,
                    "next_url": get_safe_next_url(request),
                },
                request=request,
            )
            return HttpResponse(html)

        # ----- FAILURE -----
        # Render the form again (with errors) and send it back
        print("invalid form")
        html = render_to_string(
            "components/_user_change_password.html",
            {"user": user, "form": form, "next_url": request.GET.get("next")},
            request=request,
        )
        return HttpResponse(html, status=200)

    user = User.objects.get(pk=user_id)
    form = PasswordChangeForm(user)
    return render(
        request,
        "components/_user_change_password.html",
        {"form": form, "user": user, "next_url": request.GET.get("next")},
    )


@login_required
def introduction(request):
    profile = request.user.profile

    if request.method == "POST":
        profile_form = UserProfileForm(request.POST, instance=profile)
        if profile_form.is_valid():
            profile_form.save()
            # Mark the introduction as completed
            profile.has_had_introduction = True
            profile.save(update_fields=["has_had_introduction"])

            messages.success(request, "Dein Profil wurde gespeichert.")
            # Respect a ?next= query‑parameter if present
            return redirect_next_or(request, "main-page")
        # If the form is invalid we fall through to the template rendering
        # so the user can correct the errors.
    else:
        profile_form = UserProfileForm(instance=profile)

    password_form = SetPasswordForm(request.user)

    return render(
        request,
        "introduction.html",
        {
            "profile_form": profile_form,
            "password_form": password_form,
            "user": request.user,
            "next_url": get_safe_next_url(request),
        },
    )


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


@login_required
def calendar(request):
    return render(request, "calendar.html")


@login_required
def create_event(request):
    rate_limit_error = get_event_creation_limit_error(request.user)
    if rate_limit_error:
        messages.error(request, rate_limit_error)
        return redirect_next_or(request, "events")

    if request.method == "GET":
        form = EventForm(prefix="new", request_user=request.user)
        return render(
            request,
            "events/_event_create_popup.html",
            {
                "form": form,
                "next_url": get_safe_next_url(request),
            },
        )

    data = request.POST
    form = EventForm(data=data, prefix="new", request_user=request.user)

    if form.is_valid():
        save_event(form, request.user)
        messages.success(request, "Projekt erfolgreich erstellt.")

        return redirect_next_or(request, "events")
    else:
        messages.error(request, "Form ist invalide.")

    return render(
        request,
        "events/_event_create_popup.html",
        {"form": form, "next_url": get_safe_next_url(request)},
    )


@login_required
def edit_event(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    if not can_edit_event(request.user, event) or event.final:
        messages.error(request, "Du darfst diese Aktion nicht bearbeiten")
        return redirect_next_or(request, "events")

    if request.method == "POST":
        form = EventForm(
            data=request.POST,
            instance=event,
            prefix=str(event.id),
            request_user=request.user,
        )

        if form.is_valid():
            save_event(form, request.user)

            messages.success(request, "Projekt erfolgreich bearbeitet.")

            return render(
                request, "events/_event_edit_success_popup.html", {"event": event}
            )
        else:
            messages.error(request, "Form ist invalide.")

        return render(
            request,
            "events/_event_edit_popup.html",
            {"form": form, "event": event, "next_url": get_safe_next_url(request)},
        )

    else:
        form = EventForm(
            instance=event,
            prefix=str(event.id),
            request_user=request.user,
        )
        return render(
            request,
            "events/_event_edit_popup.html",
            {"form": form, "event": event, "next_url": get_safe_next_url(request)},
        )


@login_required
@require_GET
def events(request, mode):
    now = timezone.now()
    event_list = list(
        Event.objects.select_related("creator", "manager")
        .prefetch_related("participants")
        .order_by("starting_date")
    )

    for event in event_list:
        participant_ids = {participant.pk for participant in event.participants.all()}
        event.is_upcoming = event.ending_date > now
        event.is_own = (
            event.creator_id == request.user.pk
            or event.manager_id == request.user.pk
            or request.user.pk in participant_ids
        )

    return render(
        request,
        "events.html",
        {
            "events": event_list,
            "initial_filter": mode if mode in {"upcoming", "past"} else "all",
            "own_only": mode == "own",
            "feedback": get_feedback(request.GET.get("status")),
        },
    )


def event_detail_url(event, status=None):
    url = reverse("event-details", kwargs={"event_id": event.pk})
    if status:
        url = f"{url}?{urlencode({'status': status})}"
    return url


def event_details_context(
    request,
    event,
    *,
    earnings_form=None,
    earnings_received_form=None,
    participation_time_formset=None,
    back_url=None,
    status=None,
    feedback=None,
):
    user = request.user
    participants = list(event.participants.all())
    participant_ids = {participant.pk for participant in participants}
    is_participant = user.pk in participant_ids
    can_edit = can_edit_event(user, event)
    can_manage_times = can_manage_participation_times(user)

    if earnings_form is None:
        earnings_form = SetEarningsForm(instance=event)
    if earnings_received_form is None:
        earnings_received_form = SetEarningsReceivedForm(instance=event)
    if participation_time_formset is None and can_manage_times:
        participation_time_formset = ParticipationTimeFormSet(
            instance=event,
            queryset=EventParticipation.objects.filter(event=event)
            .select_related("user", "event")
            .order_by("user__first_name", "user__last_name", "user__username"),
        )
    if feedback is None:
        feedback = get_feedback(status)

    edit_url = f"{reverse('event-edit', kwargs={'event_id': event.pk})}?{urlencode({'back': reverse('event-details', kwargs={'event_id': event.pk})})}"
    detail_url = reverse("event-details", kwargs={"event_id": event.pk})
    participation_times_open = bool(
        participation_time_formset
        and participation_time_formset.is_bound
        and (
            participation_time_formset.errors
            or participation_time_formset.non_form_errors
        )
    )

    return {
        "event": event,
        "title": event.title,
        "participants": participants,
        "can_edit": can_edit,
        "is_participant": is_participant,
        "can_delete": can_edit,
        "can_leave": is_participant and not event.final,
        "can_join": not is_participant and not event.final,
        "can_approve_payment": user.is_staff,
        "can_manage_participation_times": can_manage_times,
        "earnings_form": earnings_form,
        "earnings_received_form": earnings_received_form,
        "participation_time_formset": participation_time_formset,
        "next_url": get_safe_next_url(request),
        "back_url": back_url,
        "detail_url": detail_url,
        "edit_url": edit_url,
        "action_label": "Bearbeiten" if can_edit else "",
        "action_url": edit_url if can_edit else "",
        "action_overlay": can_edit,
        "participation_times_open": participation_times_open,
        "feedback": feedback,
    }


def render_event_details(request, event, **overrides):
    context = event_details_context(request, event, **overrides)
    return render_page_or_partial(
        request,
        "events/detail.html",
        "events/_event_details.html",
        context,
    )


def event_action_response(request, event, status):
    if is_htmx_request(request):
        return render_event_details(request, event, status=status)

    return redirect(event_detail_url(event, status))


def join_request_action_response(request, event, feedback, status):
    if is_htmx_request(request):
        return render_feedback(request, feedback)

    return redirect(event_detail_url(event, status))


def mark_join_request_notification_read(join_request):
    content_type = ContentType.objects.get_for_model(JoinRequest)
    Notification.objects.filter(
        content_type=content_type,
        object_id=join_request.pk,
        verb=NotificationVerbChoices.EVENT_JOIN_REQUEST,
    ).update(is_read=True)


@login_required
@require_GET
def event_details(request, event_id):
    event = get_object_or_404(
        Event.objects.select_related("creator", "manager").prefetch_related(
            "participants"
        ),
        id=event_id,
    )

    return render_event_details(
        request,
        event,
        back_url=get_safe_back_url(request),
        status=request.GET.get("status"),
    )


@login_required
@require_POST
def join_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    user = request.user

    if event.final:
        return event_action_response(request, event, "final")
    if timezone.now() >= event.starting_date:
        return event_action_response(request, event, "past")
    if event.participants.filter(pk=user.pk).exists():
        return event_action_response(request, event, "already-participant")

    if user.is_staff or user.pk in {event.creator_id, event.manager_id}:
        EventParticipation.objects.get_or_create(event=event, user=user)
        return event_action_response(request, event, "joined")

    _, created = JoinRequest.objects.get_or_create(requestor=user, event=event)
    return event_action_response(
        request,
        event,
        "requested" if created else "already-requested",
    )


@login_required
@require_GET
def join_request_details(request, join_request_id):
    join_request = get_object_or_404(
        JoinRequest.objects.select_related(
            "requestor", "event__creator", "event__manager"
        ),
        id=join_request_id,
    )
    if not can_manage_join_requests(request.user, join_request.event):
        raise PermissionDenied

    return render_page_or_partial(
        request,
        "events/join_request.html",
        "events/_join_request.html",
        {
            "join_request": join_request,
            "event": join_request.event,
            "back_url": get_safe_back_url(request),
        },
    )


@login_required
@require_POST
def accept_join_request(request, join_request_id):
    join_request = get_object_or_404(
        JoinRequest.objects.select_related("requestor", "event"),
        id=join_request_id,
    )
    event = join_request.event
    if not can_manage_join_requests(request.user, event):
        raise PermissionDenied

    requestor = join_request.requestor

    if event.final:
        return join_request_action_response(
            request,
            event,
            {
                "kind": "error",
                "title": "Dieses Projekt ist bereits abgeschlossen.",
                "message": "",
                "action_label": "Zur Aktion",
                "action_url": reverse("event-details", kwargs={"event_id": event.pk}),
                "action_htmx": True,
            },
            "final",
        )

    with transaction.atomic():
        EventParticipation.objects.get_or_create(event=event, user=requestor)
        mark_join_request_notification_read(join_request)
        join_request.delete()
        Notification.objects.create(
            user=requestor,
            verb=NotificationVerbChoices.EVENT_JOIN_REQUEST_ACCEPTED,
            target=event,
        )

    return join_request_action_response(
        request,
        event,
        {
            "kind": "success",
            "title": "Anfrage angenommen.",
            "message": "Die Teilnahme wurde eingetragen.",
            "action_label": "Zur Aktion",
            "action_url": reverse("event-details", kwargs={"event_id": event.pk}),
            "action_htmx": True,
        },
        "request-accepted",
    )


@login_required
@require_POST
def decline_join_request(request, join_request_id):
    join_request = get_object_or_404(
        JoinRequest.objects.select_related("requestor", "event"),
        id=join_request_id,
    )
    event = join_request.event
    if not can_manage_join_requests(request.user, event):
        raise PermissionDenied

    requestor = join_request.requestor

    with transaction.atomic():
        mark_join_request_notification_read(join_request)
        join_request.delete()
        Notification.objects.create(
            user=requestor,
            verb=NotificationVerbChoices.EVENT_JOIN_REQUEST_REJECTED,
            target=event,
        )

    return join_request_action_response(
        request,
        event,
        {
            "kind": "success",
            "title": "Anfrage abgelehnt.",
            "message": "Die Anfrage wurde abgelehnt.",
            "action_label": "Zur Aktion",
            "action_url": reverse("event-details", kwargs={"event_id": event.pk}),
            "action_htmx": True,
        },
        "request-declined",
    )


@login_required
@require_POST
def leave_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    if event.final:
        return event_action_response(request, event, "final")
    if not event.participants.filter(pk=request.user.pk).exists():
        return event_action_response(request, event, "not-participant")

    EventParticipation.objects.filter(event=event, user=request.user).delete()
    return event_action_response(request, event, "left")


@login_required
@require_POST
def delete_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    if not can_edit_event(request.user, event):
        return event_action_response(
            request,
            event,
            "final" if event.final else "delete-denied",
        )

    event.delete()

    if is_htmx_request(request):
        return render_feedback(
            request,
            {
                "kind": "success",
                "title": "Aktion gelöscht.",
                "message": "Die Aktion wurde gelöscht.",
                "action_label": "Zur Liste",
                "action_url": reverse("events"),
                "action_htmx": False,
            },
        )

    return redirect(f"{reverse('events')}?{urlencode({'status': 'deleted'})}")


@login_required
@require_POST
def set_event_earnings(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    if not can_edit_event(request.user, event):
        return event_action_response(request, event, "edit-denied")

    form = SetEarningsForm(request.POST, instance=event)
    if form.is_valid():
        form.save()
        return event_action_response(request, event, "earnings")

    return render_event_details(request, event, earnings_form=form)


@login_required
@require_POST
def set_earnings_received(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    if not request.user.is_staff:
        return event_action_response(request, event, "edit-denied")

    form = SetEarningsReceivedForm(request.POST, instance=event)
    if form.is_valid():
        event = form.save(commit=False)
        # Unchecking "Eingezahlt" reopens the event; final tracks approval.
        event.final = event.earnings_received
        event.save()
        return event_action_response(request, event, "earnings-received")

    return render_event_details(request, event, earnings_received_form=form)


@login_required
@require_POST
def set_participation_times(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    if not can_manage_participation_times(request.user):
        raise PermissionDenied

    queryset = (
        EventParticipation.objects.filter(event=event)
        .select_related("user", "event")
        .order_by("user__first_name", "user__last_name", "user__username")
    )
    formset = ParticipationTimeFormSet(
        request.POST,
        instance=event,
        queryset=queryset,
    )
    if formset.is_valid():
        formset.save()
        return event_action_response(request, event, "participation-times")

    return render_event_details(
        request,
        event,
        participation_time_formset=formset,
    )


@login_required
@require_GET
def users(request):
    if not can_view_users(request):
        messages.error(request, "Du bist nicht berechtigt die Benutzer anzuzeigen.")
        return redirect_next_or(request, "main-page")

    users = set(User.objects.all())

    return render(request, "users.html", {"users": users})


@login_required
@require_GET
def user_details(request, user_id):
    if not can_view_users(request):
        messages.error(request, "Du bist nicht berechtigt die Benutzer anzuzeigen.")
        return redirect_next_or(request, "users")

    user = get_object_or_404(User, pk=user_id)
    total_hours = user.profile.total_hours()
    total_earnings = user.profile.total_earnings()
    event_participations = set(user.event_participations.all())
    can_edit = can_edit_user(request, user_id)
    can_change_password = request.user.is_staff or request.user.id == user_id

    return render(
        request,
        "components/_user_details.html",
        {
            "user": user,
            "total_hours": total_hours,
            "total_earnings": total_earnings,
            "event_participations": event_participations,
            "can_edit": can_edit,
            "can_change_password": can_change_password,
            "next_url": get_safe_next_url(request),
        },
    )


@login_required
def edit_user(request, user_id):
    if not can_edit_user(request, user_id):
        messages.error(
            request, "Du bist nicht berechtigt dieses Nutzerprofil zu bearbeiten"
        )
        return redirect_next_or(request, "users")

    user = get_object_or_404(User, pk=user_id)

    if request.method == "POST":
        form = UserProfileForm(request.POST, instance=user.profile)

        if form.is_valid():
            form.save()
            messages.success(request, "Profil erfolgreich aktualisiert.")
            return render(request, "components/_user_edit_success.html", {"user": user})
        else:
            messages.error(request, "Form ist invalide.")
            # render the partial with errors (status 400)
            return render(
                request,
                "components/_user_edit.html",
                {"form": form, "user": user, "next_url": get_safe_next_url(request)},
            )

    else:
        form = UserProfileForm(instance=user.profile)
        return render(
            request,
            "components/_user_edit.html",
            {"form": form, "user": user, "next_url": get_safe_next_url(request)},
        )


@login_required
@require_GET
def contact(request):
    return render(request, "contact.html")


@login_required
@require_GET
def polls(request):
    return render(request, "polls.html")
