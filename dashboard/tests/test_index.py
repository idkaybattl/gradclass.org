from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import Event, Poll
from .helpers import User


def make_student(username="student"):
    user = User.objects.create_user(username=username, password="password")
    user.profile.has_had_introduction = True
    user.profile.save(update_fields=["has_had_introduction"])
    return user


def make_event(user, title, *, starts_in, ends_in):
    now = timezone.now()
    return Event.objects.create(
        title=title,
        description="",
        starting_date=now + starts_in,
        ending_date=now + ends_in,
        creator=user,
        manager=user,
    )


def make_poll(user, title, *, phase):
    now = timezone.now()
    poll = Poll.objects.create(title=title, creator=user)
    if phase == Poll.Phase.DRAFT:
        return poll

    poll.published_at = now - timedelta(days=1)
    if phase == Poll.Phase.VOTING:
        poll.voting_started_at = now - timedelta(hours=1)
        poll.voting_deadline = now + timedelta(days=1)
    if phase == Poll.Phase.CLOSED:
        poll.voting_started_at = now - timedelta(hours=1)
        poll.voting_deadline = now - timedelta(minutes=1)
        poll.voting_closed_at = now
    poll.save()
    return poll


class IndexActivityTests(TestCase):
    def setUp(self):
        self.user = make_student()
        self.client.force_login(self.user)

    def test_lists_upcoming_events_only(self):
        upcoming = make_event(
            self.user,
            "Kommende Aktion",
            starts_in=timedelta(days=1),
            ends_in=timedelta(days=1, hours=1),
        )
        past = make_event(
            self.user,
            "Vergangene Aktion",
            starts_in=timedelta(days=-2),
            ends_in=timedelta(days=-2, hours=-1),
        )

        response = self.client.get(reverse("main-page"))

        self.assertContains(response, upcoming.title)
        self.assertNotContains(response, past.title)

    def test_lists_open_polls_only(self):
        open_poll = make_poll(self.user, "Offene Umfrage", phase=Poll.Phase.VOTING)
        closed_poll = make_poll(self.user, "Beendet", phase=Poll.Phase.CLOSED)
        draft_poll = make_poll(self.user, "Entwurf", phase=Poll.Phase.DRAFT)

        response = self.client.get(reverse("main-page"))

        self.assertContains(response, open_poll.title)
        self.assertNotContains(response, closed_poll.title)
        self.assertNotContains(response, draft_poll.title)
