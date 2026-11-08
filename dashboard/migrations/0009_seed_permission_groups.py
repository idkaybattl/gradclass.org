from django.conf import settings
from django.db import migrations

GROUP_PERMISSIONS = {
    "Schüler": [
        "view_all_users",
    ],
    "Stufensprecher": [
        "create_event",
        "edit_any_event",
        "delete_any_event",
        "approve_event",
        "manage_earnings",
        "manage_participation_times",
        "manage_join_requests",
        "view_all_users",
    ],
}

MODEL_PERMISSIONS = {
    "event": [
        ("create_event", "Aktionen erstellen"),
        ("edit_any_event", "Beliebige Aktionen bearbeiten"),
        ("delete_any_event", "Beliebige Aktionen löschen"),
        ("approve_event", "Aktionen freigeben"),
        ("manage_earnings", "Einnahmen verwalten"),
        ("manage_participation_times", "Arbeitszeiten verwalten"),
        ("manage_join_requests", "Teilnahmeanfragen verwalten"),
    ],
    "userprofile": [
        ("view_all_users", "Alle Nutzereinsehen"),
        ("manage_users", "Nutzerverwalten"),
        ("access_admin", "Adminbereich betreten"),
    ],
}


def seed_groups(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)

    permissions = {}
    for model, entries in MODEL_PERMISSIONS.items():
        content_type, _ = ContentType.objects.get_or_create(
            app_label="dashboard", model=model
        )
        for codename, name in entries:
            permission, _ = Permission.objects.get_or_create(
                content_type=content_type,
                codename=codename,
                defaults={"name": name},
            )
            permissions[codename] = permission

    groups = {}
    for group_name, codenames in GROUP_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        group.permissions.set([permissions[codename] for codename in codenames])
        groups[group_name] = group

    student_group = groups["Schüler"]
    for user in User.objects.filter(is_superuser=False):
        user.groups.add(student_group)


def remove_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=GROUP_PERMISSIONS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0008_alter_event_options_alter_userprofile_options"),
        ("contenttypes", "0002_remove_content_type_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(seed_groups, remove_groups),
    ]
