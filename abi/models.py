from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class Project(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    starting_date = models.DateTimeField()
    ending_date = models.DateTimeField()
    creator = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="created_projects"
    )
    participants = models.ManyToManyField(
        User,
        related_name="participating_projects",
        blank=True,
    )
