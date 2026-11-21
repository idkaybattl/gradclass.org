from django.conf import settings
from django.db import migrations

ABIKASSE_PERMISSIONS = {
    "view_abikasse": "Abikasse einsehen",
    "manage_abikasse": "Abikasse verwalten",
}
USERPROFILE_PERMISSIONS = {
    "view_any_points": "Punkte anderer einsehen",
}


def _permissions(apps, model_name, entries):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")

    content_type, _ = ContentType.objects.get_or_create(
        app_label="dashboard", model=model_name
    )
    created = {}
    for codename, name in entries.items():
        permission, _ = Permission.objects.get_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": name},
        )
        if permission.name != name:
            permission.name = name
            permission.save(update_fields=["name"])
        created[codename] = permission
    return created


def grant(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)

    abikasse = _permissions(apps, "abikasse", ABIKASSE_PERMISSIONS)
    profile = _permissions(apps, "userprofile", USERPROFILE_PERMISSIONS)

    student_group, _ = Group.objects.get_or_create(name="Schüler")
    rep_group, _ = Group.objects.get_or_create(name="Stufensprecher")

    student_group.permissions.add(abikasse["view_abikasse"])
    rep_group.permissions.add(
        abikasse["view_abikasse"],
        abikasse["manage_abikasse"],
        profile["view_any_points"],
    )

    # Everyone counts as a student, including superusers.
    for user in User.objects.all():
        user.groups.add(student_group)


def revoke(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)

    student_group = Group.objects.filter(name="Schüler").first()
    rep_group = Group.objects.filter(name="Stufensprecher").first()
    abikasse = {
        codename: Permission.objects.filter(
            content_type__app_label="dashboard", codename=codename
        ).first()
        for codename in ABIKASSE_PERMISSIONS
    }
    profile = {
        codename: Permission.objects.filter(
            content_type__app_label="dashboard", codename=codename
        ).first()
        for codename in USERPROFILE_PERMISSIONS
    }

    if student_group and abikasse["view_abikasse"]:
        student_group.permissions.remove(abikasse["view_abikasse"])

    if rep_group:
        rep_group.permissions.remove(
            *[
                permission
                for permission in (
                    abikasse["view_abikasse"],
                    abikasse["manage_abikasse"],
                    profile["view_any_points"],
                )
                if permission
            ]
        )

    if student_group:
        for user in User.objects.filter(is_superuser=True):
            user.groups.remove(student_group)


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0016_abiballconfig_alter_abikasse_options_and_more"),
        ("contenttypes", "0002_remove_content_type_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(grant, revoke),
    ]
