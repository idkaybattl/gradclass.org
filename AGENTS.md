# AGENTS.md

Context and rules for coding agents working in this repo. Read this first.

## Project

Django 6 website for managing a German Abitur year group (WHG Abi 2028).

- Server-rendered Django templates; HTMX for partial updates.
- German user-facing text currently.
- Main app: `dashboard`. Dev database: SQLite; production: Postgres.
- The frontend rewrite is complete. `dashboard/templates/` and
  `dashboard/static/dashboard/` are the only frontend in the tree; the previous
  UI was removed.

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
- `dashboard/views/` — function-based views split by feature: `core.py`,
  `auth.py`, `events.py`, `users.py`, `notifications.py`.
- `dashboard/permissions.py` — permission checks shared by views; see
  `docs/permissions.md` for the role matrix and adding capabilities.
- `dashboard/http_helpers.py` — `next`/`back` validation and HTMX redirects.
- `dashboard/intro.py` — forced first-run introduction redirect and decorator.
- `dashboard/feedback.py` — status-flag feedback messages and rendering.
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

## Backend rules

- Authorization is capability-based: use `dashboard/permissions.py` helpers,
  never `is_staff` or group names. See `docs/permissions.md`.
- Follow the existing function-based view style: `@login_required`,
  `@require_GET` / `@require_POST`, `get_object_or_404`.
- Keep views thin. Put multi-step business logic in `services.py`; keep
  validation and field definitions in `forms.py`.
- App actions use the feedback pattern below, not `django.contrib.messages`.
  Messages are only for flows whose destination is a full page load.
- For HTMX responses, render partials with
  `render_to_string(..., request=request)`. Use `JsonResponse` only for small
  success/error endpoints.
- Redirects and HTMX responses: follow **Redirects and HTMX** below.
- Logout must stay a CSRF-protected POST form; Django 6 rejects GET logout.
- Event lists show all events to every user; all-users visibility is
  intentional.
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

## Overlays and HTMX fragments

- `data-overlay-toggle="<id>"` toggles an overlay; `data-overlay-open="<id>"`
  only opens/navigates it. Use the latter for detail, back and notification links.
- The bottom sheet is navigation, not routing: **no history entries**. “Zurück”
  is an explicit `hx-get` to the previous panel; browser back is not used to
  reopen it unless this decision is changed here.
- Back and close are different controls. “Zurück” is on the left of the panel
  header and only renders when `back_url` is valid. The shell’s `.overlay-close`
  (X) is the only close control, top-right. Never render a second close button
  in a panel.
- Overlay partials are fragments: no `{% extends %}`, `<html>`, navbar, footer or
  overlay shell. They may only depend on context passed by their own view. Load
  their CSS/JS from `base.html`, not from the fragment.
- Overlay-only form URLs redirect on a direct (non-HTMX) GET. An invalid
  non-HTMX POST renders the full-page wrapper (`*/form.html`, `users/password.html`)
  so a no-JS submission never exposes a bare fragment.
- Validate `back`/`next` through `get_safe_back_url` / `get_safe_next_url`.
  `next` is a redirect hint; `back` only navigates one overlay level.
- `redirect_next_or` is the only place that chooses between a normal redirect
  and `HX-Redirect`. Use `render_page_or_partial` for views that also render a
  full-page fallback.
- Invalid HTMX forms re-render with status 200 and preserved `next_url`.
- App actions use server-rendered feedback (`components/_feedback.html`) and
  `?status=` flags on non-HTMX redirects, not `django.contrib.messages`.

## Frontend rules

- Design tokens: `dashboard/static/dashboard/css/vars.css`.
- Shared components: `dashboard/static/dashboard/css/components.css` — `.btn`, `.field`, `.input`, `.checkbox`, `.errorlist`.
- Page styles: `base.css` (shell, nav, footer, overlays, menu), `index.css`, `login.css`.
- Use the existing tokens and components. Do not hardcode colours, font sizes, or border widths. Font sizes use `--font-size-sm/base/lg/xl`.
- Style: flat, square corners, one border thickness (`--border-width`). Avoid
  `border-radius`.
- Font: self-hosted BioRhyme. Do not add a Google Fonts CDN link.
- Mobile-first and responsive. Preserve the overlay/menu drag behaviour in `base.css` and `base.js`.
- Use `{% static %}` for assets. Run `collectstatic` after static changes.
- Component initialisers expose `window.initX(root)`, are idempotent and scoped to
  `root`. `base.js` is the only place that calls them, on `DOMContentLoaded` and
  `htmx:afterSwap`.
- Overlay requests use the global `#overlay-loading` indicator. `base.js` renders
  an error feedback panel on `htmx:responseError`, `sendError` and `timeout`.
- Overlays dispatch `overlay:open`; use it with `hx-trigger` to lazy-load overlay content.
- Icons use `.logo` with the inline `--icon` pattern; follow it.
- Icons, fonts, and vendored libraries are assets, not code to edit.

## Working style

- Make the smallest change that solves the task.
- During feature planning, have a conversation, not a monologue. Discuss the
  current question, suggest a few options with tradeoffs, and ask for
  confirmation. Keep answers short; do not dump a full plan before the key
  decisions are settled.
- For larger work (several files, a new pattern, schema or API changes), outline
  a short plan only once the open decisions are resolved, then edit.
- Critically question the user's ideas. Point out tradeoffs, risks, and
  simpler alternatives instead of just agreeing.
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
- Run `collectstatic` after static changes, and **before running the full test
  suite**. Tests use the static manifest and fail with `Missing staticfiles
  manifest entry` for any new or changed asset that has not been collected.
- Add tests only for behavior that could break silently or has regressed
  before. Skip tests for trivial template, CSS, or copy changes.

## Maintenance

- Update this file only when a shared convention, token, component, command, or structure changes.
- Keep it short; prefer pointing to canonical files over duplicating values.
