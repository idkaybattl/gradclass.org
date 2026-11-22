from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import Event, EventParticipation
from .helpers import User, make_rep


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
        self.admin = User.objects.create_superuser(
            username="staff",
            password="password",
            first_name="Clara",
            last_name="Meyer",
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

    def test_user_details_hides_mail_from_other_students(self):
        self.other.profile.external_mail = "ben@external.example"
        self.other.profile.save()

        response = self.client.get(
            reverse("user-details", args=[self.other.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertNotContains(response, "IServ Mail")
        self.assertNotContains(response, "Externe Mail")
        self.assertNotContains(response, "ben@example.org")

    def test_user_details_shows_own_mail_to_self(self):
        self.user.profile.external_mail = "anna@external.example"
        self.user.profile.save()

        response = self.client.get(
            reverse("user-details", args=[self.user.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertContains(response, "IServ Mail")
        self.assertContains(response, "anna@example.org")
        self.assertContains(response, "Externe Mail")
        self.assertContains(response, "anna@external.example")

    def test_user_details_shows_mail_to_reps(self):
        rep = make_rep("rep")
        rep.profile.has_had_introduction = True
        rep.profile.save()
        self.client.force_login(rep)

        response = self.client.get(
            reverse("user-details", args=[self.other.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertContains(response, "IServ Mail")
        self.assertContains(response, "ben@example.org")

    def test_user_details_shows_mail_to_admins(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("user-details", args=[self.other.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertContains(response, "IServ Mail")
        self.assertContains(response, "ben@example.org")

    def test_edit_user_get_renders_form(self):
        response = self.client.get(
            reverse("user-edit", args=[self.user.pk]), HTTP_HX_REQUEST="true"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profil bearbeiten")
        self.assertContains(response, 'name="birthday"')

    def test_edit_user_direct_navigation_redirects_to_details(self):
        response = self.client.get(reverse("user-edit", args=[self.user.pk]))

        self.assertRedirects(
            response,
            reverse("user-details", args=[self.user.pk]),
            fetch_redirect_response=False,
        )

    def test_edit_user_invalid_post_without_htmx_renders_full_page(self):
        response = self.client.post(
            reverse("user-edit", args=[self.user.pk]),
            {
                "birthday": "2020-13-01",
                "external_mail": "",
                "phone_number": "",
                "bio": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<html")
        self.assertContains(response, "Profil bearbeiten")
        self.assertContains(response, "errorlist")

    def test_password_popup_direct_navigation_redirects_to_details(self):
        response = self.client.get(
            reverse("change-password-popup", args=[self.user.pk])
        )

        self.assertRedirects(
            response,
            reverse("user-details", args=[self.user.pk]),
            fetch_redirect_response=False,
        )

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

    def test_admin_can_change_other_users_password_without_old_password(self):
        self.client.force_login(self.admin)

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
