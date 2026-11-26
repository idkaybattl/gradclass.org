from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import AbiballConfig, AbikasseEntry, Event, EventParticipation
from ..services import (
    abikasse_balance,
    earnings_share,
    get_abikasse,
    participation_points,
    ticket_base,
    ticket_estimate,
    total_points,
    work_points,
)
from .helpers import User, make_rep


def make_student(username):
    user = User.objects.create_user(username=username, password="password")
    user.profile.has_had_introduction = True
    user.profile.save(update_fields=["has_had_introduction"])
    return user


def make_rep_user(username):
    user = make_rep(username)
    user.profile.has_had_introduction = True
    user.profile.save(update_fields=["has_had_introduction"])
    return user


def make_event(
    creator,
    *,
    final=True,
    earnings=None,
    work_kind=Event.WorkKind.SCHOOL,
    ended=True,
    title="Aktion",
):
    now = timezone.now()
    if ended:
        starting_date = now - timedelta(hours=2)
        ending_date = now - timedelta(hours=1)
    else:
        starting_date = now + timedelta(hours=1)
        ending_date = now + timedelta(hours=2)
    return Event.objects.create(
        title=title,
        description="",
        starting_date=starting_date,
        ending_date=ending_date,
        creator=creator,
        manager=creator,
        final=final,
        earnings=earnings,
        work_kind=work_kind,
    )


def participate(event, user, hours):
    return EventParticipation.objects.create(
        event=event,
        user=user,
        participation_time=timedelta(hours=hours),
    )


class PointsServiceTests(TestCase):
    def setUp(self):
        self.user = make_student("student")
        self.other = make_student("other")

    def test_school_and_freetime_weighting(self):
        school = make_event(self.user, work_kind=Event.WorkKind.SCHOOL)
        participate(school, self.user, 2)
        freetime = make_event(self.user, work_kind=Event.WorkKind.FREETIME)
        participate(freetime, self.user, 2)

        self.assertEqual(work_points(self.user), 6)

    def test_only_final_and_ended_events_count(self):
        ended_not_final = make_event(self.user, final=False)
        participate(ended_not_final, self.user, 2)
        future_final = make_event(self.user, ended=False)
        participate(future_final, self.user, 2)
        counted = make_event(self.user)
        participate(counted, self.user, 1)

        self.assertEqual(work_points(self.user), 1)

    def test_work_points_floor_and_zero_hours(self):
        long_event = make_event(self.user)
        participate(long_event, self.user, 1.75)
        zero_event = make_event(self.user)
        participate(zero_event, self.user, 0)

        self.assertEqual(work_points(self.user), 1)

    def test_earnings_share_is_proportional_to_hours(self):
        event = make_event(self.user, earnings=Decimal("100.00"))
        participate(event, self.user, 1)
        participate(event, self.other, 3)

        self.assertEqual(earnings_share(self.user), Decimal("25"))

    def test_participation_points_add_work_and_earnings_share(self):
        event = make_event(
            self.user,
            earnings=Decimal("100.00"),
            work_kind=Event.WorkKind.FREETIME,
        )
        participation = participate(event, self.user, 2)
        participate(event, self.other, 2)

        # 2 h freetime (2×) plus half of 100 € at the default 2 € per point.
        self.assertEqual(participation_points(participation), 29)

    def test_participation_points_without_hours_are_zero(self):
        event = make_event(self.user)
        participation = participate(event, self.user, 0)

        self.assertEqual(participation_points(participation), 0)

    def test_earnings_share_skips_zero_hours_and_missing_earnings(self):
        zero_event = make_event(self.user, earnings=Decimal("100.00"))
        participate(zero_event, self.user, 0)
        participate(zero_event, self.other, 0)
        no_earnings = make_event(self.user, earnings=None)
        participate(no_earnings, self.user, 2)
        future_event = make_event(self.user, earnings=Decimal("100.00"), ended=False)
        participate(future_event, self.user, 2)

        self.assertEqual(earnings_share(self.user), Decimal("0"))

    def test_total_points_combines_work_and_earnings(self):
        event = make_event(self.user, earnings=Decimal("100.00"))
        participate(event, self.user, 2)
        participate(event, self.other, 2)

        self.assertEqual(work_points(self.user), 2)
        self.assertEqual(earnings_share(self.user), Decimal("50"))
        self.assertEqual(total_points(self.user), 27)

    def test_no_events_gives_zero_points(self):
        self.assertEqual(work_points(self.user), 0)
        self.assertEqual(earnings_share(self.user), Decimal("0"))
        self.assertEqual(total_points(self.user), 0)


class EstimateServiceTests(TestCase):
    def setUp(self):
        self.a = make_student("a")
        self.b = make_student("b")
        self.abikasse = get_abikasse()
        self.abikasse.goal = Decimal("30000.00")
        self.abikasse.save()

    def test_default_ticket_count_and_base(self):
        base = ticket_base()
        self.assertEqual(base.n_est, 10)
        self.assertEqual(base.base, Decimal("3000.00"))

        estimate = ticket_estimate(self.a)
        self.assertEqual(estimate.ticket_count, 5)
        self.assertEqual(estimate.points, 0)
        self.assertEqual(estimate.credit, Decimal("0"))
        self.assertEqual(estimate.price, Decimal("3000.00"))
        self.assertEqual(estimate.total, Decimal("15000.00"))

    def test_balance_reduces_base(self):
        AbikasseEntry.objects.create(
            kind=AbikasseEntry.Kind.INCOME,
            amount=Decimal("10000.00"),
            description="Startguthaben",
            date=timezone.localdate(),
        )

        base = ticket_base()
        self.assertEqual(base.available, Decimal("10000.00"))
        self.assertEqual(base.required, Decimal("20000.00"))

        estimate = ticket_estimate(self.a)
        self.assertEqual(estimate.price, Decimal("2000.00"))
        self.assertEqual(estimate.total, Decimal("10000.00"))

    def test_credits_shift_individual_price(self):
        event = make_event(self.a, earnings=Decimal("100.00"))
        participate(event, self.a, 2)
        participate(event, self.b, 2)

        self.assertEqual(abikasse_balance(), Decimal("100.00"))
        estimate = ticket_estimate(self.a)
        self.assertEqual(estimate.points, 27)
        self.assertEqual(estimate.credit, Decimal("54.00"))
        self.assertEqual(estimate.base, Decimal("3000.80"))
        self.assertEqual(estimate.price, Decimal("2990.00"))
        self.assertEqual(estimate.total, Decimal("14950.00"))

    def test_zero_ticket_count_has_no_price(self):
        self.a.profile.ticket_count = 0
        self.a.profile.save(update_fields=["ticket_count"])

        estimate = ticket_estimate(self.a)
        self.assertEqual(estimate.ticket_count, 0)
        self.assertIsNone(estimate.price)
        self.assertIsNone(estimate.total)

    def test_price_caps_at_zero(self):
        self.abikasse.goal = Decimal("0.00")
        self.abikasse.save()
        event = make_event(self.a, earnings=Decimal("100.00"))
        participate(event, self.a, 2)
        participate(event, self.b, 2)
        AbikasseEntry.objects.all().delete()
        self.a.profile.ticket_count = 1
        self.a.profile.save(update_fields=["ticket_count"])

        estimate = ticket_estimate(self.a)
        self.assertTrue(estimate.capped)
        self.assertEqual(estimate.price, Decimal("0.00"))
        self.assertEqual(estimate.total, Decimal("0.00"))

    def test_estimate_requires_active_students(self):
        User.objects.filter(pk__in=[self.a.pk, self.b.pk]).update(is_active=False)

        self.assertIsNone(ticket_base())
        self.assertIsNone(ticket_estimate(self.a))


class LedgerServiceTests(TestCase):
    def setUp(self):
        self.user = make_student("student")

    def test_balance_income_minus_expenses(self):
        AbikasseEntry.objects.create(
            kind=AbikasseEntry.Kind.INCOME,
            amount=Decimal("100.00"),
            description="Einnahme",
            date=timezone.localdate(),
        )
        AbikasseEntry.objects.create(
            kind=AbikasseEntry.Kind.EXPENSE,
            amount=Decimal("30.00"),
            description="Ausgabe",
            date=timezone.localdate(),
        )

        self.assertEqual(abikasse_balance(), Decimal("70.00"))

    def test_final_event_books_and_updates_one_entry(self):
        event = make_event(self.user, earnings=Decimal("100.00"), title="Sommerfest")

        entry = AbikasseEntry.objects.get(event=event)
        self.assertEqual(entry.kind, AbikasseEntry.Kind.INCOME)
        self.assertEqual(entry.amount, Decimal("100.00"))
        self.assertEqual(entry.source, AbikasseEntry.Source.EVENT)
        self.assertEqual(entry.description, "Sommerfest")
        self.assertIsNone(entry.created_by)
        self.assertEqual(entry.date, timezone.localdate(event.ending_date))

        event.earnings = Decimal("120.00")
        event.save(update_fields=["earnings"])

        self.assertEqual(AbikasseEntry.objects.filter(event=event).count(), 1)
        entry.refresh_from_db()
        self.assertEqual(entry.amount, Decimal("120.00"))

        event.earnings = None
        event.save(update_fields=["earnings"])

        self.assertFalse(AbikasseEntry.objects.filter(event=event).exists())

    def test_final_event_without_earnings_has_no_entry(self):
        event = make_event(self.user, earnings=None)

        self.assertFalse(AbikasseEntry.objects.filter(event=event).exists())


class VisibilityViewTests(TestCase):
    def setUp(self):
        self.student = make_student("student")
        self.other = make_student("other")
        self.rep = make_rep_user("rep")
        self.superuser = User.objects.create_superuser(
            username="superuser", password="password"
        )
        self.superuser.profile.has_had_introduction = True
        self.superuser.profile.save(update_fields=["has_had_introduction"])
        self.client.force_login(self.student)

    def test_self_sees_points_and_estimate(self):
        response = self.client.get(reverse("user-details", args=[self.student.pk]))

        self.assertContains(response, "Arbeitspunkte")
        self.assertContains(response, "Punkte gesamt")
        self.assertContains(response, "Ticketpreis")
        self.assertContains(response, "Schätzung vom")

    def test_participation_cards_show_hours_and_points(self):
        event = make_event(self.student)
        participate(event, self.student, 2)

        response = self.client.get(reverse("user-details", args=[self.student.pk]))

        self.assertContains(response, "2:00 h")
        self.assertContains(response, "2 Punkte")

    def test_participation_cards_hide_points_from_unrelated_users(self):
        event = make_event(self.other)
        participate(event, self.other, 2)

        response = self.client.get(reverse("user-details", args=[self.other.pk]))

        self.assertContains(response, "2:00 h")
        self.assertNotContains(response, "2 Punkte")

    def test_rep_and_superuser_see_other_user_points(self):
        for user in (self.rep, self.superuser):
            self.client.force_login(user)
            response = self.client.get(reverse("user-details", args=[self.other.pk]))
            self.assertContains(response, "Arbeitspunkte")
            self.assertContains(response, "Punkte gesamt")

    def test_unrelated_student_does_not_see_other_user_points(self):
        response = self.client.get(reverse("user-details", args=[self.other.pk]))

        self.assertNotContains(response, "Arbeitspunkte")
        self.assertNotContains(response, "Punkte gesamt")
        self.assertNotContains(response, "Schätzung vom")

    def test_users_list_never_shows_points(self):
        for user in (self.student, self.rep):
            self.client.force_login(user)
            response = self.client.get(reverse("users"))
            self.assertNotContains(response, "Arbeitspunkte")
            self.assertNotContains(response, "Punkte gesamt")

    def test_points_fragment_has_no_html(self):
        response = self.client.get(
            reverse("user-details", args=[self.student.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertNotContains(response, "<html")
        self.assertContains(response, "Arbeitspunkte")


class AbikasseViewTests(TestCase):
    def setUp(self):
        self.student = make_student("student")
        self.rep = make_rep_user("rep")
        self.abikasse = get_abikasse()
        self.abikasse.goal = Decimal("30000.00")
        self.abikasse.save()
        self.entry = AbikasseEntry.objects.create(
            kind=AbikasseEntry.Kind.INCOME,
            amount=Decimal("10.00"),
            description="Geheime Buchung",
            date=timezone.localdate(),
        )

    def test_student_sees_summary_but_no_ledger(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse("abikasse"))

        self.assertContains(response, "Kassenstand")
        self.assertContains(response, "Punkte")
        self.assertContains(response, "Dein Ticketpreis")
        self.assertNotContains(response, "Eintrag hinzufügen")
        self.assertNotContains(response, "Geheime Buchung")

    def test_manager_sees_ledger_and_actions(self):
        self.client.force_login(self.rep)

        response = self.client.get(reverse("abikasse"))

        self.assertContains(response, "Eintrag hinzufügen")
        self.assertContains(response, "Einstellungen")
        self.assertContains(response, "CSV")
        self.assertContains(response, "Geheime Buchung")

    def test_entry_create_edit_delete(self):
        self.client.force_login(self.rep)

        response = self.client.post(
            reverse("abikasse-entry-create"),
            {
                "kind": "income",
                "amount": "12,50",
                "description": "Kuchen",
                "date": "2026-01-01",
                "next": reverse("abikasse"),
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        entry = AbikasseEntry.objects.get(description="Kuchen")
        self.assertEqual(entry.amount, Decimal("12.50"))
        self.assertEqual(entry.created_by, self.rep)
        self.assertEqual(entry.source, AbikasseEntry.Source.MANUAL)

        response = self.client.post(
            reverse("abikasse-entry-edit", args=[entry.pk]),
            {
                "kind": "expense",
                "amount": "5,00",
                "description": "Zutaten",
                "date": "2026-01-02",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        entry.refresh_from_db()
        self.assertEqual(entry.kind, AbikasseEntry.Kind.EXPENSE)
        self.assertEqual(entry.description, "Zutaten")

        response = self.client.post(
            reverse("abikasse-entry-delete", args=[entry.pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AbikasseEntry.objects.filter(pk=entry.pk).exists())

    def test_student_cannot_manage_entries_or_settings(self):
        self.client.force_login(self.student)

        self.assertEqual(
            self.client.post(reverse("abikasse-entry-create"), {}).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("abikasse-settings")).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("abikasse-export")).status_code,
            403,
        )

    def test_direct_overlay_gets_redirect(self):
        self.client.force_login(self.rep)

        for name in (
            "abikasse-entry-create",
            "abikasse-settings",
            "abikasse-ticket-count-edit",
        ):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302)

    def test_overlay_fragments_have_no_html(self):
        self.client.force_login(self.rep)

        for name in (
            "abikasse-entry-create",
            "abikasse-settings",
            "abikasse-ticket-count-edit",
        ):
            response = self.client.get(reverse(name), HTTP_HX_REQUEST="true")
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "<html")

    def test_invalid_htmx_forms_rerender_with_200(self):
        self.client.force_login(self.rep)

        response = self.client.post(
            reverse("abikasse-entry-create"),
            {"kind": "income", "amount": "", "description": "", "date": ""},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "errorlist")

        response = self.client.post(
            reverse("abikasse-settings"),
            {"goal": "", "point_value": "", "default_ticket_count": ""},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "errorlist")

        response = self.client.post(
            reverse("abikasse-ticket-count-edit"),
            {"ticket_count": "21"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "errorlist")

    def test_settings_updates_goal_and_config(self):
        self.client.force_login(self.rep)

        response = self.client.post(
            reverse("abikasse-settings"),
            {
                "goal": "35000",
                "point_value": "3",
                "default_ticket_count": "4",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)

        self.abikasse.refresh_from_db()
        config = AbiballConfig.objects.get(pk=1)
        self.assertEqual(self.abikasse.goal, Decimal("35000.00"))
        self.assertEqual(config.point_value, Decimal("3.00"))
        self.assertEqual(config.default_ticket_count, 4)

    def test_ticket_count_edit_updates_price(self):
        self.client.force_login(self.student)
        before = ticket_estimate(self.student).price

        response = self.client.post(
            reverse("abikasse-ticket-count-edit"),
            {"ticket_count": "3", "next": reverse("main-page")},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Redirect"], reverse("main-page"))
        self.student.profile.refresh_from_db()
        self.assertEqual(self.student.profile.ticket_count, 3)

        after = ticket_estimate(self.student).price
        self.assertNotEqual(before, after)

        response = self.client.get(reverse("main-page"))
        self.assertContains(response, "Für 3 Personen")

    def test_csv_export(self):
        self.client.force_login(self.rep)

        response = self.client.get(reverse("abikasse-export"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/csv"))
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))
        content = response.content.decode()
        self.assertIn("Datum;Art;Beschreibung;Betrag;Aktion;Erstellt von", content)
        self.assertIn("Geheime Buchung", content)


class IndexCardTests(TestCase):
    def setUp(self):
        self.student = make_student("student")
        self.other = make_student("other")
        self.abikasse = get_abikasse()
        self.abikasse.goal = Decimal("30000.00")
        self.abikasse.save()
        self.client.force_login(self.student)

    def test_index_profile_card_links_whole_card_and_compact_summary(self):
        response = self.client.get(reverse("main-page"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="profile__hit"')
        self.assertContains(response, 'aria-label="Profil öffnen"')
        self.assertContains(
            response,
            f'href="{reverse("user-details", args=[self.student.pk])}"',
        )
        self.assertContains(response, 'class="ticket-estimate__summary"')
        self.assertContains(response, "0P")
        self.assertContains(response, "→")
        self.assertContains(response, "3000,00 €")
        self.assertContains(response, "Für 5 Personen")
        self.assertContains(response, "Ändern")
        self.assertNotContains(response, "Schätzung vom")
        self.assertNotContains(response, "Dein Ticketpreis")

    def test_abikasse_ticket_card_keeps_full_labels(self):
        response = self.client.get(reverse("abikasse"))

        self.assertContains(response, "Punkte")
        self.assertContains(response, "Dein Ticketpreis")
        self.assertContains(response, "Grundpreis")
        self.assertContains(response, "Gesamt")
        self.assertContains(response, "Schätzung vom")
        self.assertNotContains(response, "ticket-estimate__summary")
