import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import (
    STUDENT_GROUP_NAME,
    AbiballConfig,
    AbikasseEntry,
    Ballot,
    BallotVote,
    Event,
    EventParticipation,
    Option,
    Poll,
    Question,
    QuestionParticipation,
)
from .notifications import notify_participants, notify_time_frame_changed

User = get_user_model()

CENT = Decimal("0.01")
DEFAULT_POINT_VALUE = Decimal("2.00")
SECONDS_PER_HOUR = Decimal(3600)


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


def close_poll_suggestions(poll):
    """End the suggestion phase early; moderation starts immediately."""
    if poll.phase != Poll.Phase.SUGGESTIONS:
        raise ValidationError("Die Vorschlagsphase läuft nicht.")

    poll.suggestions_closed_at = timezone.now()
    poll.save(update_fields=["suggestions_closed_at"])
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


def close_poll_voting(poll):
    """End voting early; results become final."""
    if poll.phase != Poll.Phase.VOTING:
        raise ValidationError("Die Abstimmung läuft nicht.")

    poll.voting_closed_at = timezone.now()
    poll.save(update_fields=["voting_closed_at"])
    return poll


@transaction.atomic
def save_poll(form, user):
    poll = form.save(commit=False)
    if poll.pk is None:
        poll.creator = user
    elif poll.phase != Poll.Phase.DRAFT:
        raise ValidationError("Nur Entwürfe können bearbeitet werden.")
    poll.save()

    question, _ = Question.objects.get_or_create(
        poll=poll, defaults={"prompt": poll.title}
    )
    if question.prompt != poll.title:
        question.prompt = poll.title
        question.save(update_fields=["prompt"])

    question.options.all().delete()
    for index, label in enumerate(form.cleaned_data["option_labels"]):
        Option.objects.create(question=question, label=label, order=index)
    return poll


def add_poll_suggestion(question, user, label):
    existing = question.options.filter(
        created_by=user,
        state__in=[Option.State.SUGGESTED, Option.State.APPROVED],
    ).count()
    limit = question.poll.max_suggestions_per_user
    if existing >= limit:
        raise ValidationError(f"Du kannst höchstens {limit} Vorschläge machen.")

    return Option.objects.create(
        question=question,
        label=label,
        created_by=user,
        state=Option.State.APPROVED,
    )


BALLOT_COOKIE_PREFIX = "poll_ballot_"
BALLOT_SALT = "dashboard.poll-ballot"


def ballot_cookie_name(question):
    return f"{BALLOT_COOKIE_PREFIX}{question.pk}"


def _hash_ballot_token(user, token):
    message = f"{user.pk}:{token}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def read_poll_vote(question, user, token):
    """Option id of the ballot the cookie points to, if it is this user's."""
    if not token:
        return None

    participation = QuestionParticipation.objects.filter(
        question=question, user=user
    ).first()
    if participation is None or not hmac.compare_digest(
        participation.token_hash, _hash_ballot_token(user, token)
    ):
        return None

    vote = (
        BallotVote.objects.filter(ballot__question=question, ballot__token=token)
        .values_list("option_id", flat=True)
        .first()
    )
    return vote


def cast_poll_vote(question, option, user, token=None):
    """Create or change the user's vote.

    Returns ``(status, new_token)`` where status is ``voted``, ``vote-changed``
    or ``ballot-lost`` and ``new_token`` is only set on the first vote.
    """
    participation = QuestionParticipation.objects.filter(
        question=question, user=user
    ).first()

    if participation is not None:
        if not token or not hmac.compare_digest(
            participation.token_hash, _hash_ballot_token(user, token)
        ):
            return "ballot-lost", None

        ballot = Ballot.objects.filter(question=question, token=token).first()
        if ballot is None:
            return "ballot-lost", None

        BallotVote.objects.update_or_create(ballot=ballot, defaults={"option": option})
        return "vote-changed", None

    new_token = secrets.token_hex(32)
    with transaction.atomic():
        ballot = Ballot.objects.create(question=question, token=new_token)
        BallotVote.objects.create(ballot=ballot, option=option)
        QuestionParticipation.objects.create(
            question=question,
            user=user,
            token_hash=_hash_ballot_token(user, new_token),
        )
    return "voted", new_token


# Abikasse


def abikasse_balance():
    totals = AbikasseEntry.objects.aggregate(
        income=Sum("amount", filter=Q(kind=AbikasseEntry.Kind.INCOME)),
        expenses=Sum("amount", filter=Q(kind=AbikasseEntry.Kind.EXPENSE)),
    )
    return (totals["income"] or Decimal("0")) - (totals["expenses"] or Decimal("0"))


def sync_event_earnings_entry(event):
    """Keep the automatic income entry in sync with an event's earnings."""
    if not event.final or event.earnings is None or event.earnings <= 0:
        AbikasseEntry.objects.filter(
            event=event, source=AbikasseEntry.Source.EVENT
        ).delete()
        return None

    entry, _ = AbikasseEntry.objects.update_or_create(
        event=event,
        defaults={
            "kind": AbikasseEntry.Kind.INCOME,
            "amount": event.earnings,
            "description": event.title,
            "date": timezone.localdate(event.ending_date),
            "source": AbikasseEntry.Source.EVENT,
        },
    )
    return entry


def _duration_hours(value):
    if value is None:
        return Decimal("0")
    seconds = value.days * 86400 + value.seconds
    return (
        Decimal(seconds) + Decimal(value.microseconds) / Decimal(1_000_000)
    ) / SECONDS_PER_HOUR


def work_points(user):
    total = Decimal("0")
    participations = EventParticipation.objects.filter(
        user=user,
        event__final=True,
        event__ending_date__lt=timezone.now(),
    ).select_related("event")

    for participation in participations:
        hours = _duration_hours(participation.participation_time)
        if hours <= 0:
            continue
        factor = (
            Decimal("2")
            if participation.event.work_kind == Event.WorkKind.FREETIME
            else Decimal("1")
        )
        total += hours * factor

    return int(total.to_integral_value(rounding=ROUND_FLOOR))


def _event_hours(event):
    total = Decimal("0")
    durations = EventParticipation.objects.filter(
        event=event, participation_time__isnull=False
    ).values_list("participation_time", flat=True)
    for duration in durations:
        total += _duration_hours(duration)
    return total


def earnings_share(user):
    total = Decimal("0")
    participations = EventParticipation.objects.filter(
        user=user,
        event__final=True,
        event__ending_date__lt=timezone.now(),
        event__earnings__gt=0,
        participation_time__isnull=False,
    ).select_related("event")

    for participation in participations:
        user_hours = _duration_hours(participation.participation_time)
        if user_hours <= 0:
            continue
        event_hours = _event_hours(participation.event)
        if event_hours <= 0:
            continue
        total += user_hours / event_hours * participation.event.earnings

    return total


def get_abiball_config():
    return AbiballConfig.objects.filter(pk=1).first()


def current_point_value():
    config = get_abiball_config()
    return config.point_value if config is not None else DEFAULT_POINT_VALUE


def total_points(user, *, point_value=None):
    if point_value is None:
        point_value = current_point_value()
    points = Decimal(work_points(user)) + earnings_share(user) / point_value
    return int(points.to_integral_value(rounding=ROUND_FLOOR))


def active_students():
    # "Student" is a population definition, not an authorization check.
    return (
        User.objects.filter(is_active=True, groups__name=STUDENT_GROUP_NAME)
        .select_related("profile")
        .distinct()
    )


def _ticket_count(user, config):
    profile = getattr(user, "profile", None)
    if profile is None:
        return config.default_ticket_count
    return profile.ticket_count


def _money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class TicketBase:
    base: Decimal
    n_est: int
    total_credit: Decimal
    available: Decimal
    required: Decimal
    point_value: Decimal
    default_ticket_count: int


@dataclass(frozen=True)
class TicketEstimate:
    base: Decimal
    n_est: int
    available: Decimal
    required: Decimal
    points: int
    credit: Decimal
    ticket_count: int
    price: Decimal | None
    total: Decimal | None
    capped: bool
    computed_at: date


def ticket_base():
    config = get_abiball_config()
    if config is None or config.fixed_costs is None or config.per_head_costs is None:
        return None

    students = list(active_students())
    n_est = sum(_ticket_count(student, config) for student in students)
    if n_est <= 0:
        return None

    total_credit = sum(
        (
            Decimal(total_points(student, point_value=config.point_value))
            * config.point_value
            for student in students
        ),
        Decimal("0"),
    )
    available = abikasse_balance()
    required = config.fixed_costs + config.per_head_costs * n_est - available
    base = (required + total_credit) / n_est

    return TicketBase(
        base=base,
        n_est=n_est,
        total_credit=total_credit,
        available=available,
        required=required,
        point_value=config.point_value,
        default_ticket_count=config.default_ticket_count,
    )


def ticket_estimate(user):
    base = ticket_base()
    if base is None:
        return None

    profile = getattr(user, "profile", None)
    ticket_count = (
        profile.ticket_count if profile is not None else base.default_ticket_count
    )
    points = total_points(user, point_value=base.point_value)
    # Credit uses the displayed (floored) points, so it can be up to one
    # point value below the exact earnings share.
    credit = Decimal(points) * base.point_value

    if ticket_count <= 0:
        price = None
        total = None
        capped = False
    else:
        raw_price = base.base - credit / ticket_count
        capped = raw_price < 0
        price = _money(max(raw_price, Decimal("0")))
        total = _money(max(ticket_count * base.base - credit, Decimal("0")))

    return TicketEstimate(
        base=_money(base.base),
        n_est=base.n_est,
        available=base.available,
        required=base.required,
        points=points,
        credit=credit,
        ticket_count=ticket_count,
        price=price,
        total=total,
        capped=capped,
        computed_at=timezone.localdate(),
    )
