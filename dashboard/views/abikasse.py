import csv
from decimal import Decimal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from ..feedback import get_feedback, render_feedback
from ..forms import AbiballSettingsForm, AbikasseEntryForm, TicketCountForm
from ..http_helpers import (
    get_safe_back_url,
    get_safe_next_url,
    is_htmx_request,
    redirect_next_or,
)
from ..intro import introduction_required
from ..models import AbikasseEntry
from ..permissions import can_manage_abikasse, can_view_abikasse
from ..services import (
    DEFAULT_TICKET_COUNT,
    abikasse_balance,
    get_abiball_config,
    get_abikasse,
    get_or_create_abiball_config,
    ticket_estimate,
    total_points,
)


def abikasse_url(status: str | None = None) -> str:
    url = reverse("abikasse")
    if status:
        url = f"{url}?{urlencode({'status': status})}"
    return url


def _status_url(url: str, status: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query["status"] = status
    return urlunsplit(parts._replace(query=urlencode(query)))


def ticket_context(request, *, default_next=None, compact=False):
    profile = getattr(request.user, "profile", None)
    if profile is not None:
        ticket_count = profile.ticket_count
    else:
        config = get_abiball_config()
        ticket_count = (
            config.default_ticket_count if config is not None else DEFAULT_TICKET_COUNT
        )

    estimate = ticket_estimate(request.user)
    next_url = get_safe_next_url(request) or default_next
    edit_url = reverse("abikasse-ticket-count-edit")
    if next_url:
        edit_url = f"{edit_url}?{urlencode({'next': next_url})}"

    return {
        "ticket_estimate": estimate,
        "points_total": (
            estimate.points if estimate is not None else total_points(request.user)
        ),
        "ticket_count": ticket_count,
        "ticket_count_edit_url": edit_url,
        "next_url": next_url,
        "compact": compact,
    }


@login_required
@require_GET
@introduction_required
def abikasse(request):
    if not can_view_abikasse(request.user):
        raise PermissionDenied

    abikasse_obj = get_abikasse()
    balance = abikasse_balance()
    goal = abikasse_obj.goal
    progress = 0
    if goal and goal > 0:
        progress = int(min(Decimal("100"), max(Decimal("0"), balance / goal * 100)))

    may_manage = can_manage_abikasse(request.user)
    entries = None
    if may_manage:
        entries = list(AbikasseEntry.objects.select_related("event", "created_by"))

    return render(
        request,
        "abikasse.html",
        {
            "abikasse": abikasse_obj,
            "balance": balance,
            "goal": goal,
            "progress": progress,
            "can_manage": may_manage,
            "entries": entries,
            "entry_create_url": reverse("abikasse-entry-create"),
            "settings_url": reverse("abikasse-settings"),
            "export_url": reverse("abikasse-export"),
            "feedback": get_feedback(request.GET.get("status")),
            **ticket_context(request, default_next=reverse("abikasse")),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def entry_create(request):
    if not can_manage_abikasse(request.user):
        raise PermissionDenied

    back_url = get_safe_back_url(request)
    next_url = get_safe_next_url(request)

    if request.method == "POST":
        form = AbikasseEntryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.created_by = request.user
            entry.source = AbikasseEntry.Source.MANUAL
            entry.save()

            if is_htmx_request(request):
                return render_feedback(
                    request,
                    get_feedback(
                        "abikasse-entry-created",
                        action_url=abikasse_url(),
                        action_label="Zur Abikasse",
                    ),
                )

            return redirect(
                _status_url(next_url or abikasse_url(), "abikasse-entry-created")
            )
    else:
        if not is_htmx_request(request):
            return redirect("abikasse")
        form = AbikasseEntryForm(initial={"date": timezone.localdate()})

    template = (
        "abikasse/_entry_form.html"
        if is_htmx_request(request)
        else "abikasse/form.html"
    )
    return render(
        request,
        template,
        {
            "form": form,
            "mode": "create",
            "back_url": back_url,
            "next_url": next_url,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def entry_edit(request, entry_id):
    if not can_manage_abikasse(request.user):
        raise PermissionDenied

    entry = get_object_or_404(AbikasseEntry, pk=entry_id)
    back_url = get_safe_back_url(request)
    next_url = get_safe_next_url(request)

    if request.method == "POST":
        form = AbikasseEntryForm(request.POST, instance=entry)
        if form.is_valid():
            form.save()

            if is_htmx_request(request):
                return render_feedback(
                    request,
                    get_feedback(
                        "abikasse-entry-updated",
                        action_url=abikasse_url(),
                        action_label="Zur Abikasse",
                    ),
                )

            return redirect(
                _status_url(next_url or abikasse_url(), "abikasse-entry-updated")
            )
    else:
        if not is_htmx_request(request):
            return redirect("abikasse")
        form = AbikasseEntryForm(instance=entry)

    template = (
        "abikasse/_entry_form.html"
        if is_htmx_request(request)
        else "abikasse/form.html"
    )
    return render(
        request,
        template,
        {
            "form": form,
            "entry": entry,
            "mode": "edit",
            "back_url": back_url,
            "next_url": next_url,
        },
    )


@login_required
@require_POST
def entry_delete(request, entry_id):
    if not can_manage_abikasse(request.user):
        raise PermissionDenied

    entry = get_object_or_404(AbikasseEntry, pk=entry_id)
    entry.delete()

    if is_htmx_request(request):
        return render_feedback(
            request,
            get_feedback(
                "abikasse-entry-deleted",
                action_url=abikasse_url(),
                action_label="Zur Abikasse",
            ),
        )

    return redirect(
        _status_url(
            get_safe_next_url(request) or abikasse_url(),
            "abikasse-entry-deleted",
        )
    )


@login_required
@require_http_methods(["GET", "POST"])
def settings(request):
    if not can_manage_abikasse(request.user):
        raise PermissionDenied

    abikasse_obj = get_abikasse()
    config = get_or_create_abiball_config()
    back_url = get_safe_back_url(request)
    next_url = get_safe_next_url(request)

    if request.method == "POST":
        form = AbiballSettingsForm(request.POST, abikasse=abikasse_obj, config=config)
        if form.is_valid():
            form.save()

            if is_htmx_request(request):
                return render_feedback(
                    request,
                    get_feedback(
                        "abikasse-settings-updated",
                        action_url=abikasse_url(),
                        action_label="Zur Abikasse",
                    ),
                )

            return redirect(
                _status_url(next_url or abikasse_url(), "abikasse-settings-updated")
            )
    else:
        if not is_htmx_request(request):
            return redirect("abikasse")
        form = AbiballSettingsForm(abikasse=abikasse_obj, config=config)

    template = (
        "abikasse/_settings_form.html"
        if is_htmx_request(request)
        else "abikasse/settings.html"
    )
    return render(
        request,
        template,
        {"form": form, "back_url": back_url, "next_url": next_url},
    )


@login_required
@require_GET
@introduction_required
def export(request):
    if not can_manage_abikasse(request.user):
        raise PermissionDenied

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="abikasse-{timezone.localdate():%Y-%m-%d}.csv"'
    )
    response.write("\ufeff")

    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        ["Datum", "Art", "Beschreibung", "Betrag", "Aktion", "Erstellt von"]
    )
    for entry in AbikasseEntry.objects.select_related("event", "created_by"):
        created_by = str(entry.created_by) if entry.created_by else ""
        writer.writerow(
            [
                entry.date.strftime("%d.%m.%Y"),
                AbikasseEntry.Kind(entry.kind).label,
                entry.description,
                f"{entry.amount:.2f}".replace(".", ","),
                entry.event.title if entry.event else "",
                created_by,
            ]
        )

    return response


@login_required
@require_http_methods(["GET", "POST"])
def ticket_count_edit(request):
    profile = request.user.profile
    next_url = get_safe_next_url(request)

    if request.method == "POST":
        form = TicketCountForm(request.POST)
        if form.is_valid():
            profile.ticket_count = form.cleaned_data["ticket_count"]
            profile.save(update_fields=["ticket_count"])

            if is_htmx_request(request):
                return redirect_next_or(request, "abikasse")

            return redirect(
                _status_url(next_url or abikasse_url(), "ticket-count-updated")
            )
    else:
        if not is_htmx_request(request):
            return redirect(next_url or "abikasse")
        form = TicketCountForm(initial={"ticket_count": profile.ticket_count})

    template = (
        "abikasse/_ticket_count_form.html"
        if is_htmx_request(request)
        else "abikasse/ticket_count.html"
    )
    return render(request, template, {"form": form, "next_url": next_url})
