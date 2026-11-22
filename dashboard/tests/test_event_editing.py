from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..forms import EventForm
from ..models import Event, EventParticipation
from ..views.events import MAX_PROJECTS_PER_HOUR
from .helpers import User, make_limited_creator, make_rep


class EventCreateViewTests(TestCase):
    def setUp(self):
        self.user = make_rep("rep")
        self.other = User.objects.create_user(username="other", password="password")
        self.limited_user = make_limited_creator("limited")
        for user in (self.user, self.other, self.limited_user):
            user.profile.has_had_introduction = True
            user.profile.save(update_fields=["has_had_introduction"])
        self.client.force_login(self.user)

    def create_data(self, **overrides):
        start = timezone.localtime(timezone.now() + timedelta(days=1))
        end = start + timedelta(hours=2)
        data = {
            "new-title": "Neue Aktion",
            "new-description": "Gemeinsam anpacken.",
            "new-starting_date": start.strftime("%Y-%m-%dT%H:%M"),
            "new-ending_date": end.strftime("%Y-%m-%dT%H:%M"),
            "new-work_kind": Event.WorkKind.SCHOOL,
            "new-manager": str(self.user.pk),
            "new-participants": [str(self.other.pk)],
        }
        data.update(overrides)
        return data

    def create_existing_event(self, index, user=None):
        now = timezone.now()
        creator = user or self.user
        return Event.objects.create(
            title=f"Bestehende Aktion {index}",
            description="",
            starting_date=now + timedelta(days=1),
            ending_date=now + timedelta(days=1, hours=1),
            creator=creator,
            manager=creator,
        )

    def test_create_form_renders_fragment_without_back_button(self):
        response = self.client.get(reverse("event-create"), HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Neue Aktion erstellen")
        self.assertContains(response, "Erstellen")
        self.assertNotContains(response, "<html")
        self.assertNotContains(response, "overlay-panel-back")

    def test_create_form_defaults_manager_to_request_user(self):
        response = self.client.get(reverse("event-create"), HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'value="{self.user.pk}" data-hidden-user="{self.user.pk}"',
        )

    def test_create_form_direct_navigation_redirects_to_list(self):
        response = self.client.get(reverse("event-create"))

        self.assertRedirects(response, reverse("events"), fetch_redirect_response=False)

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

    def test_invalid_post_without_htmx_renders_full_page(self):
        response = self.client.post(
            reverse("event-create"),
            self.create_data(**{"new-title": ""}),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<html")
        self.assertContains(response, "Neue Aktion erstellen")
        self.assertContains(response, "errorlist")
        self.assertEqual(Event.objects.count(), 0)

    def test_rate_limit_returns_feedback_for_htmx(self):
        self.client.force_login(self.limited_user)
        for index in range(MAX_PROJECTS_PER_HOUR):
            self.create_existing_event(index, user=self.limited_user)

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
        self.client.force_login(self.limited_user)
        for index in range(MAX_PROJECTS_PER_HOUR):
            self.create_existing_event(index, user=self.limited_user)

        response = self.client.post(reverse("event-create"), self.create_data())

        self.assertRedirects(
            response,
            f"{reverse('events')}?status=rate-limited",
            fetch_redirect_response=False,
        )
        self.assertEqual(Event.objects.count(), MAX_PROJECTS_PER_HOUR)

    def test_rep_bypasses_rate_limit(self):
        for index in range(MAX_PROJECTS_PER_HOUR):
            self.create_existing_event(index)

        response = self.client.post(
            reverse("event-create"),
            self.create_data(),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aktion erfolgreich erstellt")
        self.assertEqual(Event.objects.count(), MAX_PROJECTS_PER_HOUR + 1)

    def test_student_is_denied_creation(self):
        self.client.force_login(self.other)

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
            f"{self.event.pk}-work_kind": self.event.work_kind,
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
        self.assertContains(response, "overlay-panel-back")

    def test_edit_form_direct_navigation_redirects_to_detail(self):
        response = self.client.get(reverse("event-edit", args=[self.event.pk]))

        self.assertRedirects(
            response,
            reverse("event-details", args=[self.event.pk]),
            fetch_redirect_response=False,
        )

    def test_invalid_edit_post_without_htmx_renders_full_page(self):
        data = self.edit_data(**{f"{self.event.pk}-title": ""})

        response = self.client.post(reverse("event-edit", args=[self.event.pk]), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<html")
        self.assertContains(response, "Aktion bearbeiten")
        self.assertContains(response, "errorlist")

        self.event.refresh_from_db()
        self.assertEqual(self.event.creator, self.creator)

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


class EventEarningsViewTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="manager", password="password")
        self.rep = make_rep("rep")
        self.other = User.objects.create_user(username="other", password="password")
        self.event = Event.objects.create(
            title="Sommerfest",
            description="",
            starting_date=timezone.now() + timedelta(days=1),
            ending_date=timezone.now() + timedelta(days=1, hours=2),
            creator=self.manager,
            manager=self.manager,
        )

    def test_manager_can_set_earnings(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("set-earnings", args=[self.event.pk]),
            {"earnings": "12,50"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Einnahmen gesetzt.")
        self.event.refresh_from_db()
        self.assertEqual(self.event.earnings, Decimal("12.50"))

    def test_invalid_earnings_rerenders_detail_with_errors(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("set-earnings", args=[self.event.pk]),
            {"earnings": "keine Zahl"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("earnings", response.context["earnings_form"].errors)
        self.event.refresh_from_db()
        self.assertIsNone(self.event.earnings)

    def test_unrelated_user_cannot_set_earnings(self):
        self.client.force_login(self.other)

        response = self.client.post(
            reverse("set-earnings", args=[self.event.pk]),
            {"earnings": "12,50"},
            HTTP_HX_REQUEST="true",
        )

        self.assertContains(
            response, "Du bist nicht berechtigt, diese Aktion zu bearbeiten."
        )
        self.event.refresh_from_db()
        self.assertIsNone(self.event.earnings)

    def test_rep_can_mark_earnings_received_and_finalize_event(self):
        self.client.force_login(self.rep)

        response = self.client.post(
            reverse("set-earnings-received", args=[self.event.pk]),
            {"earnings_received": "on"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Einnahmenstatus aktualisiert.")
        self.event.refresh_from_db()
        self.assertTrue(self.event.earnings_received)
        self.assertTrue(self.event.final)

    def test_non_staff_cannot_mark_earnings_received(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("set-earnings-received", args=[self.event.pk]),
            {"earnings_received": "on"},
            HTTP_HX_REQUEST="true",
        )

        self.assertContains(
            response, "Du bist nicht berechtigt, diese Aktion zu bearbeiten."
        )
        self.event.refresh_from_db()
        self.assertFalse(self.event.earnings_received)
        self.assertFalse(self.event.final)
