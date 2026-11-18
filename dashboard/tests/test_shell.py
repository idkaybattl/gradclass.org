from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import Event, JoinRequest
from .helpers import User, make_rep


class OverlayContractTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="student", password="password")
        self.manager = User.objects.create_user(username="manager", password="password")
        self.user.profile.has_had_introduction = True
        self.user.profile.save(update_fields=["has_had_introduction"])
        self.manager.profile.has_had_introduction = True
        self.manager.profile.save(update_fields=["has_had_introduction"])
        self.event = Event.objects.create(
            title="Sommerfest",
            description="",
            starting_date=timezone.now() + timedelta(days=1),
            ending_date=timezone.now() + timedelta(days=1, hours=2),
            creator=self.manager,
            manager=self.manager,
        )
        self.join_request = JoinRequest.objects.create(
            requestor=self.user, event=self.event
        )
        self.client.force_login(self.manager)

    def test_authenticated_full_pages_include_the_overlay_shell(self):
        for url in (
            reverse("main-page"),
            reverse("events"),
            reverse("users"),
            reverse("event-details", args=[self.event.pk]),
            reverse("user-details", args=[self.user.pk]),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "<html")
                self.assertContains(response, 'id="overlay-content"')

    def test_overlay_views_return_fragments_without_close_controls(self):
        urls = (
            reverse("event-details", args=[self.event.pk]),
            reverse("event-create"),
            reverse("event-edit", args=[self.event.pk]),
            reverse("user-details", args=[self.user.pk]),
            reverse("user-edit", args=[self.manager.pk]),
            reverse("change-password-popup", args=[self.manager.pk]),
            reverse("notifications"),
        )

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url, HTTP_HX_REQUEST="true")

                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "<html")
                self.assertNotContains(response, "overlay-close")
                self.assertNotContains(response, "Schließen")

    def test_overlay_views_have_a_full_page_or_redirect_fallback(self):
        for url in (
            reverse("event-create"),
            reverse("event-edit", args=[self.event.pk]),
            reverse("user-edit", args=[self.user.pk]),
            reverse("change-password-popup", args=[self.user.pk]),
            reverse("notifications"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, 302)

    def test_back_control_only_renders_when_back_url_is_present(self):
        detail_url = reverse("event-details", args=[self.event.pk])
        user_url = reverse("user-details", args=[self.user.pk])

        cases = (
            (detail_url, False),
            (f"{detail_url}?back={reverse('events')}", True),
            (user_url, False),
            (f"{user_url}?back={reverse('users')}", True),
            (reverse("event-create"), False),
            (reverse("event-edit", args=[self.event.pk]), True),
            (reverse("user-edit", args=[self.manager.pk]), True),
            (reverse("change-password-popup", args=[self.manager.pk]), True),
        )

        for url, has_back in cases:
            with self.subTest(url=url):
                response = self.client.get(url, HTTP_HX_REQUEST="true")

                if has_back:
                    self.assertContains(response, "overlay-panel-back")
                else:
                    self.assertNotContains(response, "overlay-panel-back")

    def test_join_request_fragment_has_a_back_control(self):
        self.client.force_login(self.manager)

        response = self.client.get(
            f"{reverse('join-request-details', args=[self.join_request.pk])}?back={reverse('events')}",
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "overlay-panel-back")
        self.assertNotContains(response, "overlay-close")


class StatusFeedbackTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="student", password="password")
        self.user.profile.has_had_introduction = True
        self.user.profile.save(update_fields=["has_had_introduction"])
        self.event = Event.objects.create(
            title="Sommerfest",
            description="",
            starting_date=timezone.now() + timedelta(days=1),
            ending_date=timezone.now() + timedelta(days=1, hours=2),
            creator=self.user,
            manager=self.user,
        )
        self.client.force_login(self.user)

    def test_full_page_status_flags_render_the_feedback_banner(self):
        cases = (
            (f"{reverse('events')}?status=deleted", "Aktion gelöscht."),
            (
                f"{reverse('event-details', args=[self.event.pk])}?status=joined",
                "Du nimmst jetzt teil",
            ),
            (
                f"{reverse('user-details', args=[self.user.pk])}?status=profile-updated",
                "Profil erfolgreich bearbeitet",
            ),
        )

        for url, text in cases:
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, text)
                self.assertContains(response, "feedback")


class UrlSmokeTests(TestCase):
    def setUp(self):
        self.rep = make_rep("smoke-rep")
        self.rep.profile.has_had_introduction = True
        self.rep.profile.save(update_fields=["has_had_introduction"])
        self.event = Event.objects.create(
            title="Smoke-Aktion",
            description="",
            starting_date=timezone.now() + timedelta(days=1),
            ending_date=timezone.now() + timedelta(days=1, hours=2),
            creator=self.rep,
            manager=self.rep,
        )
        self.join_request = JoinRequest.objects.create(
            requestor=self.rep, event=self.event
        )
        self.client.force_login(self.rep)

    def urls(self):
        return (
            reverse("main-page"),
            reverse("events"),
            reverse("events-upcoming"),
            reverse("events-own"),
            reverse("event-details", args=[self.event.pk]),
            reverse("event-create"),
            reverse("event-edit", args=[self.event.pk]),
            reverse("join-request-details", args=[self.join_request.pk]),
            reverse("users"),
            reverse("user-details", args=[self.rep.pk]),
            reverse("user-edit", args=[self.rep.pk]),
            reverse("change-password-popup", args=[self.rep.pk]),
            reverse("introduction"),
            reverse("calendar"),
            reverse("contact"),
            reverse("polls"),
            reverse("notifications"),
        )

    def test_every_route_renders_without_a_template_error(self):
        for url in self.urls():
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertIn(response.status_code, (200, 302))
                if response.status_code == 200:
                    self.assertContains(response, "<html")

    def test_every_overlay_route_renders_a_fragment_for_htmx(self):
        overlay_urls = (
            reverse("event-details", args=[self.event.pk]),
            reverse("event-create"),
            reverse("event-edit", args=[self.event.pk]),
            reverse("join-request-details", args=[self.join_request.pk]),
            reverse("user-details", args=[self.rep.pk]),
            reverse("user-edit", args=[self.rep.pk]),
            reverse("change-password-popup", args=[self.rep.pk]),
            reverse("notifications"),
        )

        for url in overlay_urls:
            with self.subTest(url=url):
                response = self.client.get(url, HTTP_HX_REQUEST="true")

                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "<html")
