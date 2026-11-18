from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..forms import ParticipationTimeFormSet
from ..models import Event, EventParticipation, JoinRequest
from ..notifications import Notification, NotificationVerbChoices
from .helpers import User, make_rep


class EventViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="student", password="password")
        self.other_user = User.objects.create_user(
            username="other", password="password"
        )
        self.rep = make_rep("rep")
        for user in (self.user, self.other_user, self.rep):
            user.profile.has_had_introduction = True
            user.profile.save(update_fields=["has_had_introduction"])

        now = timezone.now()
        self.own_past_event = self.create_event(
            "Meine alte Aktion",
            self.user,
            now - timedelta(days=2),
            now - timedelta(days=1),
        )
        self.other_past_event = self.create_event(
            "Fremde alte Aktion",
            self.other_user,
            now - timedelta(days=4),
            now - timedelta(days=3),
        )
        self.upcoming_event = self.create_event(
            "Kommende Aktion",
            self.other_user,
            now + timedelta(days=1),
            now + timedelta(days=2),
        )

    def create_event(self, title, creator, starting_date, ending_date):
        return Event.objects.create(
            title=title,
            description="",
            starting_date=starting_date,
            ending_date=ending_date,
            creator=creator,
            manager=creator,
        )

    def test_events_requires_login(self):
        response = self.client.get(reverse("events"))

        self.assertEqual(response.status_code, 302)

    def test_upcoming_page_renders_grid_and_upcoming_events(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("events-upcoming"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-events-grid")
        self.assertContains(response, self.upcoming_event.title)
        self.assertEqual(response.context["initial_filter"], "upcoming")

    def test_non_staff_sees_all_events(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("events"))

        self.assertContains(response, self.own_past_event.title)
        self.assertContains(response, self.other_past_event.title)
        self.assertContains(response, self.upcoming_event.title)

        events_by_id = {event.pk: event for event in response.context["events"]}
        self.assertTrue(events_by_id[self.own_past_event.pk].is_own)
        self.assertFalse(events_by_id[self.upcoming_event.pk].is_own)

    def test_manager_sees_past_event_they_manage(self):
        managed_event = self.create_event(
            "Verwaltete alte Aktion",
            self.other_user,
            timezone.now() - timedelta(days=6),
            timezone.now() - timedelta(days=5),
        )
        managed_event.manager = self.user
        managed_event.save()
        self.client.force_login(self.user)

        response = self.client.get(reverse("events"))

        self.assertContains(response, managed_event.title)
        managed = next(
            event
            for event in response.context["events"]
            if event.pk == managed_event.pk
        )
        self.assertTrue(managed.is_own)

    def test_events_own_preselects_own_filter(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("events-own"))

        self.assertTrue(response.context["own_only"])
        self.assertEqual(response.context["initial_filter"], "all")


class EventDetailViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="student", password="password")
        self.manager = User.objects.create_user(username="manager", password="password")
        self.rep = make_rep("rep")
        self.event = Event.objects.create(
            title="Sommerfest",
            description="Gemeinsam feiern.",
            starting_date=timezone.now() + timedelta(days=1),
            ending_date=timezone.now() + timedelta(days=1, hours=2),
            creator=self.manager,
            manager=self.manager,
        )

    def test_detail_renders_full_page_without_htmx(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("event-details", args=[self.event.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<html")
        self.assertContains(response, "data-event-detail")
        self.assertContains(response, "Sommerfest")

    def test_detail_renders_fragment_for_htmx(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("event-details", args=[self.event.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<html")
        self.assertNotContains(response, "overlay-close")
        self.assertContains(response, "data-event-detail")

    def test_detail_permission_flags(self):
        detail_url = reverse("event-details", args=[self.event.pk])

        self.client.force_login(self.user)
        response = self.client.get(detail_url, HTTP_HX_REQUEST="true")
        self.assertFalse(response.context["can_edit"])
        self.assertTrue(response.context["can_join"])
        self.assertFalse(response.context["can_leave"])

        EventParticipation.objects.create(event=self.event, user=self.user)
        response = self.client.get(detail_url, HTTP_HX_REQUEST="true")
        self.assertFalse(response.context["can_join"])
        self.assertTrue(response.context["can_leave"])

        self.client.force_login(self.manager)
        response = self.client.get(detail_url, HTTP_HX_REQUEST="true")
        self.assertTrue(response.context["can_edit"])
        self.assertTrue(response.context["can_join"])

        self.client.force_login(self.rep)
        response = self.client.get(detail_url, HTTP_HX_REQUEST="true")
        self.assertTrue(response.context["can_edit"])

        self.event.final = True
        self.event.save(update_fields=["final"])

        for user in (self.user, self.manager, self.rep):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(detail_url, HTTP_HX_REQUEST="true")

                self.assertFalse(response.context["can_edit"])
                self.assertFalse(response.context["can_join"])
                self.assertFalse(response.context["can_leave"])

    def test_join_creates_request_for_regular_user(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("event-join", args=[self.event.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anfrage gesendet")
        self.assertTrue(
            JoinRequest.objects.filter(requestor=self.user, event=self.event).exists()
        )

    def test_manager_joins_directly_without_request(self):
        self.event.participants.remove(self.manager)
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("event-join", args=[self.event.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Du nimmst jetzt teil")
        self.assertTrue(
            EventParticipation.objects.filter(
                event=self.event, user=self.manager
            ).exists()
        )

    def test_join_returns_error_for_past_event(self):
        self.event.starting_date = timezone.now() - timedelta(hours=1)
        self.event.ending_date = timezone.now() + timedelta(hours=1)
        self.event.save()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("event-join", args=[self.event.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertContains(response, "Das Projekt liegt in der Vergangenheit.")
        self.assertFalse(
            EventParticipation.objects.filter(event=self.event, user=self.user).exists()
        )

    def test_leave_only_removes_actual_participants(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("event-leave", args=[self.event.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertContains(response, "Du nimmst an diesem Projekt nicht teil.")

        EventParticipation.objects.create(event=self.event, user=self.user)
        response = self.client.post(
            reverse("event-leave", args=[self.event.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertContains(response, "Teilnahme beendet.")
        self.assertFalse(
            EventParticipation.objects.filter(event=self.event, user=self.user).exists()
        )

    def test_manager_can_delete_event(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("event-delete", args=[self.event.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aktion gelöscht.")
        self.assertFalse(Event.objects.filter(pk=self.event.pk).exists())

    def test_unrelated_user_cannot_delete_event(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("event-delete", args=[self.event.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertContains(
            response, "Du bist nicht berechtigt, diese Aktion zu löschen."
        )
        self.assertTrue(Event.objects.filter(pk=self.event.pk).exists())


class JoinRequestViewTests(TestCase):
    def setUp(self):
        self.requestor = User.objects.create_user(
            username="student", password="password"
        )
        self.manager = User.objects.create_user(username="manager", password="password")
        self.event = Event.objects.create(
            title="Sommerfest",
            description="",
            starting_date=timezone.now() + timedelta(days=1),
            ending_date=timezone.now() + timedelta(days=1, hours=2),
            creator=self.manager,
            manager=self.manager,
        )
        self.join_request = JoinRequest.objects.create(
            requestor=self.requestor, event=self.event
        )

    def test_join_request_requires_manager_or_staff(self):
        self.client.force_login(self.requestor)

        response = self.client.get(
            reverse("join-request-details", args=[self.join_request.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 403)

    def test_non_manager_cannot_accept_or_decline_join_request(self):
        self.client.force_login(self.requestor)

        for url_name in ("accept-join-request", "decline-join-request"):
            with self.subTest(url_name=url_name):
                response = self.client.post(
                    reverse(url_name, args=[self.join_request.pk]),
                    HTTP_HX_REQUEST="true",
                )

                self.assertEqual(response.status_code, 403)

        self.assertTrue(JoinRequest.objects.filter(pk=self.join_request.pk).exists())

    def test_join_request_renders_fragment_for_manager(self):
        self.client.force_login(self.manager)

        response = self.client.get(
            reverse("join-request-details", args=[self.join_request.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<html")
        self.assertNotContains(response, "overlay-close")
        self.assertContains(response, "möchte")
        self.assertContains(response, "Sommerfest")

    def test_accept_join_request_adds_participant_and_notifies_requestor(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("accept-join-request", args=[self.join_request.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anfrage angenommen.")
        self.assertTrue(
            EventParticipation.objects.filter(
                event=self.event, user=self.requestor
            ).exists()
        )
        self.assertFalse(JoinRequest.objects.filter(pk=self.join_request.pk).exists())
        self.assertTrue(
            Notification.objects.filter(
                user=self.requestor,
                verb=NotificationVerbChoices.EVENT_JOIN_REQUEST_ACCEPTED,
                object_id=self.event.pk,
            ).exists()
        )

    def test_accept_join_request_marks_manager_notification_read(self):
        notification = Notification.objects.get(
            user=self.manager,
            verb=NotificationVerbChoices.EVENT_JOIN_REQUEST,
            object_id=self.join_request.pk,
        )
        self.client.force_login(self.manager)

        self.client.post(
            reverse("accept-join-request", args=[self.join_request.pk]),
            HTTP_HX_REQUEST="true",
        )

        notification.refresh_from_db()
        self.assertTrue(notification.is_read)


class ParticipationTimeViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="student", password="password")
        self.rep = make_rep("rep")
        self.event = Event.objects.create(
            title="Arbeitseinsatz",
            description="",
            starting_date=timezone.now() - timedelta(days=2),
            ending_date=timezone.now() - timedelta(days=2) + timedelta(hours=4),
            creator=self.rep,
            manager=self.rep,
        )
        self.participation = EventParticipation.objects.create(
            event=self.event, user=self.user
        )

    def formset_data(self, values):
        formset = ParticipationTimeFormSet(instance=self.event)
        prefix = formset.prefix
        data = {
            f"{prefix}-TOTAL_FORMS": str(len(values)),
            f"{prefix}-INITIAL_FORMS": str(len(values)),
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
        }
        for index, (participation, value) in enumerate(values):
            hours, minutes = value.split(":", 1)
            data[f"{prefix}-{index}-id"] = str(participation.pk)
            data[f"{prefix}-{index}-participation_time_hours"] = hours
            data[f"{prefix}-{index}-participation_time_minutes"] = minutes
        return data

    def test_rep_detail_renders_split_duration_inputs(self):
        self.client.force_login(self.rep)

        response = self.client.get(reverse("event-details", args=[self.event.pk]))

        self.assertContains(response, "participation_time_hours")
        self.assertContains(response, "participation_time_minutes")
        self.assertContains(response, "money-field__suffix")

    def test_rep_can_set_zero_participation_time(self):
        self.client.force_login(self.rep)
        data = self.formset_data([(self.participation, "0:00")])

        response = self.client.post(
            reverse("set-participation-times", args=[self.event.pk]),
            data,
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Arbeitszeiten gespeichert.")
        self.participation.refresh_from_db()
        self.assertEqual(self.participation.participation_time, timedelta(0))

    def test_student_cannot_set_participation_times(self):
        self.client.force_login(self.user)
        data = self.formset_data([(self.participation, "1:00")])

        response = self.client.post(
            reverse("set-participation-times", args=[self.event.pk]), data
        )

        self.assertEqual(response.status_code, 403)

    def test_too_long_participation_time_rerenders_with_error(self):
        self.client.force_login(self.rep)
        data = self.formset_data([(self.participation, "99:00")])

        response = self.client.post(
            reverse("set-participation-times", args=[self.event.pk]),
            data,
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "darf nicht länger als die Aktion sein")

    def test_participation_save_keeps_zero_instead_of_full_duration(self):
        self.participation.participation_time = timedelta(0)
        self.participation.save()

        self.participation.refresh_from_db()
        self.assertEqual(self.participation.participation_time, timedelta(0))

    def test_total_hours_reflects_participation_times(self):
        self.participation.participation_time = timedelta(hours=1, minutes=30)
        self.participation.save()

        self.assertEqual(
            self.user.profile.total_hours(), timedelta(hours=1, minutes=30)
        )
