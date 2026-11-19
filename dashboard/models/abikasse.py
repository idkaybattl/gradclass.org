from django.db import models
from django.db.models import Sum

from .events import Event


class Abikasse(models.Model):
    goal = models.PositiveIntegerField()

    def total_earnings(self):
        return (
            Event.objects.filter(final=True)  # pyright: ignore[reportAttributeAccessIssue]
            .aggregate(Sum("earnings"))
            .get("earnings__sum", 0)
        ) or 0

    def save(self, *args, **kwargs):
        # so that there is only one abikasse instance in the database
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "Abikasse"
