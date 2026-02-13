from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template import loader
from django.utils.timezone import now

from .models import Project

User = get_user_model()


def abi(request):
    template = loader.get_template("index.html")
    return HttpResponse(template.render())


def calendar(request):
    template = loader.get_template("calendar.html")
    return HttpResponse(template.render())


@login_required
def upcoming_projects(request):
    projects = Project.objects.filter(starting_date__gte=now()).order_by(
        "starting_date"
    )
    users = User.objects.all()

    return render(
        request,
        "upcoming.html",
        {
            "projects": projects,
            "users": users,
        },
    )


@login_required
def add_participant(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    if request.method == "POST":
        user_id = request.POST.get("user_id")
        if user_id:
            user = get_object_or_404(User, id=user_id)
            project.participants.add(user)

    return redirect("upcoming-projects")


@login_required
def update_project(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    if request.method == "POST":
        title = request.POST.get("title")
        description = request.POST.get("description")
        starting_date = request.POST.get("starting_date")
        ending_date = request.POST.get("ending_date")
        participants = request.POST.get("add_participant")

        if title and description and starting_date and ending_date:
            project.title = title
            project.description = description
            project.starting_date = starting_date
            project.ending_date = ending_date
            project.participants = participants
            project.save()

    return redirect("upcoming-projects")


@login_required
def join_project(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    if request.method == "POST":
        user_id = request.POST.get("user_id")
        if user_id:
            user = get_object_or_404(User, id=user_id)
            project.participants.add(user)

    return redirect("upcoming-projects")
