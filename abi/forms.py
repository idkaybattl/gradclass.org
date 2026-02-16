from django import forms
from django.contrib.auth import get_user_model

from .models import Project

User = get_user_model()


class ParticipantsWidget(forms.Widget):
    template_name = "widgets/participants_widget.html"

    class Media:
        css = {"all": ("abi/participants_widget.css",)}
        js = ("abi/js/participants_widget.js",)

    def __init__(self, attrs=None):
        super().__init__(attrs)
        self.users = []

    def set_users(self, users):
        self.users = users

    def value_from_datadict(self, data, files, name):
        return data.getlist(name)

    def id_for_label(self, id_):
        if not id_:
            return id_
        return f"{id_}_search"

    def format_value(self, value):
        if value is None:
            return []

        if hasattr(value, "all"):
            value = value.all()

        return [str(item.pk if hasattr(item, "pk") else item) for item in value]

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
                "selected_users": selected_users,
                "available_users": available_users,
            }
        )
        return context


class ProjectForm(forms.ModelForm):
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

    def __init__(self, *args, users=None, participants_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)

        if participants_queryset is None:
            username_field = User.USERNAME_FIELD
            participants_queryset = User.objects.all().order_by(username_field)

        self.fields["participants"].queryset = participants_queryset

        if users is None:
            users = list(participants_queryset)

        self.fields["participants"].widget.set_users(users)

    class Meta:
        model = Project
        fields = [
            "title",
            "description",
            "starting_date",
            "ending_date",
            "participants",
        ]
