from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import ProjectForm
from .models import Project

User = get_user_model()
MAX_PROJECTS_PER_HOUR = 5
MAX_PROJECTS_PER_DAY = 10


def can_edit_project(user, project):
    return project.creator_id == user.id or user.is_staff


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


def abi(request):
    return render(request, "index.html")


def calendar(request):
    return render(request, "calendar.html")


@login_required
def projects(request):
    username_field = User.USERNAME_FIELD
    participants_queryset = User.objects.all().order_by(username_field)
    all_users = list(participants_queryset)
    projects = list(
        Project.objects.filter(starting_date__gte=timezone.now())
        .select_related("creator")
        .prefetch_related("participants")
        .order_by("starting_date")
    )

    participant_project_ids = {
        participant.project_id
        for participant in Project.participants.through.objects.filter(
            user_id=request.user.id,
            project_id__in=[project.id for project in projects],
        )
    }

    def build_project_form(*, instance=None, data=None, prefix=None):
        return ProjectForm(
            data=data,
            instance=instance,
            prefix=prefix,
            users=all_users,
            participants_queryset=participants_queryset,
            request_user=request.user,
        )

    def build_project_forms(overrides=None):
        overrides = overrides or {}
        return [
            (
                project,
                overrides.get(project.id)
                or build_project_form(instance=project, prefix=str(project.id)),
                can_edit_project(request.user, project),
                project.id in participant_project_ids,
            )
            for project in projects
        ]

    if request.method == "POST":
        form_action = request.POST.get("form_action")

        if form_action == "create_project":
            create_form = build_project_form(data=request.POST, prefix="new")
            rate_limit_error = get_project_creation_limit_error(request.user)
            if rate_limit_error:
                create_form.add_error(None, rate_limit_error)

            if create_form.is_valid():
                new_project = create_form.save(commit=False)
                new_project.creator = request.user
                new_project.save()
                create_form.save_m2m()
                return redirect("projects")

            return render(
                request,
                "projects.html",
                {
                    "forms": build_project_forms(),
                    "create_form": create_form,
                    "form_media": create_form.media,
                    "initial_popup_id": "create-project-popup",
                },
            )

        project_id = request.POST.get("project_id")
        if project_id:
            project = get_object_or_404(Project, pk=project_id)
            if not can_edit_project(request.user, project):
                return HttpResponseForbidden("Du darfst diese Aktion nicht bearbeiten.")

            edit_form = build_project_form(
                data=request.POST,
                instance=project,
                prefix=str(project.id),
            )

            if edit_form.is_valid():
                edit_form.save()
                return redirect("projects")

            return render(
                request,
                "projects.html",
                {
                    "forms": build_project_forms(overrides={project.id: edit_form}),
                    "create_form": build_project_form(prefix="new"),
                    "form_media": edit_form.media,
                    "initial_popup_id": f"edit-{project.id}",
                },
            )

        return redirect("projects")

    create_form = build_project_form(prefix="new")
    project_forms = build_project_forms()

    return render(
        request,
        "projects.html",
        {
            "forms": project_forms,
            "create_form": create_form,
            "form_media": create_form.media,
        },
    )


@login_required
@require_POST
def join_project(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    if request.method == "POST":
        project.participants.add(request.user)

    return redirect("projects")


@login_required
@require_POST
def leave_project(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    if request.method == "POST":
        project.participants.remove(request.user)

    return redirect("projects")
