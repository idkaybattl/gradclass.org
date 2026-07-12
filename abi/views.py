from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http.response import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from .forms import ProjectForm, SetEarningsForm, SetEarningsReceivedForm
from .models import Abikasse, Project, ProjectParticipation
from .notifications import Notification
from .services import save_project

User = get_user_model()
MAX_PROJECTS_PER_HOUR = 5
MAX_PROJECTS_PER_DAY = 10


def can_edit_project(user, project):
    return not project.final and (project.creator_id == user.id or user.is_staff)


def get_safe_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next")
    if not next_url:
        return None

    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url

    return None


def redirect_next_or(request, fallback, **kwargs):
    next_url = get_safe_next_url(request)
    if next_url:
        return redirect(next_url)

    return redirect(fallback, **kwargs)


def get_project_creation_limit_error(user):
    current_time = timezone.now()
    user_projects = Project.objects.filter(creator=user)

    projects_in_last_hour = user_projects.filter(
        created_at__gte=current_time - timedelta(hours=1)
    ).count()
    if projects_in_last_hour >= MAX_PROJECTS_PER_HOUR and not user.is_staff:
        return (
            f"Du kannst maximal {MAX_PROJECTS_PER_HOUR} Aktionen pro Stunde erstellen."
        )

    projects_in_last_day = user_projects.filter(
        created_at__gte=current_time - timedelta(days=1)
    ).count()
    if projects_in_last_day >= MAX_PROJECTS_PER_DAY and not user.is_staff:
        return f"Du kannst maximal {MAX_PROJECTS_PER_DAY} Aktionen pro Tag erstellen."

    return None


@login_required
@require_GET
def abi(request):
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
            "ranking": ranking,
        },
    )


@login_required
@require_GET
def notifications(request):
    user = request.user
    notifications = Notification.objects.filter(user=user, is_read=False).order_by(
        "-created_at"
    )
    return render(
        request, "components/notifications.html", {"notifications": notifications}
    )


@login_required
@require_POST
def mark_all_notifications_as_read(request):
    user = request.user
    notifications = Notification.objects.filter(user=user, is_read=False)
    notifications.update(is_read=True)
    return JsonResponse({"success": True})


@login_required
@require_POST
def mark_notification_as_read(request, notification_id):
    user = request.user
    notification = Notification.objects.get(id=notification_id, user=user)
    notification.is_read = True
    notification.save()
    return JsonResponse({"success": True})


@login_required
def calendar(request):
    return render(request, "calendar.html")


@login_required
def create_project(request):
    rate_limit_error = get_project_creation_limit_error(request.user)
    if rate_limit_error:
        messages.error(request, rate_limit_error)
        return redirect_next_or(request, "projects")

    if request.method == "GET":
        form = ProjectForm(prefix="new", request_user=request.user)
        return render(
            request,
            "projects/_project_create_popup.html",
            {
                "form": form,
                "next_url": get_safe_next_url(request),
            },
        )

    data = request.POST
    form = ProjectForm(data=data, prefix="new", request_user=request.user)

    if form.is_valid():
        save_project(form, request.user)
        messages.success(request, "Projekt erfolgreich erstellt.")

        return redirect_next_or(request, "projects")
    else:
        messages.error(request, "Form ist invalide.")

    return render(
        request,
        "projects/_project_create_popup.html",
        {"form": form, "next_url": get_safe_next_url(request)},
        status=400,
    )


@login_required
def edit_project(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    if not can_edit_project(request.user, project) or project.final:
        messages.error(request, "Du darfst diese Aktion nicht bearbeiten")
        return redirect_next_or(request, "projects")

    if request.method == "POST":
        form = ProjectForm(
            data=request.POST,
            instance=project,
            prefix=str(project.id),
            request_user=request.user,
        )

        if form.is_valid():
            save_project(form, request.user)

            messages.success(request, "Projekt erfolgreich bearbeitet.")

            return redirect_next_or(request, "projects")
        else:
            messages.error(request, "Form ist invalide.")

        return render(
            request,
            "projects/_project_edit_popup.html",
            {"form": form, "project": project, "next_url": get_safe_next_url(request)},
            status=400,
        )

    else:
        form = ProjectForm(
            instance=project,
            prefix=str(project.id),
            request_user=request.user,
        )
        return render(
            request,
            "projects/_project_edit_popup.html",
            {"form": form, "project": project, "next_url": get_safe_next_url(request)},
        )


@login_required
@require_GET
def projects(request, mode):
    if mode == "upcoming":
        projects = (
            Project.objects.filter(ending_date__gt=timezone.now())
            .distinct()
            .select_related("creator")
            .prefetch_related("participants")
            .order_by("starting_date")
        )

    elif mode == "own":
        projects = (
            Project.objects.filter(
                Q(participants=request.user) | Q(creator=request.user)
            )
            .distinct()
            .select_related("creator")
            .prefetch_related("participants")
            .order_by("starting_date")
        )

    # mode "all"
    else:
        if request.user.is_staff:
            projects = (
                Project.objects.all()
                .distinct()
                .select_related("creator")
                .prefetch_related("participants")
                .order_by("starting_date")
            )
        else:
            projects = (
                Project.objects.filter(
                    Q(participants=request.user)  # pyright: ignore[reportOperatorIssue]
                    | Q(creator=request.user)
                    | Q(ending_date__gt=timezone.now())
                )
                .distinct()
                .select_related("creator")
                .prefetch_related("participants")
                .order_by("starting_date")
            )

    can_view_all_projects = request.user.is_staff

    return render(
        request,
        "projects.html",
        {
            "projects": projects,
            "can_view_all_projects": can_view_all_projects,
        },
    )


@login_required
@require_GET
def project_details(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    can_edit = can_edit_project(request.user, project)
    is_participant = project.participants.filter(pk=request.user.pk).exists()
    can_delete = can_edit
    can_leave = is_participant and not project.final
    can_join = not is_participant and not project.final
    can_approve_payment = request.user.is_staff
    earnings_form = SetEarningsForm(instance=project)
    earnings_received_form = SetEarningsReceivedForm(instance=project)

    return render(
        request,
        "projects/_project_details_popup.html",
        {
            "project": project,
            "can_edit": can_edit,
            "is_participant": is_participant,
            "can_delete": can_delete,
            "can_leave": can_leave,
            "can_join": can_join,
            "can_approve_payment": can_approve_payment,
            "next_url": get_safe_next_url(request),
            "earnings_form": earnings_form,
            "earnings_received_form": earnings_received_form,
        },
    )


@login_required
@require_POST
def join_project(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    if project.final:
        messages.error(request, "Dieses Projekt ist bereits abgeschlossen.")
    elif project.starting_date < timezone.now():
        messages.error(request, "Das Projekt liegt in der Vergangenheit")

    else:
        if project.participants.filter(pk=request.user.pk).exists():
            messages.error(request, "Du nimmst an diesem Projekt bereits teil.")
        else:
            participation = ProjectParticipation.objects.create(  # pyright: ignore[reportAttributeAccessIssue]
                project=project,
                user=request.user,
            )
            participation.save()
            messages.success(request, "Du nimmst jetzt Teil.")

    return redirect_next_or(request, "projects")


@login_required
@require_POST
def leave_project(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    if project.final:
        messages.error(request, "Dieses Projekt ist bereits abgeschlossen.")
    else:
        if not project.participants.filter(pk=request.user.pk).exists():
            messages.error(request, "Du nimmst an diesem Projekt nicht teil.")
        else:
            messages.success(request, "Du hast deine Teilnahme beendet.")
        # remove participant in either case just in case
        project.participants.remove(request.user)

    return redirect_next_or(request, "projects")


@login_required
@require_POST
def delete_project(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    if project.final:
        messages.error(request, "Dieses Projekt ist bereits abgeschlossen.")
    elif not request.user.is_staff and not request.user == project.creator:
        messages.error(request, "Du bist nicht berechtigt das Projekt zu löschen")
    else:
        project.delete()
        messages.success(request, "Projekt erfolgreich gelöscht")

    return redirect_next_or(request, "projects-upcoming")


@login_required
@require_POST
def set_project_earnings(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    if not can_edit_project(request.user, project):
        messages.error(request, "Du bist nicht berechtigt das Projekt zu bearbeiten.")
    else:
        form = SetEarningsForm(
            request.POST, instance=get_object_or_404(Project, id=project_id)
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Einnahmen erfolgreich gesetzt.")

    return redirect_next_or(request, "projects-own")


@login_required
@require_POST
def set_earnings_received(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    if not request.user.is_staff:
        messages.error(request, "Du bist nicht berechtigt das Projekt zu bearbeiten.")

    else:
        form = SetEarningsReceivedForm(
            request.POST, instance=get_object_or_404(Project, id=project_id)
        )
        if form.is_valid():
            project = form.save(commit=False)
            project.final = project.earnings_received
            project.save()
            messages.success(request, "Einnahmen erfolgreich gesetzt.")

    return redirect_next_or(request, "projects")


@login_required
@require_GET
def polls(request):
    return render(request, "polls.html")
