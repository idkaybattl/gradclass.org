import re
from datetime import timedelta
from decimal import Decimal

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
)
from django.contrib.auth.forms import (
    PasswordResetForm as DjangoPasswordResetForm,
)
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.forms import inlineformset_factory
from django.template import loader
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from phonenumber_field.formfields import PhoneNumberField

from .durations import format_duration, split_duration
from .models import (
    OPTION_LABEL_MAX_LENGTH,
    AbikasseEntry,
    Event,
    EventParticipation,
    Poll,
    Quote,
    QuoteLine,
    UserProfile,
)

User = get_user_model()


class LoginForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Anmeldung fehlgeschlagen. Benutzername oder Passwort ist falsch.",
        "inactive": "Dieses Konto ist deaktiviert.",
    }


class PasswordResetForm(DjangoPasswordResetForm):
    """Find accounts by iServ or external address, deliver only to the latter."""

    email = forms.EmailField(
        label="IServ- oder externe E‑Mail",
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )

    def get_users(self, email):
        return User.objects.select_related("profile").filter(
            Q(is_active=True)
            & (Q(email__iexact=email) | Q(profile__external_mail__iexact=email))
        )

    def save(
        self,
        request,
        use_https=False,
        token_generator=default_token_generator,
        from_email=None,
        subject_template_name="emails/password_reset_subject.txt",
        email_template_name="emails/password_reset.txt",
        html_email_template_name=None,
        extra_email_context=None,
    ):
        # html_email_template_name is part of the view's call signature; mails
        # stay plain text, so it is ignored.
        host = request.get_host()
        context = {
            "protocol": "https" if use_https else "http",
            "domain": host,
            **(extra_email_context or {}),
        }
        subject = "".join(
            loader.render_to_string(subject_template_name, context).splitlines()
        )

        for user in self.get_users(self.cleaned_data["email"]):
            to_email = user.profile.external_mail
            if not to_email:
                continue

            user_context = {
                **context,
                "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": token_generator.make_token(user),
                "user": user,
            }
            EmailMultiAlternatives(
                subject,
                loader.render_to_string(email_template_name, user_context),
                from_email,
                [to_email],
                reply_to=[settings.DEFAULT_REPLY_TO],
            ).send()


class UserSearchWidget(forms.Widget):
    template_name = "widgets/user_search_widget.html"
    multiple = False

    class Media:
        css = {"all": ("dashboard/css/user_search_widget.css",)}
        js = (
            "dashboard/js/search.js",
            "dashboard/js/user-picker.js",
        )

    def __init__(self, attrs=None, multiple=None):
        super().__init__(attrs)
        if multiple is not None:
            self.multiple = multiple
        self.users = []

    def set_users(self, users):
        self.users = users

    def value_from_datadict(self, data, files, name):
        if self.multiple:
            return data.getlist(name)
        return data.get(name)

    def id_for_label(self, id_):
        if not id_:
            return id_
        return f"{id_}_search"

    def format_value(self, value):
        if value is None or value == "":
            return []

        if hasattr(value, "all"):
            value = value.all()

        if isinstance(value, (list, tuple)):
            items = value
        else:
            items = [value]

        return [str(item.pk if hasattr(item, "pk") else item) for item in items]

    def _label_for_user(self, user):
        return user.get_full_name() or user.get_username()

    def get_context(self, name, value, attrs):
        formatted_value = self.format_value(value)
        selected_ids = set(formatted_value)

        all_users = [
            {"id": str(user.pk), "label": self._label_for_user(user)}
            for user in self.users
        ]

        selected_users = [user for user in all_users if user["id"] in selected_ids]
        available_users = [user for user in all_users if user["id"] not in selected_ids]

        context = super().get_context(name, formatted_value, attrs)
        context["widget"].update(
            {
                "name": name,
                "value": formatted_value,
                "values": formatted_value,
                "multiple": self.multiple,
                "selected_users": selected_users,
                "available_users": available_users,
                "all_users": all_users,
            }
        )
        return context


class ParticipantsWidget(UserSearchWidget):
    multiple = True


class ManagerPickerWidget(UserSearchWidget):
    multiple = False


class EventForm(forms.ModelForm):
    title = forms.CharField(label="Titel ", max_length=255)
    description = forms.CharField(label="Beschreibung ", widget=forms.Textarea())
    starting_date = forms.DateTimeField(
        label="Beginn ",
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local", "lang": "de-DE"},
        ),
    )
    ending_date = forms.DateTimeField(
        label="Ende ",
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local", "lang": "de-DE"},
        ),
    )
    participants = forms.ModelMultipleChoiceField(
        label="Teilnehmer ",
        queryset=User.objects.none(),
        widget=ParticipantsWidget(),
        required=False,
    )

    manager = forms.ModelChoiceField(
        label="Manager",
        queryset=User.objects.none(),
        widget=ManagerPickerWidget(),
        required=True,
    )

    def __init__(
        self,
        *args,
        users=None,
        participants_queryset=None,
        manager_queryset=None,
        request_user=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.request_user = request_user

        username_field = User.USERNAME_FIELD
        if participants_queryset is None:
            participants_queryset = User.objects.all().order_by(username_field)

        self.fields["participants"].queryset = participants_queryset

        if users is None:
            users = list(participants_queryset)

        self.fields["participants"].widget.set_users(users)

        if manager_queryset is None:
            manager_filter = Q(is_active=True)
            if self.instance and self.instance.pk and self.instance.manager_id:
                # An existing inactive manager must stay selectable on edit.
                manager_filter |= Q(pk=self.instance.manager_id)
            manager_queryset = User.objects.filter(manager_filter).order_by(
                username_field
            )

        self.fields["manager"].queryset = manager_queryset
        self.fields["manager"].widget.set_users(list(manager_queryset))

        if self.instance and self.instance.pk:
            self.fields["manager"].initial = self.instance.manager_id
        elif request_user:
            self.fields["manager"].initial = request_user.pk

    def clean(self):
        cleaned_data = super().clean()
        title = cleaned_data.get("title")
        starting_date = cleaned_data.get("starting_date")
        ending_date = cleaned_data.get("ending_date")

        if not starting_date or not ending_date:
            return cleaned_data

        if timezone.is_naive(starting_date):
            starting_date = timezone.make_aware(
                starting_date,
                timezone.get_current_timezone(),
            )
        if timezone.is_naive(ending_date):
            ending_date = timezone.make_aware(
                ending_date,
                timezone.get_current_timezone(),
            )

        if ending_date <= starting_date:
            self.add_error("ending_date", "Das Ende muss nach dem Beginn liegen.")

        duplicate_owner = (
            self.instance.creator if self.instance.pk else self.request_user
        )
        if title and duplicate_owner:
            normalized_title = self._normalize_title(title)
            duplicate_candidates = (
                Event.objects.filter(
                    creator=duplicate_owner,
                    starting_date=starting_date,
                    ending_date=ending_date,
                )
                .exclude(pk=self.instance.pk)
                .values_list("title", flat=True)
            )

            for existing_title in duplicate_candidates:
                if self._normalize_title(existing_title) == normalized_title:
                    self.add_error(
                        None,
                        "Du hast bereits eine Aktion mit gleichem Titel und Zeitfenster.",
                    )
                    break

        return cleaned_data

    def save(self, commit=True):
        # ensure manager is set (fallback to request_user or creator)
        obj = super().save(commit=False)
        if not getattr(obj, "manager_id", None):
            if self.request_user:
                obj.manager = self.request_user
            elif getattr(obj, "creator", None):
                obj.manager = obj.creator

        if commit:
            obj.save()
            self.save_m2m()
        return obj

    @staticmethod
    def _normalize_title(value):
        return " ".join(value.strip().split()).casefold()

    class Meta:
        model = Event
        fields = [
            "title",
            "manager",
            "description",
            "starting_date",
            "ending_date",
            "work_kind",
            "participants",
        ]


class DurationHMInput(forms.Widget):
    template_name = "widgets/duration_hm.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        hours, minutes = split_duration(value)
        context["widget"]["hours"] = {"name": f"{name}_hours", "value": hours}
        context["widget"]["minutes"] = {
            "name": f"{name}_minutes",
            "value": minutes,
        }
        return context

    def value_from_datadict(self, data, files, name):
        hours = data.get(f"{name}_hours")
        minutes = data.get(f"{name}_minutes")
        if not hours and not minutes:
            return None

        hours = hours or "0"
        try:
            minutes = f"{int(minutes or 0):02d}"
        except (TypeError, ValueError):
            minutes = minutes or "0"
        return f"{hours}:{minutes}"


class DurationHMField(forms.DurationField):
    """Duration field backing the two-input hours/minutes widget."""

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, timedelta):
            return value

        match = re.fullmatch(r"(?P<hours>\d+):(?P<minutes>[0-5]\d)", str(value).strip())
        if match is None:
            raise ValidationError(
                "Bitte gültige Stunden und Minuten angeben.",
                code="invalid",
            )

        return timedelta(
            hours=int(match.group("hours")),
            minutes=int(match.group("minutes")),
        )

    def prepare_value(self, value):
        if isinstance(value, timedelta):
            return format_duration(value)
        return "" if value is None else value


class ParticipationTimeForm(forms.ModelForm):
    participation_time = DurationHMField(
        label="Arbeitszeit",
        required=False,
        widget=DurationHMInput(),
    )

    class Meta:
        model = EventParticipation
        fields = ["participation_time"]

    def clean_participation_time(self):
        value = self.cleaned_data.get("participation_time")
        if value is None:
            value = timedelta(0)

        event = getattr(self.instance, "event", None)
        if event is not None:
            event_duration = event.ending_date - event.starting_date
            if value > event_duration:
                raise ValidationError(
                    "Die Arbeitszeit darf nicht länger als die Aktion sein.",
                    code="too_long",
                )

        return value


ParticipationTimeFormSet = inlineformset_factory(
    Event,
    EventParticipation,
    form=ParticipationTimeForm,
    extra=0,
    can_delete=False,
)


class EarningsField(forms.DecimalField):
    """Decimal input that accepts both German commas and dots."""

    def to_python(self, value):
        if value in self.empty_values:
            return None

        if isinstance(value, str):
            value = value.strip().replace("€", "").replace(" ", "")
            if "," in value:
                # Treat dots as thousands separators when a comma is present.
                value = value.replace(".", "").replace(",", ".")

        return super().to_python(value)

    def prepare_value(self, value):
        if value in self.empty_values:
            return ""

        if isinstance(value, Decimal):
            return f"{value:.2f}".replace(".", ",")

        return value


class SetEarningsForm(forms.ModelForm):
    earnings = EarningsField(
        label="Einnahmen",
        min_value=0,
        initial=0,
        decimal_places=2,
        widget=forms.TextInput(
            attrs={
                "aria-label": "Einnahmen in Euro",
                "inputmode": "decimal",
                "autocomplete": "off",
                "class": "input",
            }
        ),
    )

    class Meta:
        model = Event
        fields = ["earnings"]

    def clean_earnings(self):
        value = self.cleaned_data.get("earnings")
        if value is None:
            return value

        return value.quantize(Decimal("0.01"))


class SetEarningsReceivedForm(forms.ModelForm):
    earnings_received = forms.BooleanField(
        label="Eingezahlt",
        required=False,
    )

    class Meta:
        model = Event
        fields = ["earnings_received"]


class AbikasseEntryForm(forms.ModelForm):
    amount = EarningsField(
        label="Betrag",
        min_value=Decimal("0.01"),
        max_digits=10,
        decimal_places=2,
        widget=forms.TextInput(
            attrs={
                "aria-label": "Betrag in Euro",
                "inputmode": "decimal",
                "autocomplete": "off",
                "class": "input",
            }
        ),
    )
    date = forms.DateField(
        label="Datum",
        widget=forms.DateInput(
            format="%Y-%m-%d", attrs={"type": "date", "class": "input"}
        ),
    )

    class Meta:
        model = AbikasseEntry
        fields = ["kind", "amount", "description", "date"]
        labels = {
            "kind": "Art",
            "description": "Beschreibung",
        }

    def clean_amount(self):
        return self.cleaned_data["amount"].quantize(Decimal("0.01"))


class AbiballSettingsForm(forms.Form):
    goal = EarningsField(
        label="Ziel (Gesamtkosten)",
        min_value=0,
        max_digits=10,
        decimal_places=2,
        help_text="Erwartete Gesamtkosten des Abiballs.",
        widget=forms.TextInput(attrs={"inputmode": "decimal", "class": "input"}),
    )
    point_value = EarningsField(
        label="Punktwert",
        min_value=Decimal("0.01"),
        max_digits=6,
        decimal_places=2,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "class": "input"}),
    )
    default_ticket_count = forms.IntegerField(
        label="Standard-Personenzahl",
        min_value=0,
        max_value=20,
        widget=forms.NumberInput(attrs={"min": 0, "max": 20, "class": "input"}),
    )

    def __init__(self, *args, abikasse, config, **kwargs):
        super().__init__(*args, **kwargs)
        self.abikasse = abikasse
        self.config = config
        if not self.is_bound:
            self.initial.update(
                {
                    "goal": abikasse.goal,
                    "point_value": config.point_value,
                    "default_ticket_count": config.default_ticket_count,
                }
            )

    def clean(self):
        cleaned_data = super().clean()
        for field in ("goal", "point_value"):
            value = cleaned_data.get(field)
            if value is not None:
                cleaned_data[field] = value.quantize(Decimal("0.01"))
        return cleaned_data

    def save(self):
        self.abikasse.goal = self.cleaned_data["goal"]
        self.abikasse.save()

        self.config.point_value = self.cleaned_data["point_value"]
        self.config.default_ticket_count = self.cleaned_data["default_ticket_count"]
        self.config.save()
        return self.abikasse, self.config


class TicketCountForm(forms.Form):
    ticket_count = forms.IntegerField(
        label="Personen",
        min_value=0,
        max_value=20,
        widget=forms.NumberInput(
            attrs={"inputmode": "numeric", "min": 0, "max": 20, "class": "input"}
        ),
    )


class OptionListWidget(forms.Widget):
    template_name = "widgets/option_list.html"

    def value_from_datadict(self, data, files, name):
        return "\n".join(data.getlist(name))

    def format_value(self, value):
        if isinstance(value, str):
            values = value.splitlines()
        elif value:
            values = [str(item) for item in value]
        else:
            values = []

        values = [line for line in values if line.strip()]
        return values or ["", ""]

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["values"] = self.format_value(value)
        return context


class PollForm(forms.ModelForm):
    title = forms.CharField(label="Titel", max_length=255)
    description = forms.CharField(
        label="Beschreibung", required=False, widget=forms.Textarea()
    )
    mode = forms.ChoiceField(label="Modus", choices=Poll.Mode.choices)
    suggestion_deadline = forms.DateTimeField(
        label="Vorschläge bis",
        required=False,
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local", "lang": "de-DE"},
        ),
    )
    voting_deadline = forms.DateTimeField(
        label="Abstimmung bis",
        required=False,
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local", "lang": "de-DE"},
        ),
    )
    options = forms.CharField(
        label="Optionen",
        required=False,
        widget=OptionListWidget(),
        help_text="Mindestens zwei.",
    )
    suggestions_public = forms.BooleanField(
        label="Vorschläge öffentlich",
        required=False,
    )
    results_public = forms.BooleanField(
        label="Ergebnisse öffentlich",
        required=False,
    )
    max_suggestions_per_user = forms.IntegerField(
        label="Vorschläge pro Person",
        required=False,
        min_value=1,
        max_value=50,
        initial=3,
    )

    class Meta:
        model = Poll
        fields = [
            "title",
            "description",
            "mode",
            "suggestions_public",
            "results_public",
            "suggestion_deadline",
            "voting_deadline",
            "options",
            "max_suggestions_per_user",
        ]

    def clean(self):
        cleaned_data = super().clean()
        mode = cleaned_data.get("mode")
        suggestion_deadline = cleaned_data.get("suggestion_deadline")
        voting_deadline = cleaned_data.get("voting_deadline")
        now = timezone.now()

        if mode == Poll.Mode.SUGGESTIONS:
            if not suggestion_deadline:
                self.add_error(
                    "suggestion_deadline", "Bitte eine Vorschlagsfrist angeben."
                )
            elif suggestion_deadline <= now:
                self.add_error(
                    "suggestion_deadline",
                    "Die Vorschlagsfrist muss in der Zukunft liegen.",
                )
        else:
            # Fixed polls skip the suggestion phase entirely.
            cleaned_data["suggestion_deadline"] = None

        if voting_deadline and voting_deadline <= now:
            self.add_error(
                "voting_deadline",
                "Die Abstimmungsfrist muss in der Zukunft liegen.",
            )
        elif (
            voting_deadline
            and mode == Poll.Mode.SUGGESTIONS
            and suggestion_deadline
            and voting_deadline <= suggestion_deadline
        ):
            self.add_error(
                "voting_deadline",
                "Die Abstimmung muss nach den Vorschlägen enden.",
            )
        elif mode == Poll.Mode.FIXED and not voting_deadline:
            self.add_error(
                "voting_deadline",
                "Bitte eine Abstimmungsfrist angeben.",
            )

        labels = [line.strip() for line in cleaned_data.get("options", "").splitlines()]
        labels = [label for label in labels if label]
        if mode == Poll.Mode.FIXED:
            if len(labels) < 2:
                self.add_error("options", "Bitte mindestens zwei Optionen angeben.")
            if any(len(label) > OPTION_LABEL_MAX_LENGTH for label in labels):
                self.add_error(
                    "options",
                    f"Eine Option darf höchstens {OPTION_LABEL_MAX_LENGTH} Zeichen haben.",
                )
        else:
            labels = []

        cleaned_data["option_labels"] = labels

        if cleaned_data.get("max_suggestions_per_user") is None:
            cleaned_data["max_suggestions_per_user"] = 3

        return cleaned_data


class StartVotingForm(forms.Form):
    voting_deadline = forms.DateTimeField(
        label="Abstimmung bis",
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local", "lang": "de-DE"},
        ),
        help_text="Die Abstimmung endet zu diesem Zeitpunkt automatisch.",
    )

    def clean_voting_deadline(self):
        value = self.cleaned_data["voting_deadline"]
        if value <= timezone.now():
            raise ValidationError("Die Abstimmungsfrist muss in der Zukunft liegen.")
        return value


class SuggestionDeadlineForm(forms.Form):
    suggestion_deadline = forms.DateTimeField(
        label="Neue Vorschlagsfrist",
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local", "lang": "de-DE"},
        ),
        help_text="Die Vorschlagsphase läuft bis zu diesem Zeitpunkt.",
    )


class ExternalMailForm(forms.ModelForm):
    external_mail = forms.EmailField(
        label="Externe E‑Mail",
        required=False,
        widget=forms.EmailInput(attrs={"autocomplete": "email", "inputmode": "email"}),
    )

    class Meta:
        model = UserProfile
        fields = ["external_mail"]


class ProfileDetailsForm(forms.ModelForm):
    birthday = forms.DateField(
        label="Geburtsdatum",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    phone_number = PhoneNumberField(
        label="Telefonnummer",
        region="DE",
        required=False,
    )
    bio = forms.Textarea()

    class Meta:
        model = UserProfile
        fields = ["phone_number", "birthday", "bio"]


class UserProfileForm(ExternalMailForm, ProfileDetailsForm):
    class Meta:
        model = UserProfile
        fields = ["external_mail", "phone_number", "birthday", "bio"]


class QuoteForm(forms.ModelForm):
    class Meta:
        model = Quote
        fields = ["extra_info", "spoken_on"]
        labels = {
            "extra_info": "Zusatzinfo (optional)",
            "spoken_on": "Datum",
        }
        widgets = {
            "spoken_on": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        }


class QuoteLineForm(forms.ModelForm):
    class Meta:
        model = QuoteLine
        fields = ["speaker", "text"]
        labels = {"speaker": "Sprecher", "text": "Text"}
        widgets = {
            "speaker": forms.TextInput(attrs={"list": "quote-speaker-options"}),
            "text": forms.Textarea(attrs={"rows": 2}),
        }


QuoteLineFormSet = inlineformset_factory(
    Quote,
    QuoteLine,
    form=QuoteLineForm,
    extra=0,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


class QuoteReportForm(forms.Form):
    reason = forms.CharField(
        label="Grund (optional)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
