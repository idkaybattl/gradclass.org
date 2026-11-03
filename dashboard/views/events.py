from datetime import timedelta
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from ..feedback import get_feedback, render_feedback
from ..forms import (
    EventForm,
    ParticipationTimeFormSet,
    SetEarningsForm,
    SetEarningsReceivedForm,
)
from ..http_helpers import (
    get_safe_back_url,
    get_safe_next_url,
    is_htmx_request,
    render_page_or_partial,
)
from ..intro import introduction_required
from ..models import Event, EventParticipation, JoinRequest
from ..notifications import Notification, NotificationVerbChoices
from ..permissions import (
    can_create_event,
    can_edit_event,
    can_manage_join_requests,
    can_manage_participation_times,
)
from ..services import save_event

MAX_PROJECTS_PER_HOUR = 5
MAX_PROJECTS_PER_DAY = 10


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


@login_required
@require_http_methods(["GET", "POST"])
def create_event(request):
    if not can_create_event(request.user):
        feedback = get_feedback(
            "create-denied",
            action_url=reverse("events"),
            action_label="Zur Liste",
        )
        if is_htmx_request(request):
            return render_feedback(request, feedback)

        return redirect(f"{reverse('events')}?{urlencode({'status': 'create-denied'})}")

    rate_limit_error = get_event_creation_limit_error(request.user)
    if rate_limit_error:
        feedback = get_feedback(
            "rate-limited",
            message=rate_limit_error,
            action_url=reverse("events"),
            action_label="Zur Liste",
        )
        if is_htmx_request(request):
            return render_feedback(request, feedback)

        return redirect(f"{reverse('events')}?{urlencode({'status': 'rate-limited'})}")

    if request.method == "GET":
        if not is_htmx_request(request):
            return redirect("events")
        form = EventForm(prefix="new", request_user=request.user)
    else:
        form = EventForm(
            data=request.POST,
            prefix="new",
            request_user=request.user,
        )

        if form.is_valid():
            event = save_event(form, request.user)

            if is_htmx_request(request):
                return render_feedback(
                    request,
                    get_feedback(
                        "created",
                        actions=[
                            {
                                "label": "Zur Aktion",
                                "url": event_detail_url(event),
                                "htmx": True,
                            },
                            {
                                "label": "Zur Liste",
                                "url": reverse("events"),
                            },
                        ],
                    ),
                )

            return redirect(event_detail_url(event, "created"))

    template = (
        "events/_event_form.html" if is_htmx_request(request) else "events/form.html"
    )
    return render(
        request,
        template,
        {
            "form": form,
            "mode": "create",
            "next_url": get_safe_next_url(request),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def edit_event(request, event_id):
    event = get_object_or_404(
        Event.objects.select_related("creator", "manager"), pk=event_id
    )
    if not can_edit_event(request.user, event):
        feedback = get_feedback(
            "edit-denied",
            action_url=event_detail_url(event),
            action_label="Zur Aktion",
            action_htmx=True,
        )
        if is_htmx_request(request):
            return render_feedback(request, feedback)

        return redirect(event_detail_url(event, "edit-denied"))

    back_url = get_safe_back_url(request) or event_detail_url(event)

    if request.method == "POST":
        form = EventForm(
            data=request.POST,
            instance=event,
            prefix=str(event.id),
            request_user=request.user,
        )

        if form.is_valid():
            saved_event = save_event(form, request.user)

            if is_htmx_request(request):
                return render_feedback(
                    request,
                    get_feedback(
                        "updated",
                        action_url=event_detail_url(saved_event),
                        action_label="Zur Aktion",
                        action_htmx=True,
                    ),
                )

            return redirect(event_detail_url(saved_event, "updated"))
    else:
        if not is_htmx_request(request):
            return redirect(event_detail_url(event))
        form = EventForm(
            instance=event,
            prefix=str(event.id),
            request_user=request.user,
        )

    template = (
        "events/_event_form.html" if is_htmx_request(request) else "events/form.html"
    )
    return render(
        request,
        template,
        {
            "form": form,
            "event": event,
            "mode": "edit",
            "back_url": back_url,
            "next_url": get_safe_next_url(request),
        },
    )


@login_required
@require_GET
@introduction_required
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
            "can_create_event": can_create_event(request.user),
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
        with transaction.atomic():
            formset.save()
        return event_action_response(request, event, "participation-times")

    return render_event_details(
        request,
        event,
        participation_time_formset=formset,
    )
