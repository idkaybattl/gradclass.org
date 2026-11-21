# signals.py
from django.conf import settings
from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import (
    STUDENT_GROUP_NAME,
    AbiballConfig,
    Event,
    JoinRequest,
    UserProfile,
)
from .notifications import Notification, NotificationVerbChoices
from .services import sync_event_earnings_entry


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        config = AbiballConfig.objects.filter(pk=1).first()
        defaults = {}
        if config is not None:
            defaults["ticket_count"] = config.default_ticket_count
        UserProfile.objects.get_or_create(user=instance, defaults=defaults)  # pyright: ignore[reportAttributeAccessIssue]


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def add_default_group(sender, instance, created, **kwargs):
    if not created:
        return
    group, _ = Group.objects.get_or_create(name=STUDENT_GROUP_NAME)
    instance.groups.add(group)


@receiver(post_save, sender=Event)
def sync_event_ledger(sender, instance, **kwargs):
    sync_event_earnings_entry(instance)


@receiver(post_save, sender=JoinRequest)
def notify_manager_on_join_request(sender, instance: JoinRequest, created, **kwargs):
    if not created:
        return

    manager = instance.event.manager
    # payload: notifications.py expects "requestor" to build the display string
    payload = {
        "requestor": str(instance.requestor),
        "requestor_id": instance.requestor.pk,
        # you can add more metadata if you want
    }

    # Create notification for the manager
    Notification.objects.create(
        user=manager,
        verb=NotificationVerbChoices.EVENT_JOIN_REQUEST,
        target=instance,
        payload=payload,
    )
