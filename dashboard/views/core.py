from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_GET

from ..intro import introduction_required
from ..models import Abikasse
from ..permissions import can_view_users

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
    all_users = User.objects.select_related("profile")
    users_with_hours = [
        {"user": user, "hours": user.profile.total_hours()} for user in all_users
    ]

    # Rank everyone, including 0-hour users, so ranks reflect true standing
    full_ranking = sorted(
        users_with_hours, key=lambda entry: entry.get("hours", 0), reverse=True
    )

    for i, entry in enumerate(full_ranking):
        if i > 0 and full_ranking[i - 1]["hours"] == entry["hours"]:
            entry["rank"] = full_ranking[i - 1]["rank"]
        else:
            entry["rank"] = i + 1

    # Find the request user's true rank before any filtering
    user_entry = next(entry for entry in full_ranking if entry["user"] == request.user)

    # Now filter out 0-hour users and cut to top 10 for display
    ranking = [entry for entry in full_ranking if entry["hours"] > timedelta(0)][:10]

    user_in_ranking = any(entry["user"] == request.user for entry in ranking)
    if not user_in_ranking:
        ranking.append(user_entry)

    return render(
        request,
        "index.html",
        {
            "abikasse_current": abikasse.total_earnings(),
            "abikasse_goal": abikasse.goal,
            "can_view_users": can_view_users(request),
            "ranking": ranking,
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
