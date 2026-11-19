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


class Abikasse(models.Model):
    goal = models.PositiveIntegerField()

    def total_earnings(self):
        return (
            Event.objects.filter(final=True)  # pyright: ignore[reportAttributeAccessIssue]
            .aggregate(Sum("earnings"))
            .get("earnings__sum", 0)
        ) or 0

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

    class Meta:
        permissions = [
            ("view_all_users", "Alle Nutzer:innen einsehen"),
            ("manage_users", "Nutzer:innen verwalten"),
            ("access_admin", "Adminbereich betreten"),
        ]


class Poll(models.Model):
    class Mode(models.TextChoices):
        FIXED = "fixed", "Feste Optionen"
        SUGGESTIONS = "suggestions", "Vorschläge"

    class Phase(models.TextChoices):
        DRAFT = "draft", "Entwurf"
        SUGGESTIONS = "suggestions", "Vorschläge"
        MODERATION = "moderation", "Moderation"
        VOTING = "voting", "Abstimmung"
        CLOSED = "closed", "Beendet"

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    creator = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="created_polls"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    mode = models.CharField(max_length=20, choices=Mode, default=Mode.FIXED)
    # Suggestions are visible to everyone from the start unless this is off.
    suggestions_public = models.BooleanField(default=True)  # pyright: ignore[reportArgumentType]
    # Results are visible to everyone, live and after close, unless this is off;
    # off makes the poll internal: only managers ever see results.
    results_public = models.BooleanField(default=True)  # pyright: ignore[reportArgumentType]

    published_at = models.DateTimeField(null=True, blank=True)
    suggestion_deadline = models.DateTimeField(null=True, blank=True)
    voting_started_at = models.DateTimeField(null=True, blank=True)
    voting_deadline = models.DateTimeField(null=True, blank=True)

    class Meta:
        permissions = [
            ("manage_polls", "Umfragen verwalten"),
        ]

    def __str__(self):
        return str(self.title)

    @property
    def phase(self):
        """Derive the phase from timestamps; there is no status column."""
        now = timezone.now()
        if self.published_at is None:
            return self.Phase.DRAFT
        if self.mode == self.Mode.SUGGESTIONS and now < self.suggestion_deadline:  # pyright: ignore[reportOperatorIssue]
            return self.Phase.SUGGESTIONS
        if self.voting_started_at is None:
            return self.Phase.MODERATION
        if now < self.voting_deadline:  # pyright: ignore[reportOperatorIssue]
            return self.Phase.VOTING
        return self.Phase.CLOSED


class Question(models.Model):
    class Kind(models.TextChoices):
        SINGLE_CHOICE = "single_choice", "Eine Antwort"

    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="questions")
    # v1 copies the poll title here; multi-question polls will use it directly.
    prompt = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=0)
    kind = models.CharField(max_length=20, choices=Kind, default=Kind.SINGLE_CHOICE)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return str(self.prompt)


class Option(models.Model):
    class State(models.TextChoices):
        SUGGESTED = "suggested", "Vorgeschlagen"
        APPROVED = "approved", "Freigegeben"
        REJECTED = "rejected", "Abgelehnt"
        MERGED = "merged", "Zusammengeführt"

    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="options"
    )
    label = models.CharField(max_length=120)
    order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suggested_options",
    )
    state = models.CharField(max_length=20, choices=State, default=State.APPROVED)
    merged_into = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merged_options",
    )

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return str(self.label)


class QuestionParticipation(models.Model):
    """The only place a voter is recorded; ballots have no user reference."""

    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="participations"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="poll_participations"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # HMAC(SECRET_KEY, user id + ballot token); verifies the cookie owner.
    token_hash = models.CharField(max_length=64)

    class Meta:
        unique_together = ("question", "user")


class Ballot(models.Model):
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="ballots"
    )
    token = models.CharField(max_length=64, unique=True)


class BallotVote(models.Model):
    ballot = models.ForeignKey(Ballot, on_delete=models.CASCADE, related_name="votes")
    option = models.ForeignKey(Option, on_delete=models.CASCADE, related_name="votes")

    class Meta:
        constraints = [
            # Single-choice: one row per ballot. Multi-select would drop this.
            models.UniqueConstraint(fields=["ballot"], name="unique_vote_per_ballot"),
        ]


class JoinRequest(models.Model):
    requestor = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("requestor", "event")

    def __str__(self):
        return f"JoinRequest({self.requestor}, {self.event})"
