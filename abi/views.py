from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now

from .forms import ProjectForm
from .models import Project

User = get_user_model()


def abi(request):
    return render(request, "index.html")


def calendar(request):
    return render(request, "calendar.html")


@login_required
def projects(request):
    if request.method == "GET":
        projects = Project.objects.filter(starting_date__gte=now()).order_by(
            "starting_date"
        )
        username_field = User.USERNAME_FIELD
        participants_queryset = User.objects.all().order_by(username_field)
        all_users = list(participants_queryset)

        forms = [
            (
                project,
                ProjectForm(
                    instance=project,
                    prefix=str(project.id),
                    users=all_users,
                    participants_queryset=participants_queryset,
                ),
            )
            for project in projects
        ]

        if forms:
            form_media = forms[0][1].media
        else:
            form_media = ProjectForm(
                users=[],
                participants_queryset=User.objects.none(),
            ).media

        return render(
            request,
            "projects.html",
            {
                "forms": forms,
                "form_media": form_media,
            },
        )

    if request.method == "POST":
        id = request.POST.get("project_id")
        project = Project.objects.get(pk=id)

        form = ProjectForm(request.POST, instance=project, prefix=str(project.id))

        if form.is_valid():
            form.save()

        return redirect("/projects")


@login_required
def join_project(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    if request.method == "POST":
        user_id = request.POST.get("user_id")
        if user_id:
            user = get_object_or_404(User, id=user_id)
            project.participants.add(user)

    return redirect("/projects")
