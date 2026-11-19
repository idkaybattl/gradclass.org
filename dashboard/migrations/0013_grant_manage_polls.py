from django.db import migrations

PERMISSION = ("manage_polls", "Umfragen verwalten")
GROUP_NAME = "Stufensprecher"


def grant_manage_polls(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")

    content_type, _ = ContentType.objects.get_or_create(
        app_label="dashboard", model="poll"
    )
    permission, _ = Permission.objects.get_or_create(
        content_type=content_type,
        codename=PERMISSION[0],
        defaults={"name": PERMISSION[1]},
    )
    group = Group.objects.filter(name=GROUP_NAME).first()
    if group:
        group.permissions.add(permission)


def revoke_manage_polls(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")

    permission = Permission.objects.filter(
        content_type__app_label="dashboard", codename=PERMISSION[0]
    ).first()
    group = Group.objects.filter(name=GROUP_NAME).first()
    if permission and group:
        group.permissions.remove(permission)


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0012_poll_question_option_ballot_ballotvote_and_more"),
    ]

    operations = [
        migrations.RunPython(grant_manage_polls, revoke_manage_polls),
    ]
