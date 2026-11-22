from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import Quote, QuoteLine, QuoteReport
from ..notifications import Notification, NotificationVerbChoices
from .helpers import User, make_rep


def mark_introduced(user):
    user.profile.has_had_introduction = True
    user.profile.save(update_fields=["has_had_introduction"])


class QuoteTestCase(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="student", password="password")
        self.other = User.objects.create_user(username="other", password="password")
        self.rep = make_rep("rep")
        for user in (self.student, self.other, self.rep):
            mark_introduced(user)

    def make_quote(self, *, uploader=None, spoken_on="2026-11-11", extra_info=""):
        return Quote.objects.create(
            uploader=uploader or self.student,
            spoken_on=spoken_on,
            extra_info=extra_info,
        )

    def line(self, quote, speaker, text, position=0):
        return QuoteLine.objects.create(
            quote=quote, speaker=speaker, text=text, position=position
        )

    def quote_data(self, lines, *, extra_info="", spoken_on="2026-11-22"):
        data = {
            "extra_info": extra_info,
            "spoken_on": spoken_on,
            "lines-TOTAL_FORMS": str(len(lines)),
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "1",
            "lines-MAX_NUM_FORMS": "1000",
        }
        for index, (speaker, text) in enumerate(lines):
            data[f"lines-{index}-speaker"] = speaker
            data[f"lines-{index}-text"] = text
        return data


class QuoteCreateTests(QuoteTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.student)

    def test_create_with_one_line_sets_uploader_date_and_position(self):
        response = self.client.post(
            reverse("quote-create"),
            self.quote_data(
                [("Max und Moritz", "Wir sind hier, um zu bleiben.")],
                extra_info="Bio LK",
                spoken_on="2026-11-11",
            ),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        quote = Quote.objects.get()
        self.assertEqual(quote.uploader, self.student)
        self.assertEqual(quote.spoken_on, date(2026, 11, 11))
        self.assertEqual(quote.extra_info, "Bio LK")
        line = quote.lines.get()
        self.assertEqual(line.speaker, "Max und Moritz")
        self.assertEqual(line.text, "Wir sind hier, um zu bleiben.")
        self.assertEqual(line.position, 0)

    def test_create_preserves_row_order_and_ignores_blank_rows(self):
        response = self.client.post(
            reverse("quote-create"),
            self.quote_data(
                [
                    ("Max", "Hast du die Klausur gelernt?"),
                    ("Moritz", "Ich habe sie mir angeschaut."),
                    ("", ""),
                ]
            ),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        lines = list(Quote.objects.get().lines.values_list("speaker", "position"))
        self.assertEqual(lines, [("Max", 0), ("Moritz", 1)])

    def test_missing_or_empty_line_is_rejected(self):
        blank_response = self.client.post(
            reverse("quote-create"),
            self.quote_data([("", "")]),
            HTTP_HX_REQUEST="true",
        )
        zero_response = self.client.post(
            reverse("quote-create"),
            {
                "extra_info": "",
                "spoken_on": "2026-11-22",
                "lines-TOTAL_FORMS": "0",
                "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "1",
                "lines-MAX_NUM_FORMS": "1000",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(blank_response.status_code, 200)
        self.assertEqual(zero_response.status_code, 200)
        self.assertFalse(Quote.objects.exists())

    def test_invalid_htmx_create_rerenders_partial(self):
        response = self.client.post(
            reverse("quote-create"),
            self.quote_data([("", "")]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<html")
        self.assertContains(response, "Zeile hinzufügen")
        self.assertFalse(Quote.objects.exists())

    def test_direct_get_redirects_to_list(self):
        response = self.client.get(reverse("quote-create"))

        self.assertRedirects(response, reverse("quotes"))


class QuoteListTests(QuoteTestCase):
    def test_single_line_and_dialogue_cards_render(self):
        single = self.make_quote(extra_info="Bio LK")
        self.line(single, "Max und Moritz", "Wir sind hier, um zu bleiben.")

        dialogue = self.make_quote(uploader=self.other, extra_info="Bio LK")
        self.line(dialogue, "Max", "Hast du die Klausur gelernt?", position=0)
        self.line(dialogue, "Moritz", "Ich habe sie mir angeschaut.", position=1)

        self.client.force_login(self.student)
        response = self.client.get(reverse("quotes"))
        body = " ".join(response.content.decode().split())

        self.assertContains(response, "Wir sind hier, um zu bleiben.")
        self.assertIn("— Max und Moritz (Bio LK)", body)
        self.assertContains(response, "Hast du die Klausur gelernt?")
        self.assertContains(response, "Ich habe sie mir angeschaut.")
        self.assertContains(response, "Max:")
        self.assertContains(response, "Moritz:")

    def test_list_order_is_spoken_on_then_created_at(self):
        newest = self.make_quote(spoken_on="2026-02-01")
        later_created = self.make_quote(spoken_on="2026-01-01")
        earlier_created = self.make_quote(spoken_on="2026-01-01")
        now = timezone.now()
        Quote.objects.filter(pk=later_created.pk).update(
            created_at=now - timedelta(hours=1)
        )
        Quote.objects.filter(pk=earlier_created.pk).update(
            created_at=now - timedelta(days=1)
        )

        self.client.force_login(self.student)
        response = self.client.get(reverse("quotes"))

        pks = [quote.pk for quote in response.context["quotes"]]
        self.assertEqual(pks, [newest.pk, later_created.pk, earlier_created.pk])

    def test_reports_section_is_only_for_managers(self):
        quote = self.make_quote()
        self.line(quote, "Max", "Text")
        QuoteReport.objects.create(quote=quote, reporter=self.other, reason="Grund")

        self.client.force_login(self.student)
        self.assertNotContains(self.client.get(reverse("quotes")), "Offene Meldungen")

        self.client.force_login(self.rep)
        self.assertContains(self.client.get(reverse("quotes")), "Offene Meldungen")

    def test_anonymous_access_redirects_to_login(self):
        for name in ("quotes", "quote-create"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login", response["Location"])
            self.assertIn("next=", response["Location"])


class QuoteDeleteTests(QuoteTestCase):
    def test_uploader_can_delete_own_quote(self):
        quote = self.make_quote(uploader=self.student)
        self.client.force_login(self.student)

        response = self.client.post(reverse("quote-delete", args=[quote.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertIn("quote-deleted", response["Location"])
        self.assertFalse(Quote.objects.filter(pk=quote.pk).exists())

    def test_unrelated_student_cannot_delete(self):
        quote = self.make_quote(uploader=self.student)
        self.client.force_login(self.other)

        response = self.client.post(reverse("quote-delete", args=[quote.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertIn("quote-delete-denied", response["Location"])
        self.assertTrue(Quote.objects.filter(pk=quote.pk).exists())

    def test_manager_can_delete_any_quote(self):
        quote = self.make_quote(uploader=self.student)
        self.client.force_login(self.rep)

        response = self.client.post(reverse("quote-delete", args=[quote.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertIn("quote-deleted", response["Location"])
        self.assertFalse(Quote.objects.filter(pk=quote.pk).exists())

    def test_delete_requires_post(self):
        quote = self.make_quote(uploader=self.student)
        self.client.force_login(self.student)

        self.assertEqual(
            self.client.get(reverse("quote-delete", args=[quote.pk])).status_code,
            405,
        )


class QuoteReportTests(QuoteTestCase):
    def setUp(self):
        super().setUp()
        self.quote = self.make_quote(uploader=self.student)
        self.line(self.quote, "Max", "Wir sind hier, um zu bleiben.")

    def test_report_creates_row_and_notifies_managers(self):
        self.client.force_login(self.other)

        response = self.client.post(
            reverse("quote-report", args=[self.quote.pk]),
            {"reason": "Enthält private Informationen."},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("quote-reported", response["Location"])
        report = QuoteReport.objects.get()
        self.assertEqual(report.quote, self.quote)
        self.assertEqual(report.reporter, self.other)
        self.assertEqual(report.reason, "Enthält private Informationen.")

        notification = Notification.objects.get(
            user=self.rep, verb=NotificationVerbChoices.QUOTE_REPORTED
        )
        self.assertEqual(notification.target, report)
        self.assertEqual(notification.get_url(), f"{reverse('quotes')}#reports")

    def test_duplicate_report_is_rejected(self):
        QuoteReport.objects.create(quote=self.quote, reporter=self.other)
        self.client.force_login(self.other)

        response = self.client.post(reverse("quote-report", args=[self.quote.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertIn("quote-already-reported", response["Location"])
        self.assertEqual(QuoteReport.objects.count(), 1)

    def test_duplicate_report_htmx_returns_feedback(self):
        QuoteReport.objects.create(quote=self.quote, reporter=self.other)
        self.client.force_login(self.other)

        response = self.client.post(
            reverse("quote-report", args=[self.quote.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "bereits gemeldet")
        self.assertEqual(QuoteReport.objects.count(), 1)

    def test_uploader_cannot_report_own_quote(self):
        self.client.force_login(self.student)

        response = self.client.post(reverse("quote-report", args=[self.quote.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertIn("quote-report-denied", response["Location"])
        self.assertFalse(QuoteReport.objects.exists())

    def test_report_overlay_get_and_direct_redirect(self):
        self.client.force_login(self.other)

        fragment = self.client.get(
            reverse("quote-report", args=[self.quote.pk]),
            HTTP_HX_REQUEST="true",
        )
        direct = self.client.get(reverse("quote-report", args=[self.quote.pk]))

        self.assertEqual(fragment.status_code, 200)
        self.assertNotContains(fragment, "<html")
        self.assertContains(fragment, "Zitat melden")
        self.assertRedirects(direct, reverse("quotes"))


class QuoteReportDismissTests(QuoteTestCase):
    def setUp(self):
        super().setUp()
        quote = self.make_quote(uploader=self.student)
        self.report = QuoteReport.objects.create(quote=quote, reporter=self.other)

    def test_manager_can_dismiss_report(self):
        self.client.force_login(self.rep)

        response = self.client.post(
            reverse("quote-report-dismiss", args=[self.report.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("report-dismissed", response["Location"])
        self.assertFalse(QuoteReport.objects.exists())

    def test_non_manager_cannot_dismiss_report(self):
        self.client.force_login(self.student)

        response = self.client.post(
            reverse("quote-report-dismiss", args=[self.report.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("report-dismiss-denied", response["Location"])
        self.assertTrue(QuoteReport.objects.filter(pk=self.report.pk).exists())
