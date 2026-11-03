from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..feedback import get_feedback, render_feedback
from ..forms import UserProfileForm
from ..http_helpers import (
    get_safe_back_url,
    get_safe_next_url,
    is_htmx_request,
    redirect_next_or,
)
from ..permissions import can_change_password
from .users import user_details_url

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
    user = get_object_or_404(User, pk=user_id)

    if not can_change_password(request, user_id):
        feedback = get_feedback(
            "password-denied",
            action_url=user_details_url(user),
            action_label="Zum Profil",
            action_htmx=True,
        )
        if is_htmx_request(request):
            return render_feedback(request, feedback)

        return redirect(user_details_url(user, status="password-denied"))

    form_class = PasswordChangeForm if user == request.user else SetPasswordForm
    back_url = get_safe_back_url(request) or user_details_url(user)
    next_url = get_safe_next_url(request)

    if request.method == "POST":
        form = form_class(user, request.POST)

        if form.is_valid():
            changed_user = form.save()
            if changed_user == request.user:
                update_session_auth_hash(request, changed_user)

            if is_htmx_request(request):
                return render_feedback(
                    request,
                    get_feedback(
                        "password-updated",
                        action_url=back_url,
                        action_label="Zurück zum Profil",
                        action_htmx=True,
                    ),
                )

            return redirect(user_details_url(changed_user, status="password-updated"))
    else:
        form = form_class(user)

    return render(
        request,
        "users/_password_form.html",
        {
            "form": form,
            "user": user,
            "display_name": user.get_full_name() or user.username,
            "password_title": f"Passwort ändern für {user.get_full_name() or user.username}",
            "back_url": back_url,
            "next_url": next_url,
        },
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
