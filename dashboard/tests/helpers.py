from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission

User = get_user_model()


def make_rep(username, **kwargs):
    kwargs.setdefault("password", "password")
    user = User.objects.create_user(username=username, **kwargs)
    user.groups.add(Group.objects.get(name="Stufensprecher"))
    return user


def make_limited_creator(username):
    user = User.objects.create_user(username=username, password="password")
    user.user_permissions.add(Permission.objects.get(codename="create_event"))
    return user
