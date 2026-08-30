from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from phonenumber_field.modelfields import PhoneNumberField

User = settings.AUTH_USER_MODEL


class Event(models.Model):
    # set to true when approved by staff
    # makes model instance unchangable
    final = models.BooleanField(default=False)  # pyright: ignore[reportArgumentType]

    title = models.CharField(max_length=255)
    description = models.TextField()
    starting_date = models.DateTimeField()
    ending_date = models.DateTimeField()
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


class EventParticipation(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="event_participations"
    )

    participation_time = models.DurationField(null=True, blank=True)

    class Meta:
        unique_together = ("event", "user")

    def save(self, *args, **kwargs):
        if not self.participation_time:
            self.participation_time = (
                self.event.ending_date - self.event.starting_date  # pyright: ignore[reportAttributeAccessIssue]
            )
        super().save(*args, **kwargs)


class Abikasse(models.Model):
    goal = models.PositiveIntegerField()

    def total_earnings(self):
        return (
            Event.objects.filter(final=True)  # pyright: ignore[reportAttributeAccessIssue]
            .aggregate(Sum("earnings"))
            .get("earnings__sum", 0)
        )

    def save(self, *args, **kwargs):
        # so that there is only one abikasse instance in the database
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "Abikasse"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    has_had_introduction = models.BooleanField(default=False)  # pyright: ignore[reportArgumentType]
    external_mail = models.EmailField(blank=True, null=True)
    phone_number = PhoneNumberField(blank=True, null=True)
    birthday = models.DateField(blank=True, null=True)

    bio = models.TextField(blank=True, null=True)

    def total_earnings(self):
        # TODO: currently total bullshit, need to accumulate individual earnings per event:
        # individual earnings being computed like:
        # fraction of total hours the individual worked on event times event earnings
        result = self.user.participating_events.aggregate(total=Sum("earnings"))  # pyright: ignore[reportAttributeAccessIssue]
        return result["total"] or 0

    def total_hours(self):
        # Build the queryset of relevant EventParticipation objects
        past_participations = self.user.event_participations.filter(  # pyright: ignore[reportAttributeAccessIssue]
            event__ending_date__lt=timezone.now(),  # only past events
            # event__final=True,  # only final events
        )

        # Aggregate the duration
        result = past_participations.aggregate(total=Sum("participation_time"))
        # If there are no matching rows, return a zero timedelta
        return result["total"] or timedelta(0)
        return result["total"] or timedelta(0)


class JoinRequest(models.Model):
    requestor = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("requestor", "event")

    def __str__(self):
        return f"JoinRequest({self.requestor}, {self.event})"
