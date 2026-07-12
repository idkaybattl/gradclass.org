from .models import ProjectParticipation
from .notifications import notify_participants


def update_participants(project, selected_users):
    # Remove old participants
    ProjectParticipation.objects.filter(project=project).exclude(  # pyright: ignore[reportAttributeAccessIssue]
        user__in=selected_users
    ).delete()

    # Add new participants
    existing = set(project.participants.values_list("id", flat=True))
    for user in selected_users:
        if user.id not in existing:
            ProjectParticipation.objects.create(  # pyright: ignore[reportAttributeAccessIssue]
                project=project,
                user=user,
            )


def save_project(form, user):
    if form.instance.pk:
        old = set(form.cleaned_data["participants"])
    else:
        old = set()

    project = form.save(commit=False)
    project.creator = user
    project.save()

    update_participants(project, form.cleaned_data["participants"])

    new = set(project.participants.all())

    notify_participants(project, old, new)

    return project
