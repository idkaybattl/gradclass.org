from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Event, JoinRequest
from .notifications import Notification, NotificationVerbChoices

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
