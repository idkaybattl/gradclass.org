# AGENTS.md

Context and rules for coding agents working in this repo. Read this first.

## Project

Django 6 website for managing a German Abitur year group (WHG Abi 2028).

- Server-rendered Django templates; HTMX for partial updates.
- German user-facing text currently.
- Main app: `dashboard`. Dev database: SQLite; production: Postgres.
- The frontend is being rewritten. The old UI is archived in
  `dashboard/oldtemplates/` and `dashboard/oldstatics/`.

## Commands

- Run: `.venv/bin/python manage.py runserver`
- Check: `.venv/bin/python manage.py check`
- Tests: `.venv/bin/python manage.py test`
- Static: `.venv/bin/python manage.py collectstatic --noinput`
- Vendor JS: `npm install` (postinstall copies htmx/cropper into
  `dashboard/static/vendor/`)
- Do not run `import_student_accounts` or `send_account_mails` unless asked;
  they modify users and send email.

## Structure

- `gradclassorg/` — settings and root URLs.
- `dashboard/views.py` — function-based views.
- `dashboard/context_processors.py` — template-wide unread notification count.
- `dashboard/forms.py` — forms and widgets.
- `dashboard/models.py` — models.
- `dashboard/services.py` — multi-step domain logic (e.g. `save_event`).
- `dashboard/notifications.py` — notification model and creation.
- `dashboard/signals.py` — signal handlers.
- `dashboard/urls.py` — URL names.
- `dashboard/management/commands/` — account import/mail commands.
- `dashboard/templates/` — active templates.
- `dashboard/static/dashboard/` — active CSS, JS, fonts, icons.
- `dashboard/oldtemplates/`, `dashboard/oldstatics/` — archived; do not use or
  edit.

The active template set is sparse while the rewrite is in progress. If a view
points at a template that only exists in `oldtemplates/`, treat that as part of the rewrite and ask before restoring old markup.

## Backend rules

- Follow the existing function-based view style: `@login_required`,
  `@require_GET` / `@require_POST`, `get_object_or_404`.
- Keep views thin. Put multi-step business logic in `services.py`; keep
  validation and field definitions in `forms.py`.
- Use `django.contrib.messages` for user feedback.
- For HTMX responses, render partials with
  `render_to_string(..., request=request)`. Use `JsonResponse` only for small
  success/error endpoints.
- Redirects and HTMX responses: follow **Redirects and HTMX** below.
- Logout must stay a CSRF-protected POST form; Django 6 rejects GET logout.
- User-facing strings are German.
- Add migrations for model changes. Never reset or delete the dev database.
- Do not touch `.env`, `db.sqlite3`, `.venv`, `node_modules`, or `staticfiles/`.

## Redirects and HTMX

- `next` is a navigation hint, never authorization. Validate it only with
  `get_safe_next_url`.
- Keep `get_safe_next_url` and `redirect_next_or` as the single place for
  `next` handling; don't inline `?next=` handling in views.
- Normal form success: POST/redirect/GET. On failure, re-render with errors and
  preserve the validated `next_url`.
- When HTMX is in use, `redirect_next_or` should be the only place that
  distinguishes a normal redirect from `HX-Redirect`.
- HTMX full-page navigation: return `HX-Redirect` (or `HX-Location`). A plain
  302 is followed by HTMX and its HTML is swapped into the target.
- HTMX fragment update: return the partial, or `204` + `HX-Trigger` when there
  is nothing to swap.
- Invalid HTMX form: re-render the partial with errors and preserve
  `next_url`. Use a 2xx unless response handling is configured to swap 4xx.
- Do not use `next` for actions that only close a popup or refresh a fragment.
- URL-encode `next` when placing it in a link; hidden inputs are autoescaped.

## Frontend rules

- Design tokens: `dashboard/static/dashboard/css/vars.css`.
- Shared components: `dashboard/static/dashboard/css/components.css` — `.btn`, `.field`, `.errorlist`.
- Page styles: `base.css` (shell, nav, footer, overlays, menu), `index.css`, `login.css`.
- Use the existing tokens and components. Do not hardcode colours, font sizes, or border widths. Font sizes use `--font-size-sm/base/lg/xl`.
- Style: flat, square corners, one border thickness (`--border-width`). Avoid
  `border-radius`.
- Font: self-hosted BioRhyme. Do not add a Google Fonts CDN link.
- Mobile-first and responsive. Preserve the overlay/menu drag behaviour in `base.css` and `base.js`.
- Use `{% static %}` for assets. Run `collectstatic` after static changes.
- Overlays dispatch `overlay:open`; use it with `hx-trigger` to lazy-load overlay content.
- Icons use `.logo` with the inline `--icon` pattern; follow it.
- Icons, fonts, and vendored libraries are assets, not code to edit.

## Working style

- Make the smallest change that solves the task.
- For larger work (several files, a new pattern, schema or API changes),
  outline a short plan before editing.
- Stop and ask when the request is ambiguous, has multiple reasonable
  interpretations, or when you see a materially simpler approach. Do not
  silently choose a different design.
- Reuse existing helpers and components. When a pattern appears a second or
  third time, extract it (CSS component, template partial, form widget,
  service helper). Do not generalise from a single use.
- Keep diffs focused; do not refactor unrelated code.
- Do not add dependencies, commit, or push unless asked.
- Comments only where they explain structure, intent, or a non-obvious
  constraint.

## Validation

- Run `manage.py check` after backend changes.
- Render the affected pages (test client or `runserver`) after template/view
  changes.
- Run `collectstatic` after static changes.
- The automated test suite is still minimal; add tests where practical when
  fixing logic.

## Maintenance

- Update this file only when a shared convention, token, component, command, or structure changes.
- Keep it short; prefer pointing to canonical files over duplicating values.
