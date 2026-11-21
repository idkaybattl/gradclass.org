from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL

OPTION_LABEL_MAX_LENGTH = 120


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
    max_suggestions_per_user = models.PositiveIntegerField(default=3)
    # Suggestions are visible to everyone from the start unless this is off.
    suggestions_public = models.BooleanField(default=True)  # pyright: ignore[reportArgumentType]
    # Results are visible to everyone, live and after close, unless this is off;
    # off makes the poll internal: only managers ever see results.
    results_public = models.BooleanField(default=True)  # pyright: ignore[reportArgumentType]

    published_at = models.DateTimeField(null=True, blank=True)
    suggestion_deadline = models.DateTimeField(null=True, blank=True)
    suggestions_closed_at = models.DateTimeField(null=True, blank=True)
    voting_started_at = models.DateTimeField(null=True, blank=True)
    voting_deadline = models.DateTimeField(null=True, blank=True)
    voting_closed_at = models.DateTimeField(null=True, blank=True)

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
        if (
            self.mode == self.Mode.SUGGESTIONS
            and self.suggestions_closed_at is None
            and now < self.suggestion_deadline  # pyright: ignore[reportOperatorIssue]
        ):
            return self.Phase.SUGGESTIONS
        if self.voting_closed_at is not None:
            return self.Phase.CLOSED
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
    label = models.CharField(max_length=OPTION_LABEL_MAX_LENGTH)
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
