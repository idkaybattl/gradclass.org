from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import Abikasse, Event, EventParticipation, JoinRequest, UserProfile
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
