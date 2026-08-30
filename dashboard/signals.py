# signals.py
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import JoinRequest, UserProfile
from .notifications import Notification, NotificationVerbChoices


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)  # pyright: ignore[reportAttributeAccessIssue]


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
