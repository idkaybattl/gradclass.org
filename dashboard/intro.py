"""Forced first-run introduction helpers.

The introduction is a full page, not an overlay, so it only needs a redirect
check and a view decorator.
"""

from functools import wraps

from django.shortcuts import redirect


def redirect_if_introduction_needed(request):
    """Return a redirect to the introduction until the user finished it."""
    # Callers are behind @login_required, so request.user is authenticated.
    if not request.user.profile.has_had_introduction:
        return redirect("introduction")
    return None


def introduction_required(view_func):
    """Require a finished introduction before running the view."""

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        response = redirect_if_introduction_needed(request)
        if response:
            return response
        return view_func(request, *args, **kwargs)

    return wrapped
