from datetime import datetime

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse

from .models import Event

User = settings.AUTH_USER_MODEL


class NotificationVerbChoices(models.TextChoices):
    ADDED_TO_PROJECT = ("added_to_event", "Added to event")
    REMOVED_FROM_PROJECT = ("removed_from_event", "Removed from event")
    TIME_FRAME_CHANGED = ("time_frame_changed", "Time frame changed")


class Notification(models.Model):
    # user is the person who received
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )

    verb = models.CharField(max_length=50, choices=NotificationVerbChoices.choices)

    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    target = GenericForeignKey("content_type", "object_id")

    # NEW: flexible payload for verb-specific data
    payload = models.JSONField(null=True, blank=True)

    is_read = models.BooleanField(default=False)  # pyright: ignore[reportArgumentType]
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.verb == NotificationVerbChoices.ADDED_TO_PROJECT and isinstance(
            self.target, Event
        ):
            return f"Du wurdest zu {self.target.title} hinzugefügt"
        elif self.verb == NotificationVerbChoices.REMOVED_FROM_PROJECT and isinstance(
            self.target, Event
        ):
            return f"Du wurdest aus {self.target.title} entfernt"
        elif self.verb == NotificationVerbChoices.TIME_FRAME_CHANGED and isinstance(
            self.target, Event
        ):
            p = self.payload or {}
            old_start = p.get("old_starting_date")
            old_end = p.get("old_ending_date")
            new_start = p.get("new_starting_date")
            new_end = p.get("new_ending_date")

            def _fmt(val):
                if not val:
                    return ""
                if isinstance(val, str):
                    try:
                        dt = datetime.fromisoformat(val)
                        return dt.strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        return val
                if isinstance(val, datetime):
                    return val.strftime("%Y-%m-%d %H:%M")
                return str(val)

            old_s = _fmt(old_start)
            old_e = _fmt(old_end)
            new_s = _fmt(new_start)
            new_e = _fmt(new_end)
            title = self.target.title
            return f"Zeitrahmen geändert: {title} von {old_s} - {old_e} zu {new_s} - {new_e}"
        else:
            return f"{self.verb} {self.target.__str__()}"

    def get_url(self) -> str:
        if self.verb in (
            NotificationVerbChoices.ADDED_TO_PROJECT,
            NotificationVerbChoices.REMOVED_FROM_PROJECT,
            NotificationVerbChoices.TIME_FRAME_CHANGED,
        ) and isinstance(self.target, Event):
            return reverse("event-detail", kwargs={"event_id": self.target.pk})

        # fallback
        return reverse("main-page")

    def open_as_popup(self) -> bool:
        if self.verb in (
            NotificationVerbChoices.ADDED_TO_PROJECT,
            NotificationVerbChoices.REMOVED_FROM_PROJECT,
            NotificationVerbChoices.TIME_FRAME_CHANGED,
        ) and isinstance(self.target, Event):
            return True

        return False


def notify_participants(event: Event, old, new):
    added = new - old
    removed = old - new

    for participant in added:
        # Notify the participant that they have been added to an event
        Notification(
            user=participant,
            verb=NotificationVerbChoices.ADDED_TO_PROJECT,
            target=event,
        ).save()

    for participant in removed:
        # Notify the participant that they have been removed from an event
        Notification(
            user=participant,
            verb=NotificationVerbChoices.REMOVED_FROM_PROJECT,
            target=event,
        ).save()


def notify_time_frame_changed(
    event,
    recipients,
    old_starting_date,
    old_ending_date,
    new_starting_date,
    new_ending_date,
):
    payload = {
        "old_starting_date": old_starting_date.isoformat()
        if old_starting_date
        else None,
        "old_ending_date": old_ending_date.isoformat() if old_ending_date else None,
        "new_starting_date": new_starting_date.isoformat()
        if new_starting_date
        else None,
        "new_ending_date": new_ending_date.isoformat() if new_ending_date else None,
    }

    for recipient in recipients:
        Notification(
            user=recipient,
            verb=NotificationVerbChoices.TIME_FRAME_CHANGED,
            target=event,
            payload=payload,
        ).save()
