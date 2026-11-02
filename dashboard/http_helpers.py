"""URL and HTMX response helpers shared by view modules.

This is the only module that reads the ``next``/``back`` hints and the only
module that emits ``HX-Redirect``.
"""

from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme


def _get_safe_url(request, value):
    if not value:
        return None

    if url_has_allowed_host_and_scheme(
        value,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return value

    return None


def get_safe_next_url(request):
    return _get_safe_url(request, request.POST.get("next") or request.GET.get("next"))


def get_safe_back_url(request):
    return _get_safe_url(request, request.GET.get("back"))


def redirect_next_or(request, fallback, **kwargs):
    next_url = get_safe_next_url(request)
    url = next_url or reverse(fallback, kwargs=kwargs)

    if is_htmx_request(request):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = url
        return response

    return redirect(url)


def is_htmx_request(request):
    return request.headers.get("HX-Request") == "true"


def render_page_or_partial(request, page_template, partial_template, context):
    template = partial_template if is_htmx_request(request) else page_template
    return render(request, template, context)
