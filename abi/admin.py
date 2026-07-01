from django.contrib import admin

from .models import Abikasse, Notification, Project

admin.site.register(Project)
admin.site.register(Abikasse)
admin.site.register(Notification)
