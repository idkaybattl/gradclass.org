from datetime import timedelta
from operator import not_

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http.response import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from .forms import ProjectForm
from .models import Abikasse, Notification, Project

User = get_user_model()
MAX_PROJECTS_PER_HOUR = 5
MAX_PROJECTS_PER_DAY = 10


def can_edit_project(user, project):
    return project.creator_id == user.id or user.is_staff


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
def abi(request):
    abikasse, _ = Abikasse.objects.get_or_create(
        pk=1,
        defaults={
            "current": 0,
            "goal": 30000,
        },
    )
    return render(
        request,
        "index.html",
        {"abikasse_current": abikasse.current, "abikasse_goal": abikasse.goal},
    )


@login_required
@require_GET
def notifications(request):
    user = request.user
    notifications = Notification.objects.filter(user=user, is_read=False).order_by(
        "-created_at"
    )
    return render(request, "notifications.html", {"notifications": notifications})


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
        new_project = form.save(commit=False)
        new_project.creator = request.user
        new_project.save()
        form.save_m2m()
        messages.success(request, "Projekt erfolgreich erstellt.")

        return redirect_next_or(request, "projects")

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
            form.save()
            messages.success(request, "Projekt erfolgreich bearbeitet.")

            return redirect_next_or(request, "projects")

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
def projects(request, mode):
    now = timezone.now()

    if mode == "upcoming":
        projects = (
            Project.objects.filter(ending_date__gt=timezone.now())
            .select_related("creator")
            .prefetch_related("participants")
            .order_by("starting_date")
        )

    elif mode == "own":
        projects = (
            Project.objects.filter(
                Q(participants=request.user) | Q(creator=request.user)
            )
            .select_related("creator")
            .prefetch_related("participants")
            .order_by("starting_date")
        )

    # mode "all"
    else:
        if request.user.is_staff:
            projects = (
                Project.objects.all()
                .select_related("creator")
                .prefetch_related("participants")
                .order_by("starting_date")
            )
        else:
            projects = (
                Project.objects.filter(
                    Q(participants=request.user)
                    | Q(creator=request.user)
                    | Q(ending_date__gt=timezone.now())
                )
                .distinct()
                .select_related("creator")
                .prefetch_related("participants")
                .order_by("starting_date")
            )

    # The actual form is loaded into the dialog; this only renders widget assets.
    form_media = ProjectForm(participants_queryset=User.objects.none()).media
    return render(
        request,
        "projects.html",
        {"projects": projects, "form_media": form_media},
    )


@login_required
def project_details(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    can_edit = not project.final and (
        request.user.is_staff or project.creator == request.user
    )
    is_participant = project.participants.filter(pk=request.user.pk).exists()
    can_delete = can_edit

    return render(
        request,
        "projects/_project_details_popup.html",
        {
            "project": project,
            "can_edit": can_edit,
            "is_participant": is_participant,
            "can_delete": can_delete,
            "next_url": get_safe_next_url(request),
        },
    )


@login_required
@require_POST
def join_project(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    if project.starting_date < timezone.now():
        messages.error(request, "Das Projekt liegt in der Vergangenheit")
    else:
        if project.participants.filter(pk=request.user.pk).exists():
            messages.error(request, "Du nimmst an diesem Projekt bereits teil.")
        else:
            project.participants.add(request.user)
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

    return redirect_next_or(request, "projects")
