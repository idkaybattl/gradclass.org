from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import (
    require_GET,
    require_http_methods,
    require_POST,
)

from ..feedback import get_feedback, render_feedback
from ..forms import QuoteForm, QuoteLineFormSet, QuoteReportForm
from ..http_helpers import (
    get_safe_back_url,
    get_safe_next_url,
    is_htmx_request,
)
from ..intro import introduction_required
from ..models import Quote, QuoteReport
from ..notifications import notify_quote_reported
from ..permissions import (
    can_delete_quote,
    can_manage_quotes,
    can_report_quote,
)
from ..services import save_quote


def quotes_url(status=None):
    url = reverse("quotes")
    if status:
        url = f"{url}?{urlencode({'status': status})}"
    return url


@login_required
@require_GET
@introduction_required
def quotes(request):
    quote_list = list(
        Quote.objects.select_related("uploader").prefetch_related(
            "lines", "reports__reporter"
        )
    )

    for quote in quote_list:
        quote.can_delete = can_delete_quote(request.user, quote)
        quote.can_report = can_report_quote(request.user, quote) and not any(
            report.reporter_id == request.user.pk for report in quote.reports.all()
        )

    may_manage = can_manage_quotes(request.user)
    reports = None
    if may_manage:
        reports = list(QuoteReport.objects.select_related("quote", "reporter"))

    return render(
        request,
        "quotes.html",
        {
            "quotes": quote_list,
            "reports": reports,
            "can_manage_quotes": may_manage,
            "feedback": get_feedback(request.GET.get("status")),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def quote_create(request):
    back_url = get_safe_back_url(request)
    next_url = get_safe_next_url(request)

    if request.method == "GET":
        if not is_htmx_request(request):
            return redirect("quotes")
        form = QuoteForm()
        formset = QuoteLineFormSet()
    else:
        form = QuoteForm(request.POST)
        formset = QuoteLineFormSet(request.POST)

        if form.is_valid() and formset.is_valid():
            save_quote(form, formset, request.user)

            if is_htmx_request(request):
                return render_feedback(
                    request,
                    get_feedback(
                        "quote-created",
                        actions=[
                            {"label": "Zur Liste", "url": reverse("quotes")},
                            {
                                "label": "Weiteres Zitat",
                                "url": reverse("quote-create"),
                                "htmx": True,
                            },
                        ],
                    ),
                )

            return redirect(f"{reverse('quotes')}?status=quote-created")

    template = (
        "quotes/_quote_form.html" if is_htmx_request(request) else "quotes/form.html"
    )
    return render(
        request,
        template,
        {
            "form": form,
            "formset": formset,
            "back_url": back_url,
            "next_url": next_url,
        },
    )


@login_required
@require_POST
def quote_delete(request, quote_id):
    quote = get_object_or_404(Quote, pk=quote_id)
    if not can_delete_quote(request.user, quote):
        feedback = get_feedback(
            "quote-delete-denied",
            action_url=reverse("quotes"),
            action_label="Zur Liste",
        )
        if is_htmx_request(request):
            return render_feedback(request, feedback)
        return redirect(quotes_url("quote-delete-denied"))

    quote.delete()

    if is_htmx_request(request):
        return render_feedback(
            request,
            get_feedback(
                "quote-deleted",
                action_url=reverse("quotes"),
                action_label="Zur Liste",
            ),
        )

    return redirect(quotes_url("quote-deleted"))


@login_required
@require_http_methods(["GET", "POST"])
def quote_report(request, quote_id):
    quote = get_object_or_404(Quote.objects.select_related("uploader"), pk=quote_id)
    back_url = get_safe_back_url(request)

    if not can_report_quote(request.user, quote):
        feedback = get_feedback(
            "quote-report-denied",
            action_url=reverse("quotes"),
            action_label="Zur Liste",
        )
        if is_htmx_request(request):
            return render_feedback(request, feedback)
        return redirect(quotes_url("quote-report-denied"))

    if request.method == "GET":
        if not is_htmx_request(request):
            return redirect("quotes")
        form = QuoteReportForm()
    else:
        if QuoteReport.objects.filter(quote=quote, reporter=request.user).exists():
            feedback = get_feedback(
                "quote-already-reported",
                action_url=reverse("quotes"),
                action_label="Zur Liste",
            )
            if is_htmx_request(request):
                return render_feedback(request, feedback)
            return redirect(quotes_url("quote-already-reported"))

        form = QuoteReportForm(request.POST)
        if form.is_valid():
            report = QuoteReport.objects.create(
                quote=quote,
                reporter=request.user,
                reason=form.cleaned_data["reason"],
            )
            notify_quote_reported(report)

            if is_htmx_request(request):
                return render_feedback(
                    request,
                    get_feedback(
                        "quote-reported",
                        action_url=reverse("quotes"),
                        action_label="Zur Liste",
                    ),
                )

            return redirect(quotes_url("quote-reported"))

    template = (
        "quotes/_report_form.html" if is_htmx_request(request) else "quotes/report.html"
    )
    return render(
        request,
        template,
        {
            "form": form,
            "quote": quote,
            "back_url": back_url,
            "next_url": get_safe_next_url(request),
        },
    )


@login_required
@require_POST
def quote_report_dismiss(request, report_id):
    if not can_manage_quotes(request.user):
        return redirect(quotes_url("report-dismiss-denied"))

    report = get_object_or_404(QuoteReport, pk=report_id)
    report.delete()
    return redirect(quotes_url("report-dismissed"))
