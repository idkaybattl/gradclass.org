from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from ..feedback import get_feedback
from ..intro import introduction_required
from ..models import Event, Poll
from ..services import abikasse_balance, get_abikasse
from .abikasse import ticket_context

User = get_user_model()


def _upcoming_events():
    return Event.objects.filter(ending_date__gt=timezone.now()).order_by(
        "starting_date"
    )


def _open_polls():
    return [
        poll
        for poll in Poll.objects.filter(published_at__isnull=False).order_by(
            "-created_at"
        )
        if poll.phase not in {Poll.Phase.DRAFT, Poll.Phase.CLOSED}
    ]


@login_required
@require_GET
@introduction_required
def main_page(request):
    abikasse = get_abikasse()

    return render(
        request,
        "index.html",
        {
            "abikasse_current": abikasse_balance(),
            "abikasse_goal": abikasse.goal,
            "upcoming_events": _upcoming_events(),
            "open_polls": _open_polls(),
            "feedback": get_feedback(request.GET.get("status")),
            **ticket_context(request, default_next=reverse("main-page")),
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


@require_GET
def datenschutz(request):
    contact_user = _get_contact_user()
    contact_profile = getattr(contact_user, "profile", None)
    return render(
        request,
        "legal/privacy.html",
        {"contact_user": contact_user, "contact_profile": contact_profile},
    )
