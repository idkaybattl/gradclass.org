from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from .durations import split_duration
from .forms import (
    DurationHMField,
    DurationHMInput,
    EventForm,
    ParticipationTimeFormSet,
    SetEarningsForm,
)
from .models import Abikasse, Event, EventParticipation, JoinRequest
from .notifications import Notification, NotificationVerbChoices
from .views.events import MAX_PROJECTS_PER_HOUR

User = get_user_model()


class NotificationViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="student", password="password")
        self.other_user = User.objects.create_user(
            username="other", password="password"
        )
        self.event = self.create_event()
        self.notification = Notification.objects.create(
            user=self.user,
            verb=NotificationVerbChoices.ADDED_TO_EVENT,
            target=self.event,
        )
        self.client.force_login(self.user)

    def create_event(self, title="Sommerfest"):
        return Event.objects.create(
            title=title,
            description="",
            starting_date=timezone.now(),
            ending_date=timezone.now() + timedelta(hours=1),
            creator=self.user,
            manager=self.user,
        )

    def test_base_renders_notifications_panel_and_unread_badge(self):
        self.user.profile.has_had_introduction = True
        self.user.profile.save()

        response = self.client.get(reverse("main-page"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="notifications-content"')
        self.assertContains(response, 'id="overlay-content"')
        self.assertContains(response, "<p>Mitteilungen werden geladen …</p>")
        self.assertContains(response, "notification-badge")
        self.assertContains(response, f'hx-get="{reverse("notifications")}"')

    def test_orphaned_notification_does_not_break_panel(self):
        join_request = JoinRequest.objects.create(requestor=self.user, event=self.event)
        Notification.objects.create(
            user=self.user,
            verb=NotificationVerbChoices.EVENT_JOIN_REQUEST,
            target=join_request,
        )
        join_request.delete()

        response = self.client.get(reverse("notifications"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "nicht mehr verfügbar")

    def test_notifications_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse("notifications"))

        self.assertEqual(response.status_code, 302)

    def test_notifications_only_lists_unread_notifications(self):
        read_event = self.create_event("Alte Aktion")
        Notification.objects.create(
            user=self.user,
            verb=NotificationVerbChoices.ADDED_TO_EVENT,
            target=read_event,
            is_read=True,
        )

        response = self.client.get(reverse("notifications"))

        self.assertContains(response, "Sommerfest")
        self.assertContains(response, "Gelesen")
        self.assertNotContains(response, "Alte Aktion")
        self.assertNotContains(response, "Keine ungelesenen Mitteilungen.")

    def test_event_notification_opens_event_details_in_overlay(self):
        response = self.client.get(reverse("notifications"))

        self.assertContains(
            response,
            f'hx-get="{reverse("event-details", args=[self.event.pk])}"',
        )
        self.assertContains(response, 'data-overlay-open="overlay"')
        self.assertContains(response, 'hx-target="#overlay-content"')

    def test_join_request_notification_opens_request_in_overlay(self):
        join_request = JoinRequest.objects.create(
            requestor=self.other_user, event=self.event
        )
        Notification.objects.create(
            user=self.user,
            verb=NotificationVerbChoices.EVENT_JOIN_REQUEST,
            target=join_request,
        )

        response = self.client.get(reverse("notifications"))

        self.assertContains(
            response,
            f'hx-get="{reverse("join-request-details", args=[join_request.pk])}"',
        )

    def test_mark_notification_as_read_returns_updated_panel(self):
        response = self.client.post(
            reverse("mark-notification-as-read", args=[self.notification.pk]),
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="notifications-content",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Keine ungelesenen Mitteilungen.")
        self.assertContains(response, 'hx-swap-oob="outerHTML"')
        self.notification.refresh_from_db()
        self.assertTrue(self.notification.is_read)

    def test_mark_all_notifications_as_read_keeps_other_users_unread(self):
        other_notification = Notification.objects.create(
            user=self.other_user,
            verb=NotificationVerbChoices.ADDED_TO_EVENT,
            target=self.event,
        )

        response = self.client.post(
            reverse("mark-all-notifications-as-read"), HTTP_HX_REQUEST="true"
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "notification-badge")
        self.notification.refresh_from_db()
        other_notification.refresh_from_db()
        self.assertTrue(self.notification.is_read)
        self.assertFalse(other_notification.is_read)

    def test_mark_notification_as_read_redirects_without_htmx(self):
        response = self.client.post(
            reverse("mark-notification-as-read", args=[self.notification.pk])
        )

        self.assertRedirects(
            response, reverse("main-page"), fetch_redirect_response=False
        )


class EventViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="student", password="password")
        self.other_user = User.objects.create_user(
            username="other", password="password"
        )
        self.staff = User.objects.create_user(
            username="staff", password="password", is_staff=True
        )
        for user in (self.user, self.other_user, self.staff):
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

    def test_staff_sees_all_past_events(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("events"))

        self.assertContains(response, self.own_past_event.title)
        self.assertContains(response, self.other_past_event.title)

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

    def test_index_and_menu_link_to_events_pages(self):
        self.user.profile.has_had_introduction = True
        self.user.profile.save()
        self.client.force_login(self.user)

        response = self.client.get(reverse("main-page"))

        self.assertContains(response, f'href="{reverse("events-upcoming")}"')
        self.assertContains(response, f'href="{reverse("events")}"')


class HomePageViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="student",
            password="password",
            first_name="Anna",
            last_name="Zimmer",
        )
        self.user.profile.has_had_introduction = True
        self.user.profile.save(update_fields=["has_had_introduction"])
        self.client.force_login(self.user)

    def test_home_page_restores_abikasse_and_navigation_links(self):
        Abikasse.objects.create(goal=30000)
        now = timezone.now()
        Event.objects.create(
            title="Sommerfest",
            description="",
            starting_date=now - timedelta(days=2),
            ending_date=now - timedelta(days=1),
            creator=self.user,
            manager=self.user,
            earnings=Decimal("100.00"),
            final=True,
        )

        response = self.client.get(reverse("main-page"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "100,00 €")
        self.assertContains(response, "30000,00 €")
        self.assertContains(response, 'class="fund__divider"')
        self.assertContains(response, "Neuigkeiten")
        self.assertNotContains(response, "Rangliste")
        self.assertContains(response, f'href="{reverse("polls")}"')
        self.assertContains(response, f'href="{reverse("events-upcoming")}"')

    def test_empty_abikasse_shows_zero(self):
        response = self.client.get(reverse("main-page"))

        self.assertContains(response, "0,00 €")

    def test_home_page_does_not_force_reload(self):
        response = self.client.get(reverse("main-page"))

        self.assertNotContains(response, 'http-equiv="refresh"')

    def test_admin_menu_link_is_staff_only(self):
        response = self.client.get(reverse("main-page"))

        self.assertNotContains(response, 'href="/admin/"')

        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])

        response = self.client.get(reverse("main-page"))

        self.assertContains(response, 'href="/admin/"')

    def test_menu_links_available_pages_and_marks_others_disabled(self):
        response = self.client.get(reverse("main-page"))

        self.assertContains(response, f'href="{reverse("users")}"')
        self.assertContains(response, 'data-overlay-toggle="overlay"')
        self.assertContains(response, 'aria-controls="overlay"')
        self.assertContains(
            response,
            f'href="{reverse("user-details", args=[self.user.pk])}" data-overlay-open="overlay"',
        )
        self.assertContains(response, 'aria-disabled="true"')


class EventDetailViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="student", password="password")
        self.manager = User.objects.create_user(username="manager", password="password")
        self.staff = User.objects.create_user(
            username="staff", password="password", is_staff=True
        )
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


class DurationWidgetTests(SimpleTestCase):
    def test_split_duration_parses_timedelta_and_string(self):
        self.assertEqual(split_duration(timedelta(hours=2, minutes=5)), (2, 5))
        self.assertEqual(split_duration("2:05"), (2, 5))
        self.assertEqual(split_duration(""), (None, None))

    def test_duration_field_parses_h_mm(self):
        self.assertEqual(
            DurationHMField().clean("2:30"), timedelta(hours=2, minutes=30)
        )

    def test_duration_widget_reads_split_inputs(self):
        widget = DurationHMInput()

        self.assertEqual(
            widget.value_from_datadict(
                {
                    "participation_time_hours": "2",
                    "participation_time_minutes": "5",
                },
                {},
                "participation_time",
            ),
            "2:05",
        )
        self.assertIsNone(widget.value_from_datadict({}, {}, "participation_time"))


class ParticipationTimeViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="student", password="password")
        self.staff = User.objects.create_user(
            username="staff", password="password", is_staff=True
        )
        self.event = Event.objects.create(
            title="Arbeitseinsatz",
            description="",
            starting_date=timezone.now() - timedelta(days=2),
            ending_date=timezone.now() - timedelta(days=2) + timedelta(hours=4),
            creator=self.staff,
            manager=self.staff,
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

    def test_staff_detail_renders_split_duration_inputs(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("event-details", args=[self.event.pk]))

        self.assertContains(response, "participation_time_hours")
        self.assertContains(response, "participation_time_minutes")
        self.assertContains(response, "money-field__suffix")

    def test_staff_can_set_zero_participation_time(self):
        self.client.force_login(self.staff)
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

    def test_non_staff_cannot_set_participation_times(self):
        self.client.force_login(self.user)
        data = self.formset_data([(self.participation, "1:00")])

        response = self.client.post(
            reverse("set-participation-times", args=[self.event.pk]), data
        )

        self.assertEqual(response.status_code, 403)

    def test_too_long_participation_time_rerenders_with_error(self):
        self.client.force_login(self.staff)
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


class EventCreateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="student", password="password")
        self.other = User.objects.create_user(username="other", password="password")
        self.user.profile.has_had_introduction = True
        self.user.profile.save(update_fields=["has_had_introduction"])
        self.client.force_login(self.user)

    def create_data(self, **overrides):
        start = timezone.localtime(timezone.now() + timedelta(days=1))
        end = start + timedelta(hours=2)
        data = {
            "new-title": "Neue Aktion",
            "new-description": "Gemeinsam anpacken.",
            "new-starting_date": start.strftime("%Y-%m-%dT%H:%M"),
            "new-ending_date": end.strftime("%Y-%m-%dT%H:%M"),
            "new-manager": str(self.user.pk),
            "new-participants": [str(self.other.pk)],
        }
        data.update(overrides)
        return data

    def create_existing_event(self, index):
        now = timezone.now()
        return Event.objects.create(
            title=f"Bestehende Aktion {index}",
            description="",
            starting_date=now + timedelta(days=1),
            ending_date=now + timedelta(days=1, hours=1),
            creator=self.user,
            manager=self.user,
        )

    def test_create_form_renders_fragment_without_back_button(self):
        response = self.client.get(reverse("event-create"), HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Neue Aktion erstellen")
        self.assertContains(response, "Erstellen")
        self.assertNotContains(response, "<html")
        self.assertNotContains(response, "overlay-panel-back")

    def test_create_form_defaults_manager_to_request_user(self):
        response = self.client.get(reverse("event-create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'value="{self.user.pk}" data-hidden-user="{self.user.pk}"',
        )

    def test_valid_post_creates_event_with_participants_and_feedback(self):
        response = self.client.post(
            reverse("event-create"),
            self.create_data(),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aktion erfolgreich erstellt")
        self.assertContains(response, "Zur Aktion")
        self.assertContains(response, "Zur Liste")

        self.assertEqual(Event.objects.count(), 1)
        event = Event.objects.get()
        self.assertEqual(event.creator, self.user)
        self.assertEqual(event.manager, self.user)
        self.assertEqual(list(event.participants.all()), [self.other])
        self.assertEqual(EventParticipation.objects.filter(event=event).count(), 1)
        self.assertContains(
            response, f'hx-get="{reverse("event-details", args=[event.pk])}"'
        )

    def test_valid_post_redirects_to_detail_without_htmx(self):
        response = self.client.post(reverse("event-create"), self.create_data())

        event = Event.objects.get()
        self.assertRedirects(
            response,
            f"{reverse('event-details', args=[event.pk])}?status=created",
            fetch_redirect_response=False,
        )

    def test_invalid_post_rerenders_form_with_errors(self):
        response = self.client.post(
            reverse("event-create"),
            self.create_data(**{"new-title": ""}),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("title", response.context["form"].errors)
        self.assertContains(response, "Neue Aktion erstellen")
        self.assertEqual(Event.objects.count(), 0)

    def test_rate_limit_returns_feedback_for_htmx(self):
        for index in range(MAX_PROJECTS_PER_HOUR):
            self.create_existing_event(index)

        response = self.client.post(
            reverse("event-create"),
            self.create_data(),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Du kannst maximal")
        self.assertContains(response, "Zur Liste")
        self.assertEqual(Event.objects.count(), MAX_PROJECTS_PER_HOUR)

    def test_rate_limit_redirects_with_status_without_htmx(self):
        for index in range(MAX_PROJECTS_PER_HOUR):
            self.create_existing_event(index)

        response = self.client.post(reverse("event-create"), self.create_data())

        self.assertRedirects(
            response,
            f"{reverse('events')}?status=rate-limited",
            fetch_redirect_response=False,
        )
        self.assertEqual(Event.objects.count(), MAX_PROJECTS_PER_HOUR)

    @patch("dashboard.views.events.can_create_event", return_value=False)
    def test_restricted_user_is_denied_creation(self, _can_create_event):
        response = self.client.post(
            reverse("event-create"),
            self.create_data(),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "Du bist nicht berechtigt, diese Aktion zu erstellen."
        )
        self.assertEqual(Event.objects.count(), 0)

    @patch("dashboard.views.events.can_create_event", return_value=False)
    def test_events_page_hides_create_button_without_permission(
        self, _can_create_event
    ):
        response = self.client.get(reverse("events"))

        self.assertNotContains(response, "Neue Aktion")

    def test_events_page_shows_create_button_by_default(self):
        response = self.client.get(reverse("events"))

        self.assertContains(response, "Neue Aktion")


class EventEditViewTests(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user(username="creator", password="password")
        self.manager = User.objects.create_user(username="manager", password="password")
        self.other = User.objects.create_user(username="other", password="password")

        self.start = timezone.now() + timedelta(days=1)
        self.end = self.start + timedelta(hours=2)
        self.event = Event.objects.create(
            title="Sommerfest",
            description="Gemeinsam feiern.",
            starting_date=self.start,
            ending_date=self.end,
            creator=self.creator,
            manager=self.manager,
        )

        self.client.force_login(self.manager)

    def edit_data(self, **overrides):
        data = {
            f"{self.event.pk}-title": self.event.title,
            f"{self.event.pk}-description": self.event.description,
            f"{self.event.pk}-starting_date": timezone.localtime(self.start).strftime(
                "%Y-%m-%dT%H:%M"
            ),
            f"{self.event.pk}-ending_date": timezone.localtime(self.end).strftime(
                "%Y-%m-%dT%H:%M"
            ),
            f"{self.event.pk}-manager": str(self.manager.pk),
        }
        data.update(overrides)
        return data

    def test_edit_form_shows_existing_manager(self):
        response = self.client.get(
            reverse("event-edit", args=[self.event.pk]), HTTP_HX_REQUEST="true"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aktion bearbeiten")
        self.assertContains(response, "data-user-search")
        self.assertContains(response, f'name="{self.event.pk}-manager"')
        self.assertContains(
            response,
            f'value="{self.manager.pk}" data-hidden-user="{self.manager.pk}"',
        )
        self.assertNotContains(response, "<html")

    def test_manager_picker_only_lists_active_users(self):
        User.objects.create_user(
            username="active-user",
            password="password",
            first_name="Aktive",
            last_name="Person",
        )
        User.objects.create_user(
            username="inactive-user",
            password="password",
            first_name="Inaktive",
            last_name="Person",
            is_active=False,
        )

        form = EventForm(instance=self.event, request_user=self.manager)
        manager_html = str(form["manager"])

        self.assertIn("Aktive Person", manager_html)
        self.assertNotIn("Inaktive Person", manager_html)
        self.assertIn("data-user-results", manager_html)

    def test_create_form_defaults_manager_to_request_user(self):
        form = EventForm(request_user=self.manager)

        manager_html = str(form["manager"])

        self.assertIn(
            f'value="{self.manager.pk}" data-hidden-user="{self.manager.pk}"',
            manager_html,
        )

    def test_missing_manager_rerenders_with_error_and_keeps_creator(self):
        data = self.edit_data(**{f"{self.event.pk}-manager": ""})

        response = self.client.post(
            reverse("event-edit", args=[self.event.pk]),
            data,
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("manager", response.context["form"].errors)
        self.assertContains(response, "Aktion bearbeiten")

        self.event.refresh_from_db()
        self.assertEqual(self.event.creator, self.creator)
        self.assertEqual(self.event.manager, self.manager)

    def test_edit_updates_event_without_reassigning_creator(self):
        response = self.client.post(
            reverse("event-edit", args=[self.event.pk]),
            self.edit_data(**{f"{self.event.pk}-title": "Sommerfest neu"}),
        )

        self.assertRedirects(
            response,
            f"{reverse('event-details', args=[self.event.pk])}?status=updated",
            fetch_redirect_response=False,
        )

        self.event.refresh_from_db()
        self.assertEqual(self.event.title, "Sommerfest neu")
        self.assertEqual(self.event.creator, self.creator)
        self.assertEqual(self.event.manager, self.manager)

    def test_edit_removes_participants(self):
        self.event.participants.add(self.other)

        response = self.client.post(
            reverse("event-edit", args=[self.event.pk]), self.edit_data()
        )

        self.assertRedirects(
            response,
            f"{reverse('event-details', args=[self.event.pk])}?status=updated",
            fetch_redirect_response=False,
        )
        self.assertFalse(self.event.participants.filter(pk=self.other.pk).exists())

    def test_edit_can_change_manager(self):
        response = self.client.post(
            reverse("event-edit", args=[self.event.pk]),
            self.edit_data(**{f"{self.event.pk}-manager": str(self.other.pk)}),
        )

        self.assertRedirects(
            response,
            f"{reverse('event-details', args=[self.event.pk])}?status=updated",
            fetch_redirect_response=False,
        )

        self.event.refresh_from_db()
        self.assertEqual(self.event.manager, self.other)
        self.assertEqual(self.event.creator, self.creator)

    def test_edit_htmx_success_returns_feedback_with_action(self):
        response = self.client.post(
            reverse("event-edit", args=[self.event.pk]),
            self.edit_data(**{f"{self.event.pk}-title": "Sommerfest neu"}),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aktion erfolgreich bearbeitet")
        self.assertContains(response, "Zur Aktion")
        self.assertContains(
            response, f'hx-get="{reverse("event-details", args=[self.event.pk])}"'
        )

    def test_final_event_cannot_be_edited(self):
        self.event.final = True
        self.event.save(update_fields=["final"])

        response = self.client.get(reverse("event-edit", args=[self.event.pk]))

        self.assertRedirects(
            response,
            f"{reverse('event-details', args=[self.event.pk])}?status=edit-denied",
            fetch_redirect_response=False,
        )

    def test_unrelated_user_cannot_edit_event(self):
        self.client.force_login(self.other)

        response = self.client.get(
            reverse("event-edit", args=[self.event.pk]), HTTP_HX_REQUEST="true"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "Du bist nicht berechtigt, diese Aktion zu bearbeiten."
        )


class EarningsFormTests(TestCase):
    def test_accepts_comma_and_dot_and_quantizes_to_two_places(self):
        for raw_value in ("13,1", "13.1"):
            with self.subTest(raw_value=raw_value):
                form = SetEarningsForm(data={"earnings": raw_value})

                self.assertTrue(form.is_valid())
                self.assertEqual(form.cleaned_data["earnings"], Decimal("13.10"))

    def test_prepares_existing_value_with_two_decimal_places(self):
        user = User.objects.create_user(username="user", password="password")
        event = Event.objects.create(
            title="Aktion",
            description="",
            starting_date=timezone.now(),
            ending_date=timezone.now() + timedelta(hours=1),
            creator=user,
            manager=user,
            earnings=Decimal("13.1"),
        )

        earnings_html = str(SetEarningsForm(instance=event)["earnings"])

        self.assertIn('value="13,10"', earnings_html)
        self.assertIn('inputmode="decimal"', earnings_html)


class UserViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="student",
            password="password",
            first_name="Anna",
            last_name="Zimmer",
            email="anna@example.org",
        )
        self.other = User.objects.create_user(
            username="other",
            password="password",
            first_name="Ben",
            last_name="Albers",
            email="ben@example.org",
        )
        self.staff = User.objects.create_user(
            username="staff",
            password="password",
            first_name="Clara",
            last_name="Meyer",
            is_staff=True,
        )
        self.user.profile.has_had_introduction = True
        self.user.profile.save()
        self.client.force_login(self.user)

    def test_users_page_lists_users_in_name_order_with_search_hooks(self):
        response = self.client.get(reverse("users"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<html")
        self.assertContains(response, "data-users-page")
        self.assertContains(response, 'data-user-name="Ben Albers"')
        self.assertEqual(
            [user.username for user in response.context["users"]],
            ["student", "other", "staff"],
        )

    def test_user_details_full_page_keeps_request_user_in_shell(self):
        response = self.client.get(reverse("user-details", args=[self.other.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<html")
        self.assertContains(response, "data-user-detail")
        self.assertContains(response, "Ben Albers")
        self.assertContains(
            response,
            f'href="{reverse("user-details", args=[self.user.pk])}" data-overlay-open="overlay"',
        )
        self.assertNotContains(response, reverse("user-details", args=[self.other.pk]))

    def test_user_details_renders_fragment_for_htmx(self):
        response = self.client.get(
            reverse("user-details", args=[self.other.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<html")
        self.assertContains(response, "data-user-detail")

    def test_user_details_formats_total_hours_and_lists_participations(self):
        event = Event.objects.create(
            title="Sommerfest",
            description="",
            starting_date=timezone.now() - timedelta(days=2, hours=2),
            ending_date=timezone.now() - timedelta(days=2),
            creator=self.user,
            manager=self.user,
        )
        EventParticipation.objects.create(
            event=event,
            user=self.other,
            participation_time=timedelta(hours=1, minutes=30),
        )

        response = self.client.get(
            reverse("user-details", args=[self.other.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertContains(response, "Arbeitsstunden: 1:30 h")
        self.assertContains(response, "Sommerfest")

    def test_user_details_renders_status_feedback(self):
        response = self.client.get(
            reverse("user-details", args=[self.user.pk]),
            {"status": "profile-updated"},
            HTTP_HX_REQUEST="true",
        )

        self.assertContains(response, "Profil erfolgreich bearbeitet")

    def test_edit_user_get_renders_form(self):
        response = self.client.get(
            reverse("user-edit", args=[self.user.pk]), HTTP_HX_REQUEST="true"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profil bearbeiten")
        self.assertContains(response, 'name="birthday"')

    def test_edit_user_success_returns_feedback(self):
        response = self.client.post(
            reverse("user-edit", args=[self.user.pk]),
            {
                "birthday": "2008-01-02",
                "external_mail": "",
                "phone_number": "",
                "bio": "Neue Bio",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profil erfolgreich bearbeitet")
        self.assertContains(response, "Zurück zum Profil")
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.bio, "Neue Bio")

    def test_edit_user_success_redirects_without_htmx(self):
        response = self.client.post(
            reverse("user-edit", args=[self.user.pk]),
            {
                "birthday": "",
                "external_mail": "",
                "phone_number": "",
                "bio": "",
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('user-details', args=[self.user.pk])}?status=profile-updated",
            fetch_redirect_response=False,
        )

    def test_unrelated_user_cannot_edit_user(self):
        self.client.force_login(self.other)

        response = self.client.get(
            reverse("user-edit", args=[self.user.pk]), HTTP_HX_REQUEST="true"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "Du bist nicht berechtigt, dieses Nutzerprofil zu bearbeiten."
        )

    def test_self_password_change_requires_old_password(self):
        response = self.client.post(
            reverse("change-password-popup", args=[self.user.pk]),
            {
                "old_password": "password",
                "new_password1": "new-password-123",
                "new_password2": "new-password-123",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Passwort erfolgreich geändert")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("new-password-123"))

        # update_session_auth_hash keeps the current session logged in.
        self.assertEqual(self.client.get(reverse("main-page")).status_code, 200)

    def test_wrong_old_password_rerenders_self_form(self):
        response = self.client.post(
            reverse("change-password-popup", args=[self.user.pk]),
            {
                "old_password": "wrong",
                "new_password1": "new-password-123",
                "new_password2": "new-password-123",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Passwort ändern für")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("password"))

    def test_staff_can_change_other_users_password_without_old_password(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("change-password-popup", args=[self.other.pk]),
            {
                "new_password1": "new-password-123",
                "new_password2": "new-password-123",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Passwort erfolgreich geändert")
        self.other.refresh_from_db()
        self.assertTrue(self.other.check_password("new-password-123"))

    def test_non_staff_cannot_change_other_users_password(self):
        response = self.client.post(
            reverse("change-password-popup", args=[self.other.pk]),
            {
                "old_password": "password",
                "new_password1": "new-password-123",
                "new_password2": "new-password-123",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "Du bist nicht berechtigt, dieses Passwort zu ändern."
        )
        self.other.refresh_from_db()
        self.assertTrue(self.other.check_password("password"))


class IntroductionViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="new-student",
            password="old-password",
            first_name="Nora",
        )
        self.client.force_login(self.user)

    def test_entry_points_redirect_to_introduction_until_complete(self):
        for url_name in (
            "main-page",
            "events",
            "users",
            "calendar",
            "contact",
            "polls",
        ):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertRedirects(response, reverse("introduction"))

    def test_introduction_page_renders_steps(self):
        response = self.client.get(reverse("introduction"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-introduction")
        self.assertContains(response, 'data-initial-step="step-1"')
        self.assertContains(response, 'id="step-1"')
        self.assertContains(response, 'id="step-6"')
        self.assertContains(response, "<p>Hi Nora,</p>")
        self.assertContains(
            response,
            '<button type="button" class="btn" data-from="step-1" '
            'data-to="step-2">Weiter</button>',
        )
        self.assertContains(response, "<li>Ankündigungen</li>")
        self.assertContains(response, "Telefonnummer:")

    def test_password_step_success_returns_trigger_and_updates_password(self):
        response = self.client.post(
            reverse("set-password"),
            {
                "new_password1": "new-password-123",
                "new_password2": "new-password-123",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Trigger"], "intro:password-set")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("new-password-123"))

    def test_password_step_invalid_rerenders_partial_with_errors(self):
        response = self.client.post(
            reverse("set-password"),
            {"new_password1": "short", "new_password2": "different"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<html")
        self.assertContains(response, "errorlist")
        self.assertTrue(response.context["password_form"].errors)

    def test_password_step_without_htmx_redirects_to_introduction(self):
        response = self.client.post(
            reverse("set-password"),
            {
                "new_password1": "new-password-123",
                "new_password2": "new-password-123",
            },
        )

        self.assertRedirects(response, reverse("introduction"))

    def test_profile_completion_htmx_returns_feedback_step(self):
        response = self.client.post(
            reverse("introduction"),
            {"bio": "Hallo"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<html")
        self.assertContains(response, "Profil gespeichert")
        self.assertContains(response, "Weiter zur Startseite")
        self.assertEqual(response.context["feedback"]["kind"], "success")
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.has_had_introduction)

    def test_profile_completion_without_htmx_redirects_to_main_page(self):
        response = self.client.post(reverse("introduction"), {"bio": "Hallo"})

        self.assertRedirects(response, reverse("main-page"))
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.has_had_introduction)

    def test_invalid_profile_rerenders_page_at_profile_step(self):
        response = self.client.post(
            reverse("introduction"),
            {"birthday": "2020-13-01"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<html")
        self.assertContains(response, 'data-initial-step="profile"')
        self.assertContains(response, "errorlist")
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.has_had_introduction)

    def test_invalid_profile_htmx_rerenders_form_partial(self):
        response = self.client.post(
            reverse("introduction"),
            {"birthday": "2020-13-01"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<html")
        self.assertContains(response, "errorlist")
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.has_had_introduction)


class StaticPageViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="student", password="password")
        self.user.profile.has_had_introduction = True
        self.user.profile.save(update_fields=["has_had_introduction"])
        self.client.force_login(self.user)

    def test_stub_pages_render_in_the_shell(self):
        for url_name, heading in (
            ("calendar", "Kalender"),
            ("polls", "Demokratie"),
            ("contact", "Kontakt"),
        ):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "<html")
                self.assertContains(response, f"<h1>{heading}</h1>")

    def test_events_page_links_to_the_calendar_stub(self):
        response = self.client.get(reverse("events"))

        self.assertContains(response, f'href="{reverse("calendar")}"')
