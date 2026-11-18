from datetime import timedelta

from django.test import RequestFactory, TestCase
from django.utils import timezone
from gradclassorg.admin_site import CapabilityAdminSite

from .. import permissions
from ..models import Event
from .helpers import User, make_rep


class PermissionMatrixTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="student", password="password")
        self.manager = User.objects.create_user(username="manager", password="password")
        self.rep = make_rep("rep")
        self.superuser = User.objects.create_superuser(
            username="superuser", password="password"
        )
        self.event = Event.objects.create(
            title="Sommerfest",
            description="",
            starting_date=timezone.now() + timedelta(days=1),
            ending_date=timezone.now() + timedelta(days=1, hours=2),
            creator=self.manager,
            manager=self.manager,
        )

    def request_for(self, user):
        request = RequestFactory().get("/")
        request.user = user
        return request

    def test_create_event_capability(self):
        self.assertFalse(permissions.can_create_event(self.student))
        self.assertTrue(permissions.can_create_event(self.rep))
        self.assertTrue(permissions.can_create_event(self.superuser))

    def test_reps_bypass_creation_limit(self):
        self.assertFalse(permissions.can_bypass_event_creation_limit(self.student))
        self.assertTrue(permissions.can_bypass_event_creation_limit(self.rep))
        self.assertTrue(permissions.can_bypass_event_creation_limit(self.superuser))

    def test_event_edit_respects_ownership_and_final_state(self):
        self.assertFalse(permissions.can_edit_event(self.student, self.event))
        self.assertTrue(permissions.can_edit_event(self.manager, self.event))
        self.assertTrue(permissions.can_edit_event(self.rep, self.event))
        self.assertTrue(permissions.can_delete_event(self.rep, self.event))

        self.event.final = True
        self.event.save(update_fields=["final"])

        self.assertFalse(permissions.can_edit_event(self.manager, self.event))
        self.assertFalse(permissions.can_edit_event(self.rep, self.event))
        self.assertFalse(permissions.can_delete_event(self.superuser, self.event))

    def test_join_request_and_participation_capabilities(self):
        self.assertFalse(permissions.can_manage_join_requests(self.student, self.event))
        self.assertTrue(permissions.can_manage_join_requests(self.manager, self.event))
        self.assertTrue(permissions.can_manage_join_requests(self.rep, self.event))
        self.assertFalse(permissions.can_manage_participation_times(self.student))
        self.assertTrue(permissions.can_manage_participation_times(self.rep))

    def test_only_reps_mark_earnings_received(self):
        self.assertFalse(permissions.can_manage_earnings(self.manager))
        self.assertTrue(permissions.can_manage_earnings(self.rep))
        self.assertTrue(permissions.can_manage_earnings(self.superuser))

    def test_user_management_is_superuser_only(self):
        manager_request = self.request_for(self.manager)
        rep_request = self.request_for(self.rep)
        admin_request = self.request_for(self.superuser)

        self.assertTrue(permissions.can_edit_user(manager_request, self.manager.pk))
        self.assertFalse(permissions.can_edit_user(rep_request, self.manager.pk))
        self.assertTrue(permissions.can_edit_user(admin_request, self.manager.pk))
        self.assertFalse(permissions.can_change_password(rep_request, self.manager.pk))
        self.assertTrue(permissions.can_change_password(admin_request, self.manager.pk))

    def test_all_users_can_view_the_user_directory(self):
        self.assertTrue(permissions.can_view_users(self.request_for(self.student)))
        self.assertTrue(permissions.can_view_users(self.request_for(self.rep)))

    def test_admin_site_requires_access_admin(self):
        site = CapabilityAdminSite()

        self.assertTrue(site.has_permission(self.request_for(self.superuser)))
        self.assertFalse(site.has_permission(self.request_for(self.rep)))

        self.student.is_staff = True
        self.assertFalse(site.has_permission(self.request_for(self.student)))
        self.assertFalse(permissions.can_access_admin(self.rep))
        self.assertTrue(permissions.can_access_admin(self.superuser))
