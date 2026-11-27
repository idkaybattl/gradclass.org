from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import (
    Abikasse,
    Event,
    EventParticipation,
    JoinRequest,
    Option,
    Poll,
    Question,
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

    def get_inline_instances(self, request, obj=None):
        # A new user gets its UserProfile from the post_save signal, so the
        # inline must not try to create a second one on the add form.
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)


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


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0


class OptionInline(admin.TabularInline):
    model = Option
    extra = 0


class PollAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "mode",
        "phase_display",
        "creator",
        "created_at",
        "suggestion_deadline",
        "voting_deadline",
    )
    list_filter = ("mode", "results_public", "suggestions_public")
    search_fields = ("title", "description", "creator__username")
    readonly_fields = ("created_at", "phase_display")
    inlines = [QuestionInline]

    @admin.display(description="Phase")
    def phase_display(self, poll):
        return poll.phase.label


class QuestionAdmin(admin.ModelAdmin):
    list_display = ("prompt", "poll", "kind", "order")
    list_filter = ("kind",)
    search_fields = ("prompt", "poll__title")
    inlines = [OptionInline]


class OptionAdmin(admin.ModelAdmin):
    list_display = ("label", "question", "state", "created_by", "order")
    list_filter = ("state",)
    search_fields = ("label", "question__prompt", "question__poll__title")


admin.site.register(Poll, PollAdmin)
admin.site.register(Question, QuestionAdmin)
admin.site.register(Option, OptionAdmin)
