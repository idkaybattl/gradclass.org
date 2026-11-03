from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

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

VALID_INITIAL_STEPS = {
    "step-1",
    "step-2",
    "step-3",
    "step-4",
    "step-5",
    "step-6",
    "password",
    "profile",
}


def introduction_context(
    request,
    *,
    profile_form=None,
    password_form=None,
    initial_step="step-1",
):
    profile = request.user.profile
    if profile_form is None:
        profile_form = UserProfileForm(instance=profile)
    if password_form is None:
        password_form = SetPasswordForm(request.user)

    return {
        "profile_form": profile_form,
        "password_form": password_form,
        "user": request.user,
        "next_url": get_safe_next_url(request),
        "initial_step": initial_step,
    }


@login_required
@require_POST
def password_set(request):
    form = SetPasswordForm(request.user, request.POST)
    if form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)

        if is_htmx_request(request):
            response = HttpResponse(status=204)
            response["HX-Trigger"] = "intro:password-set"
            return response

        return redirect("introduction")

    if is_htmx_request(request):
        return render(
            request,
            "introduction/_password_form.html",
            {"password_form": form},
        )

    return render(
        request,
        "introduction.html",
        introduction_context(request, password_form=form, initial_step="password"),
    )


@login_required
@require_http_methods(["GET", "POST"])
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
        if not is_htmx_request(request):
            return redirect(user_details_url(user))
        form = form_class(user)

    template = (
        "users/_password_form.html"
        if is_htmx_request(request)
        else "users/password.html"
    )
    return render(
        request,
        template,
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
@require_http_methods(["GET", "POST"])
def introduction(request):
    profile = request.user.profile

    if request.method == "POST":
        profile_form = UserProfileForm(request.POST, instance=profile)
        if profile_form.is_valid():
            profile_form.save()
            # Mark the introduction as completed
            profile.has_had_introduction = True
            profile.save(update_fields=["has_had_introduction"])

            if is_htmx_request(request):
                next_url = get_safe_next_url(request) or reverse("main-page")
                return render_feedback(
                    request,
                    get_feedback(
                        "intro-profile-saved",
                        action_url=next_url,
                        action_label="Weiter zur Startseite",
                    ),
                )

            # Respect a ?next= parameter if present
            return redirect_next_or(request, "main-page")

        if is_htmx_request(request):
            return render(
                request,
                "introduction/_profile_form.html",
                {
                    "profile_form": profile_form,
                    "next_url": get_safe_next_url(request),
                },
            )

        return render(
            request,
            "introduction.html",
            introduction_context(
                request,
                profile_form=profile_form,
                initial_step="profile",
            ),
        )

    initial_step = request.GET.get("step") or "step-1"
    if initial_step not in VALID_INITIAL_STEPS:
        initial_step = "step-1"

    return render(
        request,
        "introduction.html",
        introduction_context(request, initial_step=initial_step),
    )
