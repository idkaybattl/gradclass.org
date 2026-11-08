from django.contrib.admin import AdminSite
from django.contrib.admin.apps import AdminConfig

from dashboard.permissions import can_access_admin


class CapabilityAdminSite(AdminSite):
    def has_permission(self, request):
        return request.user.is_active and can_access_admin(request.user)


class CapabilityAdminConfig(AdminConfig):
    default_site = "gradclassorg.admin_site.CapabilityAdminSite"
