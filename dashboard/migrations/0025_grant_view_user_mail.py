from django.db import migrations

PERMISSION = ("view_user_mail", "E-Mail-Adressen aller Nutzer:innen einsehen")
GROUP_NAME = "Stufensprecher"


def grant_view_user_mail(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")

    content_type, _ = ContentType.objects.get_or_create(
        app_label="dashboard", model="userprofile"
    )
    permission, _ = Permission.objects.get_or_create(
        content_type=content_type,
        codename=PERMISSION[0],
        defaults={"name": PERMISSION[1]},
    )
    group = Group.objects.filter(name=GROUP_NAME).first()
    if group:
        group.permissions.add(permission)


def revoke_view_user_mail(apps, schema_editor):
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
        ("dashboard", "0024_alter_userprofile_options"),
    ]

    operations = [
        migrations.RunPython(grant_view_user_mail, revoke_view_user_mail),
    ]
