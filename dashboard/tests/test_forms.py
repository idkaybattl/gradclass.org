from datetime import timedelta
from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from ..durations import split_duration
from ..forms import DurationHMField, DurationHMInput, SetEarningsForm
from ..models import Event
from .helpers import User


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
