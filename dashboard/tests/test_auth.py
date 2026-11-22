import re

from django.conf import settings
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from .helpers import User


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
        self.assertContains(response, 'data-initial-step="intro-welcome"')
        self.assertContains(response, 'id="intro-welcome"')
        self.assertContains(response, 'id="intro-email"')
        self.assertContains(response, 'id="intro-profile"')
        self.assertContains(response, "<p>Hi Nora,</p>")
        self.assertContains(
            response,
            '<button type="button" class="btn" data-from="intro-welcome" '
            'data-to="intro-features">Weiter</button>',
        )
        self.assertContains(response, "<li>Neuigkeiten und Ankündigungen</li>")
        self.assertContains(response, "Telefonnummer:")

    def test_introduction_step_parameter_selects_the_step(self):
        response = self.client.get(reverse("introduction"), {"step": "email"})

        self.assertContains(response, 'data-initial-step="intro-email"')

    def test_introduction_ignores_unknown_step_parameter(self):
        response = self.client.get(reverse("introduction"), {"step": "nope"})

        self.assertContains(response, 'data-initial-step="intro-welcome"')

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

        self.assertRedirects(response, f"{reverse('introduction')}?step=email")

    def test_email_step_success_returns_trigger_and_saves_mail(self):
        response = self.client.post(
            reverse("set-email"),
            {"external_mail": "nora@example.org"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Trigger"], "intro:email-set")
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.external_mail, "nora@example.org")

    def test_email_step_is_optional(self):
        response = self.client.post(
            reverse("set-email"),
            {"external_mail": ""},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.external_mail)

    def test_email_step_invalid_rerenders_partial_with_errors(self):
        response = self.client.post(
            reverse("set-email"),
            {"external_mail": "not-an-address"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<html")
        self.assertContains(response, "errorlist")
        self.assertTrue(response.context["email_form"].errors)

    def test_email_step_without_htmx_redirects_to_profile_step(self):
        response = self.client.post(
            reverse("set-email"),
            {"external_mail": "nora@example.org"},
        )

        self.assertRedirects(response, f"{reverse('introduction')}?step=profile")
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.external_mail, "nora@example.org")

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
        self.assertContains(response, 'data-initial-step="intro-profile"')
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


class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="reset-user",
            password="old-password",
            email="reset@iserv.example",
            first_name="Reset",
        )
        self.user.profile.external_mail = "reset@external.example"
        self.user.profile.save()

    def request_reset(self, email):
        return self.client.post(reverse("password-reset"), {"email": email})

    def reset_link(self):
        return re.search(r"https?://\S+", mail.outbox[0].body).group(0)

    def test_reset_mail_only_goes_to_external_address(self):
        response = self.request_reset("RESET@iserv.example")

        self.assertRedirects(response, reverse("password-reset-done"))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["reset@external.example"])
        self.assertEqual(message.from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertEqual(message.reply_to, [settings.DEFAULT_REPLY_TO])
        self.assertIn("passwort-zuruecksetzen", message.body)

    def test_external_address_also_identifies_the_account(self):
        response = self.request_reset("reset@external.example")

        self.assertRedirects(response, reverse("password-reset-done"))
        self.assertEqual(len(mail.outbox), 1)

    def test_user_without_external_mail_gets_no_mail_but_done_page(self):
        User.objects.create_user(
            username="iserv-only", password="x", email="only@iserv.example"
        )

        response = self.request_reset("only@iserv.example")

        self.assertRedirects(response, reverse("password-reset-done"))
        self.assertEqual(mail.outbox, [])

    def test_unknown_and_inactive_addresses_get_no_mail(self):
        inactive = User.objects.create_user(
            username="inactive", password="x", email="inactive@iserv.example"
        )
        inactive.profile.external_mail = "inactive@external.example"
        inactive.profile.save()
        inactive.is_active = False
        inactive.save(update_fields=["is_active"])

        for email in ["unknown@example.com", "inactive@iserv.example"]:
            with self.subTest(email=email):
                response = self.request_reset(email)

                self.assertRedirects(response, reverse("password-reset-done"))
                self.assertEqual(mail.outbox, [])

    def test_link_stops_working_after_password_change(self):
        self.request_reset("reset@iserv.example")
        link = self.reset_link()

        step = self.client.get(link)
        self.assertEqual(step.status_code, 302)
        self.assertContains(self.client.get(step.url), "Neues Passwort")
        response = self.client.post(
            step.url,
            {"new_password1": "new-password", "new_password2": "new-password"},
        )
        self.assertRedirects(response, reverse("password-reset-complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("new-password"))

        self.assertContains(self.client.get(link), "ungültig")

    def test_link_action_is_gated_on_manage_users(self):
        target = User.objects.create_user(username="target", password="x")
        action = reverse("user-reset-link", args=[target.pk])

        self.client.force_login(self.user)
        denied = self.client.post(action, HTTP_HX_REQUEST="true")
        self.assertEqual(denied.status_code, 200)
        self.assertContains(denied, "nicht berechtigt")
        self.assertNotContains(denied, "data-copy-field")

        admin = User.objects.create_superuser(username="admin", password="x")
        self.client.force_login(admin)
        response = self.client.post(action, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-copy-field")
        self.assertContains(response, "/passwort-zuruecksetzen/")

    def test_reset_pages_and_login_render_without_login(self):
        for name in [
            "password-reset",
            "password-reset-done",
            "password-reset-complete",
            "login",
        ]:
            with self.subTest(view=name):
                response = self.client.get(reverse(name))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "login-card")
