from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template import loader
from django.utils.timezone import now

from .forms import ProjectForm
from .models import Project

User = get_user_model()


def abi(request):
    template = loader.get_template("index.html")
    return HttpResponse(template.render())


def calendar(request):
    template = loader.get_template("calendar.html")
    return HttpResponse(template.render())


@login_required
def projects(request):
    if request.method == "GET":
        projects = Project.objects.filter(starting_date__gte=now()).order_by(
            "starting_date"
        )
        users = User.objects.all()

        forms = [
            (project, ProjectForm(instance=project, prefix=str(project.id)))
            for project in projects
        ]
        return render(
            request,
            "projects.html",
            {"forms": forms, "users": users},
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
