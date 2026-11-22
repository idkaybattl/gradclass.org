from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from phonenumber_field.modelfields import PhoneNumberField

User = settings.AUTH_USER_MODEL

STUDENT_GROUP_NAME = "Schüler"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    has_had_introduction = models.BooleanField(default=False)  # pyright: ignore[reportArgumentType]
    external_mail = models.EmailField(blank=True, null=True)
    phone_number = PhoneNumberField(blank=True, null=True)
    birthday = models.DateField(blank=True, null=True)

    bio = models.TextField(blank=True, null=True)

    ticket_count = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
    )

    def total_hours(self):
        # Build the queryset of relevant EventParticipation objects
        past_participations = self.user.event_participations.filter(  # pyright: ignore[reportAttributeAccessIssue]
            event__ending_date__lt=timezone.now(),  # only past events
            # event__final=True,  # only final events
        )

        # Aggregate the duration
        result = past_participations.aggregate(total=Sum("participation_time"))
        # If there are no matching rows, return a zero timedelta
        return result["total"] or timedelta(0)

    class Meta:
        permissions = [
            ("view_all_users", "Alle Nutzer:innen einsehen"),
            ("manage_users", "Nutzer:innen verwalten"),
            ("access_admin", "Adminbereich betreten"),
            ("view_any_points", "Punkte anderer einsehen"),
            ("view_user_mail", "E-Mail-Adressen aller Nutzer:innen einsehen"),
        ]
