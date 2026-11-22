from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import (
    Abikasse,
    Event,
    EventParticipation,
    JoinRequest,
    Quote,
    QuoteLine,
    QuoteReport,
    UserProfile,
)
from .notifications import Notification


# Define an inline admin descriptor for Employee model
# which acts a bit like a singleton
class EmployeeInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = "employee"


# Define a new User admin
class UserAdmin(BaseUserAdmin):
    inlines = [EmployeeInline]


# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

admin.site.register(Event)
admin.site.register(Abikasse)
admin.site.register(Notification)
admin.site.register(EventParticipation)
admin.site.register(JoinRequest)


class QuoteLineInline(admin.TabularInline):
    model = QuoteLine
    extra = 0


class QuoteAdmin(admin.ModelAdmin):
    inlines = [QuoteLineInline]
    list_display = ("__str__", "uploader", "spoken_on", "created_at")
    search_fields = (
        "extra_info",
        "lines__text",
        "lines__speaker",
        "uploader__first_name",
        "uploader__last_name",
        "uploader__username",
    )


class QuoteReportAdmin(admin.ModelAdmin):
    list_display = ("__str__", "reporter", "created_at")
    search_fields = (
        "reason",
        "quote__lines__text",
        "quote__lines__speaker",
        "reporter__first_name",
        "reporter__last_name",
        "reporter__username",
    )


admin.site.register(Quote, QuoteAdmin)
admin.site.register(QuoteReport, QuoteReportAdmin)
