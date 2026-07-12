from django.contrib import admin

from .models import Abikasse, Project, ProjectParticipation
from .notifications import Notification

admin.site.register(Project)
admin.site.register(Abikasse)
admin.site.register(Notification)
admin.site.register(ProjectParticipation)
