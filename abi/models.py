from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class Project(models.Model):
    # set to true when approved by staff
    # makes model instance unchangable
    final = models.BooleanField(default=False)

    title = models.CharField(max_length=255)
    description = models.TextField()
    starting_date = models.DateTimeField()
    ending_date = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    creator = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="created_projects"
    )

    participants = models.ManyToManyField(
        User,
        related_name="participating_projects",
        blank=True,
    )

    def __str__(self):
        return str(self.title)


class Notification(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )
    is_read = models.BooleanField(default=False)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.message)


class Abikasse(models.Model):
    goal = models.PositiveIntegerField()
    current = models.IntegerField()

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "Abikasse"
