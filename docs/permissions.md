# Permissions and roles

Roles are Django auth **groups**; capabilities are Django **permissions**.
`dashboard/permissions.py` is the only place that answers "may this user do X?".
Views pass booleans to templates; templates never check groups or `is_staff`.

## Managing roles

Django admin is the role UI:

- **Groups → Add group**: create a role and tick its capabilities.
- **Users → user → Groups**: a user can be in several groups, which is intended.
  Permissions are the union; there are no deny rules or precedence.
- Code checks permissions only, never group names. The one exception is
  `dashboard/signals.py`, which puts new non-superusers in the default group.

Group names are display labels. Renaming a group does not change authorization,
but it breaks the default-group assignment in `signals.py` (it would create a
new group with the old name).

## Roles

| Group | Purpose |
|---|---|
| `Schüler` | Baseline role; every non-superuser is added on creation |
| `Stufensprecher` | Student representatives |
| superuser | Server admin; passes every check implicitly |

## Capabilities

| Capability | Schüler | Stufensprecher | Superuser |
|---|:--:|:--:|:--:|
| `create_event` | – | ✓ | ✓ |
| `edit_any_event` | – | ✓ | ✓ |
| `delete_any_event` | – | ✓ | ✓ |
| `approve_event` | – | ✓ | ✓ |
| `manage_earnings` | – | ✓ | ✓ |
| `manage_participation_times` | – | ✓ | ✓ |
| `manage_join_requests` | own events only | ✓ | ✓ |
| `bypass_event_creation_limit` | – | ✓ | ✓ |
| `view_all_users` | ✓ | ✓ | ✓ |
| `manage_users` | – | – | ✓ |
| `access_admin` | – | – | ✓ |

`approve_event` is defined for the future approval flow; it is not consumed yet.

## Object rules

These are independent of groups and live in `permissions.py`:

- The event creator or manager may edit/delete their own event while it is not
  final.
- The event creator or manager may manage join requests and set the earnings
  amount for their event.
- Any user may join/leave an event they are not managing, view their own
  profile, and change their own password.
- Only `manage_earnings` holders (reps/superuser) may mark earnings as received
  and finalise the event.
- Final events are read-only for everyone.

## Admin access

`/admin/` is gated by `access_admin` through `gradclassorg/admin_site.py`.
Django's admin login form still requires `is_staff`, so a future non-superuser
admin needs **both** `access_admin` and `is_staff`. The admin menu link uses the
same capability, so `is_staff` alone does not expose it.

## Adding a capability

1. Add the codename and German label to `Meta.permissions` in
   `dashboard/models.py`; run `makemigrations`.
2. Add a constant and a `can_*` helper in `dashboard/permissions.py`.
3. Grant it to a group in Django admin (or in a data migration for defaults).
4. Use the helper in the view and pass a boolean to the template.
5. Add a positive and a negative test.
