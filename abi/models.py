from django.conf import settings
from django.db import models
from django.db.models import Sum

User = settings.AUTH_USER_MODEL


class Project(models.Model):
    # set to true when approved by staff
    # makes model instance unchangable
    final = models.BooleanField(default=False)  # pyright: ignore[reportArgumentType]

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
        through="ProjectParticipation",
        related_name="participating_projects",
        blank=True,
    )

    earnings = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )
    earnings_received = models.BooleanField(default=False)  # pyright: ignore[reportArgumentType]

    def __str__(self):
        return str(self.title)


class ProjectParticipation(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    participation_time = models.DurationField(null=True, blank=True)

    class Meta:
        unique_together = ("project", "user")

    def save(self, *args, **kwargs):
        if not self.participation_time:
            self.participation_time = (
                self.project.ending_date - self.project.starting_date  # pyright: ignore[reportAttributeAccessIssue]
            )
        super().save(*args, **kwargs)


class Abikasse(models.Model):
    goal = models.PositiveIntegerField()

    def total_earnings(self):
        Project.objects.aggregate(Sum("earnings"))  # pyright: ignore[reportAttributeAccessIssue]

    def save(self, *args, **kwargs):
        # so that there is only one abikasse instance in the database
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "Abikasse"
