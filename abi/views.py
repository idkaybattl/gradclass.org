from django.http import HttpResponse
from django.template import loader

from django.shortcuts import render, get_object_or_404, redirect
from django.utils.timezone import now
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from .models import Project

User = get_user_model()


def abi(request):
    template = loader.get_template('index.html')
    return HttpResponse(template.render())

def calendar(request):
    template = loader.get_template('calendar.html')
    return HttpResponse(template.render())


@login_required
def upcoming_projects(request):
    projects = Project.objects.filter(starting_date__gte=now()).order_by("starting_date")
    users = User.objects.all()

    return render(request, "upcoming.html", {
        "projects": projects,
        "users": users,
    })


@login_required
def add_participant(request, project_id):
    project = get_object_or_404(Project, id=project_id)

    if request.method == "POST":
        user_id = request.POST.get("user_id")
        if user_id:
            user = get_object_or_404(User, id=user_id)
            project.participants.add(user)

    return redirect("upcoming-projects")
