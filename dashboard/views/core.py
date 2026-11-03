from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_GET

from ..intro import introduction_required
from ..models import Abikasse


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
@introduction_required
def calendar(request):
    return render(request, "calendar.html")


@login_required
@require_GET
@introduction_required
def contact(request):
    return render(request, "contact.html")


@login_required
@require_GET
@introduction_required
def polls(request):
    return render(request, "polls.html")
