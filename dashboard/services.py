from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import Event, EventParticipation, Option, Poll
from .notifications import notify_participants, notify_time_frame_changed


def update_participants(event, selected_users):
    # Remove old participants
    EventParticipation.objects.filter(event=event).exclude(  # pyright: ignore[rparticipationortAttributeAccessIssue]
        user__in=selected_users
    ).delete()

    # Add new participants
    existing = set(event.participants.values_list("id", flat=True))
    for user in selected_users:
        if user.id not in existing:
            EventParticipation.objects.create(  # pyright: ignore[rparticipationortAttributeAccessIssue]
                event=event,
                user=user,
            )


@transaction.atomic
def save_event(form, user):
    is_creation = not form.instance.pk

    # Adjust participation times when the event timeframe changes
    if not is_creation:
        # Load a fresh copy from the database to capture the pre-save values.
        # Accessing `form.instance` can yield the same in-memory object that the
        # form may already have modified, so read from DB to get the real old
        # values.
        previous_event = Event.objects.get(pk=form.instance.pk)
        old_starting_datetime = previous_event.starting_date
        old_ending_datetime = previous_event.ending_date
        old_duration = old_ending_datetime - old_starting_datetime
        old = set(previous_event.participants.all())
    else:
        old_starting_datetime = None
        old_ending_datetime = None
        old_duration = None
        old = set()

    event = form.save(commit=False)
    if is_creation:
        event.creator = user
    event.save()

    update_participants(event, form.cleaned_data["participants"])

    # Compute the new max duration of the event
    new_duration = event.ending_date - event.starting_date

    # Update participation times
    # - If a participation_time was equal to the old max duration, keparticipation it at the new max duration
    # - Ensure no participation_time exceeds the new event duration
    # - If participation_time is null, set it to the new max duration
    participations = EventParticipation.objects.select_related("event").filter(
        event=event
    )

    to_update = []
    for participation in participations:
        original = participation.participation_time
        changed = False

        # Keep max-time participations at max if timeframe changed
        if (
            old_duration is not None
            and original is not None
            and original == old_duration
        ):
            participation.participation_time = new_duration
            changed = True

        # Default/null -> set to new max duration
        if original is None:
            participation.participation_time = new_duration
            changed = True

        # Clamp to not exceed the event duration
        if (
            participation.participation_time is not None
            and participation.participation_time > new_duration
        ):
            participation.participation_time = new_duration
            changed = True

        if changed:
            to_update.append(participation)

    if to_update:
        EventParticipation.objects.bulk_update(to_update, ["participation_time"])  # pyright: ignore[rparticipationortArgumentType]

    # Notify participants of changes in timeframe
    new_starting_datetime = event.starting_date
    new_ending_datetime = event.ending_date

    if old_duration and (
        old_starting_datetime != event.starting_date
        or old_ending_datetime != event.ending_date
    ):
        notify_time_frame_changed(
            event,
            event.participants.all(),
            old_starting_datetime,
            old_ending_datetime,
            new_starting_datetime,
            new_ending_datetime,
        )

    new = set(event.participants.all())

    notify_participants(event, old, new)

    return event


def build_password_reset_url(user, request):
    """Absolute one-time reset link, for out-of-band delivery."""
    return request.build_absolute_uri(
        reverse(
            "password-reset-confirm",
            kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": default_token_generator.make_token(user),
            },
        )
    )


def start_poll_suggestions(poll):
    """Draft -> suggestions. Only suggestion polls can enter this phase."""
    if poll.phase != Poll.Phase.DRAFT or poll.mode != Poll.Mode.SUGGESTIONS:
        raise ValidationError("Für diese Umfrage können keine Vorschläge starten.")

    now = timezone.now()
    if not poll.suggestion_deadline or poll.suggestion_deadline <= now:
        raise ValidationError("Die Vorschlagsfrist liegt nicht in der Zukunft.")

    poll.published_at = now
    poll.save(update_fields=["published_at"])
    return poll


def start_poll_voting(poll):
    """Draft (fixed) or moderation (suggestions) -> voting."""
    if poll.mode == Poll.Mode.SUGGESTIONS:
        if poll.phase != Poll.Phase.MODERATION:
            raise ValidationError("Die Vorschlagsphase ist noch nicht beendet.")
    elif poll.phase != Poll.Phase.DRAFT:
        raise ValidationError("Die Abstimmung läuft bereits.")

    now = timezone.now()
    if not poll.voting_deadline or poll.voting_deadline <= now:
        raise ValidationError("Die Abstimmungsfrist liegt nicht in der Zukunft.")

    approved = Option.objects.filter(
        question__poll=poll, state=Option.State.APPROVED
    ).count()
    if approved < 2:
        raise ValidationError("Es braucht mindestens zwei Optionen.")

    update_fields = ["voting_started_at"]
    if poll.published_at is None:
        poll.published_at = now
        update_fields.append("published_at")
    poll.voting_started_at = now
    poll.save(update_fields=update_fields)
    return poll
