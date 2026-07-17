from .models import Event, EventParticipation
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


def save_event(form, user):
    # Adjust participation times when the event timeframe changes
    if form.instance.pk:
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
