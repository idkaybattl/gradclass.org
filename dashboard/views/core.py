from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_GET

from ..intro import introduction_required
from ..models import Abikasse

User = get_user_model()


@login_required
@require_GET
@introduction_required
def main_page(request):
    abikasse, _ = Abikasse.objects.get_or_create(
        pk=1,
        defaults={
            "goal": 30000,
        },
    )

    return render(
        request,
        "index.html",
        {
            "abikasse_current": abikasse.total_earnings(),
            "abikasse_goal": abikasse.goal,
        },
    )


@login_required
@require_GET
@introduction_required
def calendar(request):
    return render(request, "calendar.html")


def _get_contact_user():
    users = User.objects.select_related("profile")
    if settings.CONTACT_USER_ID:
        return users.filter(pk=settings.CONTACT_USER_ID).first()
    return users.filter(is_superuser=True, is_active=True).order_by("pk").first()


@login_required
@require_GET
@introduction_required
def contact(request):
    contact_user = _get_contact_user()
    contact_profile = getattr(contact_user, "profile", None)
    return render(
        request,
        "contact.html",
        {"contact_user": contact_user, "contact_profile": contact_profile},
    )


@login_required
@require_GET
@introduction_required
def polls(request):
    return render(request, "polls.html")
