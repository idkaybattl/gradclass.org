from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class Event(models.Model):
    class WorkKind(models.TextChoices):
        SCHOOL = "school", "Schulzeit (1×)"
        FREETIME = "freetime", "Freizeit (2×)"

    # set to true when approved by staff
    # makes model instance unchangable
    final = models.BooleanField(default=False)  # pyright: ignore[reportArgumentType]

    title = models.CharField(max_length=255)
    description = models.TextField()
    starting_date = models.DateTimeField()
    ending_date = models.DateTimeField()
    work_kind = models.CharField(
        max_length=20,
        choices=WorkKind,
        default=WorkKind.SCHOOL,
        verbose_name="Art der Arbeit",
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    creator = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="created_events"
    )

    manager = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="managed_events"
    )

    participants = models.ManyToManyField(
        User,
        through="EventParticipation",
        related_name="participating_events",
        blank=True,
    )

    earnings = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )
    earnings_received = models.BooleanField(default=False)  # pyright: ignore[reportArgumentType]

    def __str__(self):
        return str(self.title)

    class Meta:
        permissions = [
            ("create_event", "Aktionen erstellen"),
            ("edit_any_event", "Beliebige Aktionen bearbeiten"),
            ("delete_any_event", "Beliebige Aktionen löschen"),
            ("approve_event", "Aktionen freigeben"),
            ("manage_earnings", "Einnahmen verwalten"),
            ("manage_participation_times", "Arbeitszeiten verwalten"),
            ("manage_join_requests", "Teilnahmeanfragen verwalten"),
            ("bypass_event_creation_limit", "Erstellungslimit umgehen"),
        ]


class EventParticipation(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="event_participations"
    )

    participation_time = models.DurationField(null=True, blank=True)

    class Meta:
        unique_together = ("event", "user")

    def save(self, *args, **kwargs):
        # `timedelta(0)` is falsy; only a missing value means "use the full event".
        if self.participation_time is None:
            self.participation_time = (
                self.event.ending_date - self.event.starting_date  # pyright: ignore[reportAttributeAccessIssue]
            )
        super().save(*args, **kwargs)


class JoinRequest(models.Model):
    requestor = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("requestor", "event")

    def __str__(self):
        return f"JoinRequest({self.requestor}, {self.event})"
