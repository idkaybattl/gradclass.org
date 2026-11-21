from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Sum

from .events import Event

User = settings.AUTH_USER_MODEL


class Abikasse(models.Model):
    goal = models.DecimalField(max_digits=10, decimal_places=2)

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

    class Meta:
        # `view_abikasse` is Django's built-in view permission; declaring it here
        # would clash with the auto-created codename.
        permissions = [
            ("manage_abikasse", "Abikasse verwalten"),
        ]


class AbikasseEntry(models.Model):
    class Kind(models.TextChoices):
        INCOME = "income", "Einnahme"
        EXPENSE = "expense", "Ausgabe"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manuell"
        EVENT = "event", "Aktion"

    kind = models.CharField(max_length=20, choices=Kind)
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    description = models.CharField(max_length=255)
    date = models.DateField()
    event = models.OneToOneField(
        Event,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="abikasse_entry",
    )
    source = models.CharField(max_length=20, choices=Source, default=Source.MANUAL)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="abikasse_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return str(self.description)


class AbiballConfig(models.Model):
    fixed_costs = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    per_head_costs = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    point_value = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("2.00"),
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    default_ticket_count = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
    )

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "Abiball-Konfiguration"
