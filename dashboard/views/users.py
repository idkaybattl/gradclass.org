from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from ..forms import UserProfileForm
from ..http_helpers import get_safe_next_url, redirect_next_or
from ..permissions import can_edit_user, can_view_users

User = get_user_model()


@login_required
@require_GET
def users(request):
    if not can_view_users(request):
        messages.error(request, "Du bist nicht berechtigt die Benutzer anzuzeigen.")
        return redirect_next_or(request, "main-page")

    users = set(User.objects.all())

    return render(request, "users.html", {"users": users})


@login_required
@require_GET
def user_details(request, user_id):
    if not can_view_users(request):
        messages.error(request, "Du bist nicht berechtigt die Benutzer anzuzeigen.")
        return redirect_next_or(request, "users")

    user = get_object_or_404(User, pk=user_id)
    total_hours = user.profile.total_hours()
    total_earnings = user.profile.total_earnings()
    event_participations = set(user.event_participations.all())
    can_edit = can_edit_user(request, user_id)
    can_change_password = request.user.is_staff or request.user.id == user_id

    return render(
        request,
        "components/_user_details.html",
        {
            "user": user,
            "total_hours": total_hours,
            "total_earnings": total_earnings,
            "event_participations": event_participations,
            "can_edit": can_edit,
            "can_change_password": can_change_password,
            "next_url": get_safe_next_url(request),
        },
    )


@login_required
def edit_user(request, user_id):
    if not can_edit_user(request, user_id):
        messages.error(
            request, "Du bist nicht berechtigt dieses Nutzerprofil zu bearbeiten"
        )
        return redirect_next_or(request, "users")

    user = get_object_or_404(User, pk=user_id)

    if request.method == "POST":
        form = UserProfileForm(request.POST, instance=user.profile)

        if form.is_valid():
            form.save()
            messages.success(request, "Profil erfolgreich aktualisiert.")
            return render(request, "components/_user_edit_success.html", {"user": user})
        else:
            messages.error(request, "Form ist invalide.")
            # render the partial with errors (status 400)
            return render(
                request,
                "components/_user_edit.html",
                {"form": form, "user": user, "next_url": get_safe_next_url(request)},
            )

    else:
        form = UserProfileForm(instance=user.profile)
        return render(
            request,
            "components/_user_edit.html",
            {"form": form, "user": user, "next_url": get_safe_next_url(request)},
        )
