from django.db import migrations

RENAMES = {
    "Schüler:in": "Schüler",
    "Stufensprecher:in": "Stufensprecher",
}


def _merge_group(Group, old_name, new_name):
    old_group = Group.objects.filter(name=old_name).first()
    if old_group is None:
        return

    new_group = Group.objects.filter(name=new_name).first()
    if new_group is None:
        old_group.name = new_name
        old_group.save(update_fields=["name"])
        return

    new_group.permissions.add(*old_group.permissions.all())
    for user in old_group.user_set.all():
        user.groups.add(new_group)
    old_group.delete()


def rename_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for old_name, new_name in RENAMES.items():
        _merge_group(Group, old_name, new_name)


def restore_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for old_name, new_name in RENAMES.items():
        _merge_group(Group, new_name, old_name)


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0009_seed_permission_groups"),
    ]

    operations = [
        migrations.RunPython(rename_groups, restore_groups),
    ]
