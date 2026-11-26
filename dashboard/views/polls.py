import csv
import random
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from ..feedback import get_feedback, render_feedback
from ..forms import PollForm, StartVotingForm, SuggestionDeadlineForm
from ..http_helpers import (
    get_safe_back_url,
    get_safe_next_url,
    is_htmx_request,
    render_page_or_partial,
)
from ..intro import introduction_required
from ..models import OPTION_LABEL_MAX_LENGTH, BallotVote, Option, Poll
from ..permissions import can_create_poll, can_manage_poll, can_view_poll_results
from ..services import (
    BALLOT_SALT,
    add_poll_suggestion,
    ballot_cookie_name,
    cast_poll_vote,
    close_poll_suggestions,
    close_poll_voting,
    read_poll_vote,
    save_poll,
    set_poll_suggestion_deadline,
    start_poll_suggestions,
    start_poll_voting,
)


def poll_detail_url(poll, status=None):
    url = reverse("poll-details", kwargs={"poll_id": poll.pk})
    if status:
        url = f"{url}?{urlencode({'status': status})}"
    return url


def get_poll_question(poll):
    question = poll.questions.first()
    if question is None:
        raise Http404
    return question


def read_ballot_token(request, question):
    return request.get_signed_cookie(
        ballot_cookie_name(question), default=None, salt=BALLOT_SALT
    )


def _results_context(poll, user):
    question = get_poll_question(poll)
    total_votes = question.participations.count()
    can_view_results = can_view_poll_results(user, poll)
    results = []
    is_tie = False

    if can_view_results:
        approved = list(
            question.options.filter(state=Option.State.APPROVED).annotate(
                vote_count=Count("votes")
            )
        )
        top_votes = max((option.vote_count for option in approved), default=0)
        results = [
            {
                "option": option,
                "votes": option.vote_count,
                "percent": round(option.vote_count * 100 / total_votes)
                if total_votes
                else 0,
            }
            for option in approved
        ]
        is_tie = top_votes > 0 and (
            sum(1 for option in approved if option.vote_count == top_votes) > 1
        )

    return {
        "can_view_results": can_view_results,
        "results": results,
        "total_votes": total_votes,
        "is_tie": is_tie,
    }


def poll_details_context(
    request,
    poll,
    *,
    status=None,
    message="",
    suggestion_error="",
    suggestion_value="",
    show_voting_deadline_form=False,
    voting_deadline_form=None,
    suggestion_deadline_form=None,
    back_url=None,
):
    user = request.user
    phase = poll.phase
    question = get_poll_question(poll)
    is_manager = can_manage_poll(user, poll)
    can_moderate = is_manager and phase in {
        Poll.Phase.SUGGESTIONS,
        Poll.Phase.MODERATION,
    }

    options = []
    moderation_options = []
    if phase in {Poll.Phase.SUGGESTIONS, Poll.Phase.MODERATION}:
        if is_manager or poll.suggestions_public:
            options_queryset = question.options.filter(
                state__in=[Option.State.SUGGESTED, Option.State.APPROVED]
            )
            if is_manager:
                options_queryset = options_queryset.select_related("created_by")
            options = list(options_queryset)
            random.shuffle(options)
        if can_moderate:
            moderation_options = list(
                question.options.select_related(
                    "created_by", "merged_into"
                ).prefetch_related("merged_options__created_by")
            )
            random.shuffle(moderation_options)
    else:
        options = list(question.options.filter(state=Option.State.APPROVED))

    merge_targets = [
        option
        for option in moderation_options
        if option.state in {Option.State.SUGGESTED, Option.State.APPROVED}
    ]

    token = read_ballot_token(request, question)
    current_option_id = read_poll_vote(question, user, token)
    has_voted = question.participations.filter(user=user).exists()

    can_edit = is_manager and phase == Poll.Phase.DRAFT
    detail_url = poll_detail_url(poll)
    edit_url = f"{reverse('poll-edit', kwargs={'poll_id': poll.pk})}?{urlencode({'back': detail_url})}"
    moderation_url = reverse("poll-moderate", kwargs={"poll_id": poll.pk})

    action_label = ""
    action_url = ""
    if can_edit:
        action_label, action_url = "Bearbeiten", edit_url
    elif can_moderate:
        action_label, action_url = "Moderieren", moderation_url

    results_context = _results_context(poll, user)

    if (
        suggestion_deadline_form is None
        and phase == Poll.Phase.SUGGESTIONS
        and is_manager
    ):
        suggestion_deadline_form = SuggestionDeadlineForm(
            initial={"suggestion_deadline": poll.suggestion_deadline}
        )

    return {
        "poll": poll,
        "phase": phase,
        "title": poll.title,
        "options": options,
        "is_manager": is_manager,
        "can_moderate": can_moderate,
        "can_suggest": phase == Poll.Phase.SUGGESTIONS,
        "can_edit": can_edit,
        "can_start_suggestions": can_edit and poll.mode == Poll.Mode.SUGGESTIONS,
        "can_start_voting": is_manager
        and (
            (phase == Poll.Phase.DRAFT and poll.mode == Poll.Mode.FIXED)
            or (phase == Poll.Phase.MODERATION and poll.mode == Poll.Mode.SUGGESTIONS)
        ),
        "can_close_suggestions": is_manager and phase == Poll.Phase.SUGGESTIONS,
        "can_close_voting": is_manager and phase == Poll.Phase.VOTING,
        "can_vote": phase == Poll.Phase.VOTING,
        "has_voted": has_voted,
        "current_option_id": current_option_id,
        "can_view_results": results_context["can_view_results"],
        "results": results_context["results"],
        "total_votes": results_context["total_votes"],
        "is_tie": results_context["is_tie"],
        "suggestion_error": suggestion_error,
        "suggestion_value": suggestion_value,
        "show_voting_deadline_form": show_voting_deadline_form,
        "voting_deadline_form": voting_deadline_form or StartVotingForm(),
        "suggestion_deadline_form": suggestion_deadline_form,
        "next_url": get_safe_next_url(request),
        "back_url": back_url,
        "detail_url": detail_url,
        "edit_url": edit_url,
        "moderation_options": moderation_options,
        "merge_targets": merge_targets,
        "action_label": action_label,
        "action_url": action_url,
        "action_overlay": bool(action_url),
        "feedback": get_feedback(status, message=message),
    }


def render_poll_details(request, poll, **overrides):
    context = poll_details_context(request, poll, **overrides)
    return render_page_or_partial(
        request,
        "polls/detail.html",
        "polls/_poll_details.html",
        context,
    )


def render_moderation_panel(request, poll, **overrides):
    context = poll_details_context(request, poll, **overrides)
    context["title"] = "Moderation"
    context["back_url"] = context["detail_url"]
    context["action_label"] = ""
    context["action_url"] = ""
    return render(request, "polls/_moderation_panel.html", context)


def poll_action_response(request, poll, status, message=""):
    if is_htmx_request(request):
        return render_poll_details(request, poll, status=status, message=message)

    return redirect(poll_detail_url(poll, status))


def moderation_action_response(request, poll, status, message=""):
    if is_htmx_request(request):
        return render_moderation_panel(request, poll, status=status, message=message)

    return redirect(poll_detail_url(poll, status))


@login_required
@require_GET
@introduction_required
def polls(request):
    user = request.user
    active_filter = request.GET.get("filter") or "open"
    if active_filter not in {"open", "closed", "drafts", "all"}:
        active_filter = "open"

    poll_list = list(Poll.objects.select_related("creator").order_by("-created_at"))
    phases = {poll.pk: poll.phase for poll in poll_list}

    is_manager = can_create_poll(user)
    show_drafts = is_manager or any(
        phases[poll.pk] == Poll.Phase.DRAFT and poll.creator.pk == user.pk
        for poll in poll_list
    )
    if active_filter == "drafts" and not show_drafts:
        active_filter = "open"

    # All visible polls are rendered; the switcher filters on the client.
    visible = [
        poll
        for poll in poll_list
        if phases[poll.pk] != Poll.Phase.DRAFT
        or is_manager
        or poll.creator.pk == user.pk
    ]

    vote_counts = (
        BallotVote.objects.filter(option__question__poll__in=visible)
        .values("option__question__poll_id")
        .annotate(total=Count("id"))
    )
    turnout = {row["option__question__poll_id"]: row["total"] for row in vote_counts}

    return render(
        request,
        "polls.html",
        {
            "poll_items": [
                {
                    "poll": poll,
                    "phase": phases[poll.pk],
                    "turnout": turnout.get(poll.pk, 0),
                }
                for poll in visible
            ],
            "active_filter": active_filter,
            "filter_open": active_filter == "open",
            "filter_all": active_filter == "all",
            "filter_closed": active_filter == "closed",
            "filter_drafts": active_filter == "drafts",
            "show_drafts": show_drafts,
            "can_create_poll": is_manager,
            "feedback": get_feedback(request.GET.get("status")),
        },
    )


@login_required
@require_GET
def poll_details(request, poll_id):
    poll = get_object_or_404(Poll.objects.select_related("creator"), pk=poll_id)
    if poll.phase == Poll.Phase.DRAFT and not can_manage_poll(request.user, poll):
        raise Http404

    return render_poll_details(
        request,
        poll,
        back_url=get_safe_back_url(request),
        status=request.GET.get("status"),
    )


def _suggestion_mode(form):
    if form.is_bound:
        return form.data.get("mode") == Poll.Mode.SUGGESTIONS
    return bool(form.instance.pk) and form.instance.mode == Poll.Mode.SUGGESTIONS


@login_required
@require_http_methods(["GET", "POST"])
def poll_create(request):
    if not can_create_poll(request.user):
        feedback = get_feedback(
            "poll-create-denied",
            action_url=reverse("polls"),
            action_label="Zur Liste",
        )
        if is_htmx_request(request):
            return render_feedback(request, feedback)

        return redirect(
            f"{reverse('polls')}?{urlencode({'status': 'poll-create-denied'})}"
        )

    if request.method == "GET":
        if not is_htmx_request(request):
            return redirect("polls")
        form = PollForm()
    else:
        form = PollForm(data=request.POST)
        if form.is_valid():
            poll = save_poll(form, request.user)

            if is_htmx_request(request):
                return render_feedback(
                    request,
                    get_feedback(
                        "poll-created",
                        actions=[
                            {
                                "label": "Zur Umfrage",
                                "url": poll_detail_url(poll),
                                "htmx": True,
                            },
                            {
                                "label": "Zur Liste",
                                "url": reverse("polls"),
                            },
                        ],
                    ),
                )

            return redirect(poll_detail_url(poll, "poll-created"))

    template = (
        "polls/_poll_form.html" if is_htmx_request(request) else "polls/form.html"
    )
    return render(
        request,
        template,
        {
            "form": form,
            "mode": "create",
            "suggestion_mode": _suggestion_mode(form),
            "next_url": get_safe_next_url(request),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def poll_edit(request, poll_id):
    poll = get_object_or_404(Poll.objects.select_related("creator"), pk=poll_id)
    if not can_manage_poll(request.user, poll):
        return poll_action_response(request, poll, "poll-edit-denied")
    if poll.phase != Poll.Phase.DRAFT:
        return poll_action_response(request, poll, "poll-not-draft")

    back_url = get_safe_back_url(request) or poll_detail_url(poll)

    if request.method == "POST":
        form = PollForm(data=request.POST, instance=poll)
        if form.is_valid():
            save_poll(form, request.user)

            if is_htmx_request(request):
                return render_feedback(
                    request,
                    get_feedback(
                        "poll-updated",
                        action_url=poll_detail_url(poll),
                        action_label="Zur Umfrage",
                        action_htmx=True,
                    ),
                )

            return redirect(poll_detail_url(poll, "poll-updated"))
    else:
        if not is_htmx_request(request):
            return redirect(poll_detail_url(poll))

        question = get_poll_question(poll)
        form = PollForm(
            instance=poll,
            initial={
                "options": "\n".join(
                    question.options.filter(state=Option.State.APPROVED).values_list(
                        "label", flat=True
                    )
                )
            },
        )

    template = (
        "polls/_poll_form.html" if is_htmx_request(request) else "polls/form.html"
    )
    return render(
        request,
        template,
        {
            "form": form,
            "poll": poll,
            "mode": "edit",
            "suggestion_mode": _suggestion_mode(form),
            "back_url": back_url,
            "next_url": get_safe_next_url(request),
        },
    )


def _phase_action(request, poll, action, success_status):
    if not can_manage_poll(request.user, poll):
        return poll_action_response(request, poll, "moderation-denied")

    try:
        action(poll)
    except ValidationError as error:
        return poll_action_response(
            request, poll, "poll-phase-denied", str(error.messages[0])
        )

    return poll_action_response(request, poll, success_status)


@login_required
@require_POST
def poll_start_suggestions(request, poll_id):
    poll = get_object_or_404(Poll, pk=poll_id)
    return _phase_action(request, poll, start_poll_suggestions, "suggestions-started")


@login_required
@require_POST
def poll_start_voting(request, poll_id):
    poll = get_object_or_404(Poll, pk=poll_id)
    if not can_manage_poll(request.user, poll):
        return poll_action_response(request, poll, "moderation-denied")

    startable = (poll.mode == Poll.Mode.FIXED and poll.phase == Poll.Phase.DRAFT) or (
        poll.mode == Poll.Mode.SUGGESTIONS and poll.phase == Poll.Phase.MODERATION
    )
    if not startable:
        return poll_action_response(request, poll, "poll-phase-denied")

    needs_deadline = (
        poll.voting_deadline is None or poll.voting_deadline <= timezone.now()
    )
    submitted = "voting_deadline" in request.POST

    if submitted or needs_deadline:
        form = StartVotingForm(request.POST if submitted else None)
        if submitted and form.is_valid():
            poll.voting_deadline = form.cleaned_data["voting_deadline"]
            poll.save(update_fields=["voting_deadline"])
        else:
            return render_poll_details(
                request,
                poll,
                show_voting_deadline_form=True,
                voting_deadline_form=form,
            )

    return _phase_action(request, poll, start_poll_voting, "voting-started")


@login_required
@require_POST
def poll_close_suggestions(request, poll_id):
    poll = get_object_or_404(Poll, pk=poll_id)
    return _phase_action(request, poll, close_poll_suggestions, "suggestions-closed")


@login_required
@require_POST
def poll_set_suggestion_deadline(request, poll_id):
    poll = get_object_or_404(Poll, pk=poll_id)
    if not can_manage_poll(request.user, poll):
        return poll_action_response(request, poll, "moderation-denied")

    form = SuggestionDeadlineForm(request.POST)
    if form.is_valid():
        try:
            set_poll_suggestion_deadline(poll, form.cleaned_data["suggestion_deadline"])
        except ValidationError as error:
            form.add_error("suggestion_deadline", error)
        else:
            return poll_action_response(request, poll, "suggestion-deadline-updated")

    if is_htmx_request(request):
        return render_moderation_panel(request, poll, suggestion_deadline_form=form)

    return render_poll_details(request, poll, suggestion_deadline_form=form)


@login_required
@require_POST
def poll_close_voting(request, poll_id):
    poll = get_object_or_404(Poll, pk=poll_id)
    return _phase_action(request, poll, close_poll_voting, "voting-closed")


def _suggestion_label_error(label):
    if not label:
        return "Bitte einen Vorschlag eingeben."
    if len(label) > OPTION_LABEL_MAX_LENGTH:
        return f"Ein Vorschlag darf höchstens {OPTION_LABEL_MAX_LENGTH} Zeichen haben."
    return ""


@login_required
@require_POST
def poll_suggest(request, poll_id):
    poll = get_object_or_404(Poll.objects.select_related("creator"), pk=poll_id)
    if poll.phase != Poll.Phase.SUGGESTIONS:
        return poll_action_response(request, poll, "suggestions-ended")

    question = get_poll_question(poll)
    action = request.POST.get("action")
    label = request.POST.get("label", "").strip()

    option = None
    if action in {"edit", "withdraw"}:
        option = get_object_or_404(
            Option,
            pk=request.POST.get("option"),
            question=question,
            created_by=request.user,
        )

    if action in {"add", "edit"}:
        error = _suggestion_label_error(label)
        if error:
            return render_poll_details(
                request,
                poll,
                suggestion_error=error,
                suggestion_value=label,
            )

    try:
        if action == "add":
            add_poll_suggestion(question, request.user, label)
            status = "suggestion-added"
        elif action == "edit" and option is not None:
            option.label = label
            option.save(update_fields=["label"])
            status = "suggestion-updated"
        elif action == "withdraw" and option is not None:
            option.delete()
            status = "suggestion-withdrawn"
        else:
            return poll_action_response(request, poll, "poll-phase-denied")
    except ValidationError as error:
        return render_poll_details(
            request, poll, suggestion_error=str(error.messages[0])
        )

    return poll_action_response(request, poll, status)


@login_required
@require_http_methods(["GET", "POST"])
def poll_moderate(request, poll_id):
    poll = get_object_or_404(Poll.objects.select_related("creator"), pk=poll_id)
    if not can_manage_poll(request.user, poll):
        return poll_action_response(request, poll, "moderation-denied")
    if poll.phase not in {Poll.Phase.SUGGESTIONS, Poll.Phase.MODERATION}:
        return poll_action_response(request, poll, "poll-phase-denied")

    if request.method == "GET":
        if not is_htmx_request(request):
            return redirect(poll_detail_url(poll))
        return render_moderation_panel(request, poll)

    question = get_poll_question(poll)
    action = request.POST.get("action")
    option = get_object_or_404(Option, pk=request.POST.get("option"), question=question)

    if action == "approve":
        option.state = Option.State.APPROVED
        option.save(update_fields=["state"])
        status = "suggestion-approved"
    elif action == "reject":
        option.state = Option.State.REJECTED
        option.save(update_fields=["state"])
        status = "suggestion-rejected"
    elif action == "edit":
        label = request.POST.get("label", "").strip()
        error = _suggestion_label_error(label)
        if error:
            if is_htmx_request(request):
                return render_moderation_panel(
                    request, poll, suggestion_error=error, suggestion_value=label
                )
            return render_poll_details(
                request,
                poll,
                suggestion_error=error,
                suggestion_value=label,
            )
        option.label = label
        option.save(update_fields=["label"])
        status = "suggestion-updated"
    elif action == "merge":
        merged_into = request.POST.get("merged_into")
        if not merged_into:
            return poll_action_response(request, poll, "poll-phase-denied")
        target = get_object_or_404(Option, pk=merged_into, question=question)
        if target.pk == option.pk or target.state not in {
            Option.State.SUGGESTED,
            Option.State.APPROVED,
        }:
            return poll_action_response(request, poll, "poll-phase-denied")
        option.state = Option.State.MERGED
        option.merged_into = target
        option.save(update_fields=["state", "merged_into"])
        status = "suggestion-merged"
    else:
        return poll_action_response(request, poll, "poll-phase-denied")

    return moderation_action_response(request, poll, status)


@login_required
@require_POST
def poll_vote(request, poll_id):
    poll = get_object_or_404(Poll.objects.select_related("creator"), pk=poll_id)
    if poll.phase != Poll.Phase.VOTING:
        return poll_action_response(request, poll, "vote-closed")

    question = get_poll_question(poll)
    option = question.options.filter(
        pk=request.POST.get("option"), state=Option.State.APPROVED
    ).first()
    if option is None:
        return poll_action_response(request, poll, "vote-invalid")

    token = read_ballot_token(request, question)
    status, new_token = cast_poll_vote(question, option, request.user, token)
    response = poll_action_response(request, poll, status)

    if new_token:
        max_age = max(int((poll.voting_deadline - timezone.now()).total_seconds()), 0)
        response.set_signed_cookie(
            ballot_cookie_name(question),
            new_token,
            salt=BALLOT_SALT,
            max_age=max_age,
            httponly=True,
            samesite="Lax",
            secure=request.is_secure(),
            path="/",
        )
    return response


@login_required
@require_GET
def poll_export(request, poll_id):
    poll = get_object_or_404(Poll.objects.select_related("creator"), pk=poll_id)
    if not can_manage_poll(request.user, poll):
        raise PermissionDenied

    question = get_poll_question(poll)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="vorschlaege-{poll.pk}-{timezone.localdate():%Y-%m-%d}.csv"'
    )
    response.write("\ufeff")

    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Vorschlag", "Autor:in", "Status", "Zusammengeführt in"])
    options = question.options.select_related("created_by", "merged_into")
    for option in options:
        author = option.created_by
        writer.writerow(
            [
                option.label,
                (author.get_full_name() or author.username) if author else "",
                Option.State(option.state).label,
                option.merged_into.label if option.merged_into else "",
            ]
        )

    return response


@login_required
@require_GET
def poll_results(request, poll_id):
    poll = get_object_or_404(Poll.objects.select_related("creator"), pk=poll_id)
    if not can_view_poll_results(request.user, poll):
        raise PermissionDenied

    return render(
        request,
        "polls/_results.html",
        {"poll": poll, "phase": poll.phase, **_results_context(poll, request.user)},
    )
