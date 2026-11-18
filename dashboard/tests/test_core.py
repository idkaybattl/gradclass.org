from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import Abikasse, Event
from .helpers import User


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

    def test_admin_menu_link_requires_access_admin(self):
        response = self.client.get(reverse("main-page"))
        self.assertNotContains(response, 'href="/admin/"')

        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        response = self.client.get(reverse("main-page"))
        self.assertNotContains(response, 'href="/admin/"')

        self.user.user_permissions.add(Permission.objects.get(codename="access_admin"))
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


class ContactViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="student", password="password")
        self.user.profile.has_had_introduction = True
        self.user.profile.save(update_fields=["has_had_introduction"])
        self.client.force_login(self.user)

    def test_contact_shows_superuser_profile_details(self):
        contact = User.objects.create_superuser(
            username="maintainer",
            password="password",
            email="iserv@whg.example",
            first_name="Moritz",
            last_name="Fechte",
        )
        contact.profile.external_mail = "moritz@example.com"
        contact.profile.phone_number = "+491712952470"
        contact.profile.save()

        response = self.client.get(reverse("contact"))

        self.assertContains(response, "Moritz Fechte")
        self.assertContains(response, 'href="tel:+491712952470"')
        self.assertContains(response, "0171 2952470")
        self.assertContains(response, 'href="mailto:moritz@example.com"')
        self.assertNotContains(response, "iserv@whg.example")

    def test_contact_hides_empty_rows_and_shows_fallback(self):
        User.objects.create_superuser(
            username="maintainer",
            password="password",
            first_name="Moritz",
            last_name="Fechte",
        )

        response = self.client.get(reverse("contact"))

        self.assertContains(response, "Moritz Fechte")
        self.assertContains(response, "Zurzeit sind keine Kontaktdaten hinterlegt.")
        self.assertNotContains(response, "tel:")
        self.assertNotContains(response, "mailto:")

    def test_contact_user_id_setting_wins(self):
        first = User.objects.create_superuser(
            username="first", password="password", first_name="First"
        )
        first.profile.external_mail = "first@example.com"
        first.profile.save()
        second = User.objects.create_superuser(
            username="second", password="password", first_name="Second"
        )
        second.profile.external_mail = "second@example.com"
        second.profile.save()

        with self.settings(CONTACT_USER_ID=second.pk):
            response = self.client.get(reverse("contact"))

        self.assertContains(response, "Second")
        self.assertContains(response, "second@example.com")
        self.assertNotContains(response, "first@example.com")

    def test_contact_without_superuser_renders_fallback(self):
        response = self.client.get(reverse("contact"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<h1>Kontakt</h1>")
        self.assertContains(response, "Zurzeit sind keine Kontaktdaten hinterlegt.")
