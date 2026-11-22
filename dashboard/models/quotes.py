from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class Quote(models.Model):
    uploader = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quotes",
    )
    spoken_on = models.DateField(default=timezone.localdate)
    extra_info = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-spoken_on", "-created_at"]
        permissions = [
            ("manage_quotes", "Zitate verwalten"),
        ]

    def __str__(self):
        first_line = self.lines.first()
        if first_line is None:
            return "Zitat"
        text = first_line.text.strip()
        return text[:60] + ("…" if len(text) > 60 else "")


class QuoteLine(models.Model):
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name="lines")
    speaker = models.CharField(max_length=200)
    text = models.TextField()
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.speaker}: {self.text[:40]}"


class QuoteReport(models.Model):
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name="reports")
    reporter = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="quote_reports"
    )
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("quote", "reporter")
        ordering = ["created_at"]

    def __str__(self):
        return f"Meldung zu {self.quote}"
