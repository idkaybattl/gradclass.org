from django import forms
from django.contrib.auth import get_user_model

from .models import Project

User = get_user_model()


class ProjectForm(forms.ModelForm):
    title = forms.CharField(label="Titel ", max_length=255)
    description = forms.CharField(label="Beschreibung ", widget=forms.Textarea())
    starting_date = forms.DateTimeField(label="Beginn ")
    ending_date = forms.DateTimeField(label="Ende ")
    participants = forms.ModelMultipleChoiceField(
        queryset=User.objects.all(),
        widget=forms.MultipleHiddenInput,
        required=False,
    )

    class Meta:
        model = Project
        fields = [
            "title",
            "description",
            "starting_date",
            "ending_date",
            "participants",
        ]
