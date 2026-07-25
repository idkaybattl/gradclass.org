from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.db.models import Q
from django.http.response import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from .forms import EventForm, SetEarningsForm, SetEarningsReceivedForm, UserProfileForm
from .models import Abikasse, Event, EventParticipation
from .notifications import Notification
from .services import save_event

User = get_user_model()
MAX_PROJECTS_PER_HOUR = 5
MAX_PROJECTS_PER_DAY = 10


def can_edit_event(user, event):
    return not event.final and (event.creator_id == user.id or user.is_staff)


def can_view_all_events(request):
    return request.user.is_staff


def can_view_users(request):
    # currently everybody can view all users
    return True


def can_edit_user(request, user_id):
    return request.user.is_staff or request.user.id == user_id


def get_safe_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next")
    if not next_url:
        return None

    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url

    return None


def redirect_next_or(request, fallback, **kwargs):
    next_url = get_safe_next_url(request)
    if next_url:
        return redirect(next_url)

    return redirect(fallback, **kwargs)


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
            "can_view_all_events": can_view_all_events(request),
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


@login_required
@require_POST
def password_change(request):
    form = PasswordChangeForm(request.user, request.POST)
    if form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Dein Passwort wurde erfolgreich geändert.")
        return JsonResponse({"success": True})


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
    user = request.user
    notifications = Notification.objects.filter(user=user, is_read=False).order_by(
        "-created_at"
    )
    return render(
        request, "components/notifications.html", {"notifications": notifications}
    )


@login_required
@require_POST
def mark_all_notifications_as_read(request):
    user = request.user
    notifications = Notification.objects.filter(user=user, is_read=False)
    notifications.update(is_read=True)
    return JsonResponse({"success": True})


@login_required
@require_POST
def mark_notification_as_read(request, notification_id):
    user = request.user
    notification = Notification.objects.get(id=notification_id, user=user)
    notification.is_read = True
    notification.save()
    return JsonResponse({"success": True})


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
        status=400,
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

            return redirect_next_or(request, "events")
        else:
            messages.error(request, "Form ist invalide.")

        return render(
            request,
            "events/_event_edit_popup.html",
            {"form": form, "event": event, "next_url": get_safe_next_url(request)},
            status=400,
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
    if mode == "upcoming":
        events = (
            Event.objects.filter(ending_date__gt=timezone.now())
            .distinct()
            .select_related("creator")
            .prefetch_related("participants")
            .order_by("starting_date")
        )

    elif mode == "own":
        events = (
            Event.objects.filter(Q(participants=request.user) | Q(creator=request.user))
            .distinct()
            .select_related("creator")
            .prefetch_related("participants")
            .order_by("starting_date")
        )

    # mode "all"
    else:
        if request.user.is_staff:
            events = (
                Event.objects.all()
                .distinct()
                .select_related("creator")
                .prefetch_related("participants")
                .order_by("starting_date")
            )
        else:
            events = (
                Event.objects.filter(
                    Q(participants=request.user)  # pyright: ignore[reportOperatorIssue]
                    | Q(creator=request.user)
                    | Q(ending_date__gt=timezone.now())
                )
                .distinct()
                .select_related("creator")
                .prefetch_related("participants")
                .order_by("starting_date")
            )

    can_view_all_events = request.user.is_staff

    return render(
        request,
        "events.html",
        {
            "events": events,
            "can_view_all_events": can_view_all_events,
        },
    )


@login_required
@require_GET
def event_details(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    can_edit = can_edit_event(request.user, event)
    is_participant = event.participants.filter(pk=request.user.pk).exists()
    can_delete = can_edit
    can_leave = is_participant and not event.final
    can_join = not is_participant and not event.final
    can_approve_payment = request.user.is_staff
    earnings_form = SetEarningsForm(instance=event)
    earnings_received_form = SetEarningsReceivedForm(instance=event)

    return render(
        request,
        "events/_event_details_popup.html",
        {
            "event": event,
            "can_edit": can_edit,
            "is_participant": is_participant,
            "can_delete": can_delete,
            "can_leave": can_leave,
            "can_join": can_join,
            "can_approve_payment": can_approve_payment,
            "next_url": get_safe_next_url(request),
            "earnings_form": earnings_form,
            "earnings_received_form": earnings_received_form,
        },
    )


@login_required
@require_POST
def join_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    if event.final:
        messages.error(request, "Dieses Projekt ist bereits abgeschlossen.")
    elif event.starting_date < timezone.now():
        messages.error(request, "Das Projekt liegt in der Vergangenheit")

    else:
        if event.participants.filter(pk=request.user.pk).exists():
            messages.error(request, "Du nimmst an diesem Projekt bereits teil.")
        else:
            participation = EventParticipation.objects.create(  # pyright: ignore[reportAttributeAccessIssue]
                event=event,
                user=request.user,
            )
            participation.save()
            messages.success(request, "Du nimmst jetzt Teil.")

    return redirect_next_or(request, "events")


@login_required
@require_POST
def leave_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    if event.final:
        messages.error(request, "Dieses Projekt ist bereits abgeschlossen.")
    else:
        if not event.participants.filter(pk=request.user.pk).exists():
            messages.error(request, "Du nimmst an diesem Projekt nicht teil.")
        else:
            messages.success(request, "Du hast deine Teilnahme beendet.")
        # remove participant in either case just in case
        event.participants.remove(request.user)

    return redirect_next_or(request, "events")


@login_required
@require_POST
def delete_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    if event.final:
        messages.error(request, "Dieses Projekt ist bereits abgeschlossen.")
    elif not request.user.is_staff and not request.user == event.creator:
        messages.error(request, "Du bist nicht berechtigt das Projekt zu löschen")
    else:
        event.delete()
        messages.success(request, "Projekt erfolgreich gelöscht")

    return redirect_next_or(request, "events-upcoming")


@login_required
@require_POST
def set_event_earnings(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    if not can_edit_event(request.user, event):
        messages.error(request, "Du bist nicht berechtigt das Projekt zu bearbeiten.")
    else:
        form = SetEarningsForm(
            request.POST, instance=get_object_or_404(Event, id=event_id)
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Einnahmen erfolgreich gesetzt.")

    return redirect_next_or(request, "events-own")


@login_required
@require_POST
def set_earnings_received(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    if not request.user.is_staff:
        messages.error(request, "Du bist nicht berechtigt das Projekt zu bearbeiten.")

    else:
        form = SetEarningsReceivedForm(
            request.POST, instance=get_object_or_404(Event, id=event_id)
        )
        if form.is_valid():
            event = form.save(commit=False)
            event.final = event.earnings_received
            event.save()
            messages.success(request, "Einnahmen erfolgreich gesetzt.")

    return redirect_next_or(request, "events")


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

    return render(
        request,
        "components/_user_details.html",
        {
            "user": user,
            "total_hours": total_hours,
            "total_earnings": total_earnings,
            "event_participations": event_participations,
            "can_edit": can_edit,
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
            return redirect_next_or(request, "users")
        else:
            messages.error(request, "Form ist invalide.")
            # render the partial with errors (status 400)
            return render(
                request,
                "components/_user_edit.html",
                {"form": form, "user": user, "next_url": get_safe_next_url(request)},
                status=400,
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
