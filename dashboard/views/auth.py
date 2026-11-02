from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from ..forms import UserProfileForm
from ..http_helpers import get_safe_next_url, redirect_next_or
from ..permissions import can_edit_user

User = get_user_model()


def redirect_if_introduction_needed(request):
    """
    Helper used by views that should force the user through the introduction
    before accessing the main site.
    """
    # The user is guaranteed to be authenticated (all callers are @login_required)
    profile = request.user.profile
    if not profile.has_had_introduction:
        return redirect("introduction")  # name of the URL pattern
    return None


@login_required
@require_POST
def password_set(request):
    form = SetPasswordForm(request.user, request.POST)
    if form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        return JsonResponse({"success": True})
    return JsonResponse({"success": False})


@login_required
def change_password_popup(request, user_id):
    if request.method == "POST":
        user = User.objects.get(pk=user_id)
        form = PasswordChangeForm(user, request.POST)
        if form.is_valid():
            print("valid form")
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Dein Passwort wurde erfolgreich geändert.")
            # Build the same context user_details uses
            total_hours = user.profile.total_hours()
            total_earnings = user.profile.total_earnings()
            event_participations = set(user.event_participations.all())
            can_edit = can_edit_user(request, user_id)
            can_change_password = request.user.is_staff or request.user.id == user_id

            html = render_to_string(
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
                request=request,
            )
            return HttpResponse(html)

        # ----- FAILURE -----
        # Render the form again (with errors) and send it back
        print("invalid form")
        html = render_to_string(
            "components/_user_change_password.html",
            {"user": user, "form": form, "next_url": request.GET.get("next")},
            request=request,
        )
        return HttpResponse(html, status=200)

    user = User.objects.get(pk=user_id)
    form = PasswordChangeForm(user)
    return render(
        request,
        "components/_user_change_password.html",
        {"form": form, "user": user, "next_url": request.GET.get("next")},
    )


@login_required
def introduction(request):
    profile = request.user.profile

    if request.method == "POST":
        profile_form = UserProfileForm(request.POST, instance=profile)
        if profile_form.is_valid():
            profile_form.save()
            # Mark the introduction as completed
            profile.has_had_introduction = True
            profile.save(update_fields=["has_had_introduction"])

            messages.success(request, "Dein Profil wurde gespeichert.")
            # Respect a ?next= query‑parameter if present
            return redirect_next_or(request, "main-page")
        # If the form is invalid we fall through to the template rendering
        # so the user can correct the errors.
    else:
        profile_form = UserProfileForm(instance=profile)

    password_form = SetPasswordForm(request.user)

    return render(
        request,
        "introduction.html",
        {
            "profile_form": profile_form,
            "password_form": password_form,
            "user": request.user,
            "next_url": get_safe_next_url(request),
        },
    )
