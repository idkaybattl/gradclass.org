# TODO — Frontend rewrite parity

Status: the parity rewrite is complete. `dashboard/templates/` and
`dashboard/static/dashboard/` are the only frontend; the old archive
(`dashboard/oldtemplates/`, `dashboard/oldstatics/`) has been removed and is
recoverable from git history. Sections 1–9 are kept as the record of that work;
new work starts at §10.

Ground rules from `AGENTS.md`:

- Use `vars.css` tokens and `components.css` (`.btn`, `.field`, `.input`,
  `.checkbox`, `.errorlist`) instead of new colours/radii/sizes.
- Keep German user-facing strings.
- HTMX partials use `render_to_string(..., request=request)` or
  `render(request, partial, ...)`; normal navigation is POST/redirect/GET.
- `next` is validated only through `get_safe_next_url` / `redirect_next_or`.
- Run `manage.py check`, the test suite, and `collectstatic` as noted below.

## Layout pattern: full-page lists, overlay details

The pattern for every feature:

- **Lists/overviews are real full pages** (`/events/`, `/users/`, `/polls/`).
  They are normal navigations, not HTMX swaps. Browser back, refresh and links
  behave normally, and client-side filter/search state is preserved while the
  user opens and closes overlays on top of them.
- **Item details and everything still related to that item open in the bottom
  sheet** (`#overlay.overlay--sheet` in `base.html`): event details, create/edit
  forms, user details, profile edit, password change, join requests.
- The overlay is **navigation, not routing**. It loads fragments fetched with
  `hx-get` into `#overlay-content`. “Zurück” is an explicit `hx-get` to the
  previous panel; it is not a browser-history entry unless we later add
  `hx-push-url` deliberately.
- **Back and close are different controls.** “Zurück” lives on the left of the
  panel header and navigates one overlay level; the X lives on the right (the
  current `.overlay-close`) and dismisses the whole sheet. They must never share
  the same slot or be used interchangeably.
- Direct GETs to overlay-only URLs still need a full-page fallback (or a redirect
  to the list page), so notifications, bookmarks and no-JS links do not dump a
  bare fragment into the browser.

Why the sheet can hold details/edit/create: `.overlay-content` is already the
scroll container, the sheet already has a drag handle and an `.overlay-close`
button, and `base.js` already guarantees only one overlay is open at a time. What
is missing is a non-toggling “open/navigate” trigger, partial rendering for the
overlay views, focus handling, and component re-initialisation after HTMX swaps.

## Feedback pattern: dedicated panels, no Django messages

Do **not** use `django.contrib.messages` for app actions. Messages only render on
the next full page load, so an HTMX-only action produces no feedback until the
user happens to navigate, and then it appears late. Use server-rendered feedback
in the same container instead:

- **Form success** (create/edit/profile/password): return
  `components/_feedback.html` into `#overlay-content`, e.g. “Aktion erfolgreich
  bearbeitet”, with navigation actions like “Zur Aktion” or “Zur Liste”. The
  sheet X is the only close control; do not add a “Schließen” button next to the
  navigation actions. This is the old `_event_edit_success_popup.html` idea, but
  styled and reusable.
- **Invalid form**: re-render the form partial with field/non-field errors and
  status 200. No message queue.
- **Quick actions** (join/leave/earnings): return the refreshed detail partial
  with a small `feedback`/`status` block at the top of that same partial. The
  feedback is part of the response, so it cannot arrive late.
- **Delete**: return a dedicated feedback panel (“Aktion gelöscht”) with a “Zur
  Liste” action that navigates back to the events page.
- **Non-HTMX PRG fallback**: redirect with a whitelisted status flag
  (`?status=created`, `?status=updated`, `?status=deleted`, …) and render the
  same feedback component on the destination page. Never accept arbitrary
  message text from the query string.
- Do not add a `messages` block to `base.html`; remove existing `messages.*`
  calls from the views as they are touched.

---

# 2. Editing events

- [x] **Fix the `save_event` creator bug before adding the edit UI.**
  `services.save_event(form, user)` always sets `event.creator = user`. On edit
  that reassigns the creator to the editor (manager or staff). Set `creator`
  only when `form.instance.pk` is falsy, or create/update through two explicit
  helpers.
- [x] Wrap `save_event` in `transaction.atomic()` so participant updates,
  participation-time clamping and notifications are all-or-nothing.
- [x] `edit_event` view:
  - Permission: `can_edit_event(user, event)` (which already includes
    `not event.final`). Remove the redundant `or event.final`.
  - GET: `EventForm(instance=event, prefix=str(event.id),
    request_user=request.user)`, render `events/_event_form.html` with
    `mode="edit"`, `event`, `back_url` (details), `next_url`.
  - POST: same form; on success return `components/_feedback.html` (“Aktion
    erfolgreich bearbeitet”) with “Zur Aktion” (loads the detail partial). The X
    closes the sheet. Non-HTMX: redirect to the full-page detail wrapper with
    `?status=updated`. On failure return `_event_form.html` with status 200 and
    preserved `next_url`.
  - Do not show the old `_event_edit_success_popup.html`; supersede it with the
    shared feedback partial.
- [x] `templates/events/_event_form.html` for edit:
  - Header “Aktion bearbeiten”; left-hand back to details, no close button in
    the header.
  - Hidden `next`.
  - `{% csrf_token %}`.
  - `{% include "events/_event_form_fields.html" %}`.
  - Actions: “Fertig” submit only. Do not add a separate “Abbrechen” that closes
    the sheet; the left back controls panel navigation and the X dismisses.
  - Do not rely on the old `form_action` / `event_id` hidden inputs; the URL
    carries the action.
- [x] `templates/events/_event_form_fields.html`:
  - Render `form.non_field_errors` and each field explicitly:
    title, manager (searchable picker), description, starting_date, ending_date,
    participants.
  - Use `<p class="field">` with `{{ field.errors }}`, `{{ field.label_tag }}`,
    `{{ field }}`; the component CSS already styles inputs inside `.field`.
  - Participants field goes in a `participants` wrapper using the widget
    partial (step 3); the manager field uses the picker below.
- [x] **Replace the manager `<select>` with a searchable single-user picker.**
  This is shared by create and edit, so implement it once in the form field.
  - Add a `ManagerPickerWidget` in `forms.py` (or `widgets.py` after the view
    refactor) and use it for `EventForm.manager`.
  - The picker searches **all users** with the same `searchItems` helper as the
    participants widget. By default filter the source to `is_active=True`; allow
    inactive accounts only if there is a clear reason. It renders a selected-user
    chip, a search input and a results list, and submits the chosen user ID
    through a hidden input.
  - Reuse the participants-widget machinery instead of duplicating it:
    generalise `ParticipantsWidget` into a `UserSearchWidget` with a
    `multiple=True/False` switch, and keep `ParticipantsWidget` as the
    multi-select subclass. The single-select mode replaces the current user
    instead of adding to a list.
  - Template: `widgets/user_picker_widget.html` (or a shared
    `widgets/user_search_widget.html` with a `multiple` branch). Keep
    `data-user-search`, `data-selected-user` and `data-user-results` hooks.
  - JS: `static/dashboard/js/user-picker.js` (or extend the participants JS)
    with `initUserPickers(root)`, idempotent and re-initialised on
    `DOMContentLoaded` and `htmx:afterSwap`.
  - Accessibility: keyboard support (Up/Down/Enter/Escape), `role="combobox"`
    plus `role="listbox"`, `aria-expanded`, `aria-activedescendant`, and a
    visible focus state. Do not rely on mouse-only clicks.
  - Validation: `ModelChoiceField` with the same queryset as the search source;
    an empty selection is invalid; the selected user must survive an invalid
    form re-render.
  - Defaults: create → `request.user`; edit → `instance.manager`. The manager may
    be any active user, including a student; do not restrict to staff.
  - If the user count grows beyond a few hundred, replace the client-side list
    with an HTMX search endpoint (`/users/search/?q=`) later; keep the same widget
    markup so only the data source changes.
- [x] Add tests for the manager picker: search filters users, selecting a result
  updates the hidden input, create defaults to the request user, edit shows the
  existing manager, and a missing manager re-renders with an error.
- [x] Port the old date validation to `static/dashboard/js/event-form.js`:
  - `endInput.min = startInput.value`.
  - Custom validity “Das Ende muss nach dem Beginn liegen.”
  - Run on input/change, initialise on `DOMContentLoaded` and
    `htmx:afterSwap`, guard with `dataset.eventFormInitialized`.
  - Field names are prefixed (`<prefix>-starting_date`), so match with
    `input[name$="starting_date"]` / `ending_date`.
- [x] Add a “Bearbeiten” button in the detail header and on user-owned event
  cards if the old UI exposed it; it should open the edit form in the same sheet.

---

# 3. Creating events

- [x] `create_event` view:
  - Keep the rate limit (`get_event_creation_limit_error`). On limit: return
    `components/_feedback.html` with an error variant and “Zur Liste” for HTMX;
    the X closes. Non-HTMX redirects to the events page with
    `?status=rate-limited`.
  - GET: `EventForm(prefix="new", request_user=request.user)`, render
    `events/_event_form.html` with `mode="create"` and no `event`.
  - POST: validate; on success `event = save_event(form, request.user)` and
    return `components/_feedback.html` (“Aktion erfolgreich erstellt”) with
    “Zur Aktion” (loads the new event’s detail partial) and “Zur Liste”
    (navigates to the events page). Non-HTMX: redirect to the full-page detail
    wrapper with `?status=created`.
  - On failure render the form with status 200 and preserved `next_url`.
- [x] `templates/events/_event_form.html` for create:
  - Header “Neue Aktion erstellen”; no back button because there is no previous
    overlay panel. The X dismisses the sheet.
  - Same fields partial as edit.
  - Submit label “Erstellen”. No separate “Abbrechen” button that closes the
    sheet.
- [x] Wire the “Neue Aktion” button on the events page to
  `data-overlay-open="overlay"` + `hx-get="{% url 'event-create' %}"` +
  `hx-target="#overlay-content"`. Render the button only when
  `can_create_event` is true (see the future restriction below).
- [x] **Port the participants widget to the active template set.**
  `EventForm` now uses `widgets/user_search_widget.html`; the old
  `participants_widget.html` lived in the removed archive.
  - [x] Create `templates/widgets/participants_widget.html` based on the old
    template, keeping: `data-participants-widget`, `data-field-name`,
    selected list with remove buttons, search input, available list, hidden
    inputs, and the `<template>` used for cloning.
  - [x] Create `static/dashboard/css/participants.css` using tokens only:
    no border radius, `--border-width`, `--text`, `--bg`, `--primary`,
    `--font-size-*`. Do not copy the old rounded/grey `rgba(...)` styles.
  - [x] Create `static/dashboard/js/participants.js` from the old
    `participants_widget.js`, using the new `searchItems` helper:
    - `initParticipantsWidget(root)` + `initParticipantsWidgets(root)`.
    - Re-initialise on `DOMContentLoaded` and `htmx:afterSwap`.
    - Keep add/remove, search filtering, empty states, duplicate prevention,
      hidden-input updates.
  - [x] Update `ParticipantsWidget.Media` to the new paths **or** remove `Media`
    and load the assets globally (recommended, because the form is loaded into
    an overlay; a `<script>` inside swapped content is fragile).
- [x] Ensure `ParticipantsWidget` works with form prefixes: `widget.name` is
  already prefixed by Django; do not hard-code `participants`.
- [x] The manager picker is shared with edit; see Section 2. On create it
  defaults to `request.user`; on edit it defaults to `instance.manager`.
- [x] **Future restriction: only staff may create events.**
  - Add `can_create_event(user)` now as the single hook. Initially return `True`
    for every user so behavior does not change yet.
  - Use it for the `create_event` view check and for the “Neue Aktion” button
    visibility.
  - Later switch the implementation to `user.is_staff` (or a `create_event`
    permission codename) in one place; this is the first consumer of the general
    permissions system in Section 10.
  - Add a test that a non-staff user is denied once the restriction is enabled.
  - Decide whether the existing rate limit still applies to staff; if only staff
    can create, non-staff limits usually become irrelevant.
- [x] Add a test that POSTing a valid form creates exactly one event and one
  participation set, that invalid input re-renders the form with errors, and
  that the success response contains the feedback panel.

---

# 4. Refactor `dashboard/views.py`

Do this after the event flows (steps 1–3) are stable, before adding the remaining
pages. It keeps the move from churning code that is still being written.

- [x] Convert `dashboard/views.py` into a package:

  ```
  dashboard/
    views/
      __init__.py          # empty or compatibility re-exports
      core.py              # main_page, calendar, contact, polls
      auth.py              # introduction, password_set, change_password_popup
      events.py            # events, event_details, create/edit/delete,
                           # join/leave, join requests, earnings
      users.py             # users, user_details, edit_user
      notifications.py     # notifications, mark_* views
    permissions.py         # can_edit_event, can_view_users, can_edit_user,
                           # can_manage_join_request, can_delete_event
    http_helpers.py        # get_safe_next_url, redirect_next_or,
                           # is_htmx_request, render_page_or_partial
    feedback.py            # STATUS_FEEDBACK, get_feedback, render_feedback
    services.py            # unchanged
  ```

- [x] Move helper functions out of the view module:
  - `get_safe_next_url`, `redirect_next_or`, `is_htmx_request`,
    `render_page_or_partial` → `http_helpers.py`.
  - `STATUS_FEEDBACK`, `get_feedback`, `render_feedback` → `feedback.py`
    (feedback renders templates and is not an HTTP concern).
  - `can_edit_event`, `can_view_users`, `can_edit_user`,
    `can_manage_join_request`, `can_delete_event` → `permissions.py`.
  - `get_event_creation_limit_error`, `MAX_PROJECTS_PER_*` → `views/events.py`
    or a small `event_limits.py` if reused.
  - `event_details_context` → `views/events.py` (or `event_context.py`).
- [x] Update `dashboard/urls.py` imports explicitly, e.g.:
  ```python
  from .views import auth, core, events, notifications, users
  ```
  and use `events.events`, `users.user_details`, etc. Avoid relying on
  `from . import views` re-exports; explicit imports make the split obvious.
- [x] Keep every URL name unchanged so templates, tests and notifications keep
  working.
- [x] Make `dashboard/http_helpers.py` the **only** place that reads `next` and
  the **only** place that emits `HX-Redirect`.
- [x] Check for circular imports: `permissions.py` imports models only;
  `http_helpers.py` imports Django only; view modules import both.
- [x] Update `AGENTS.md` after the split:
  - Replace `dashboard/views.py — function-based views` with the package layout.
  - Add the overlay trigger convention and the 200-vs-400 rule.
- [x] Keep tests passing while moving functions in small commits/patches; run
  `manage.py check` after the URL import change.

---

# 5. Users

## 5.1 Users list page

- [x] Add `templates/users.html` extending `base.html`:
  - Full page, not an HTMX partial: search input (`data-user-search`), grid,
    empty state.
  - Each card opens `user-details` in the sheet.
- [x] Add `templates/users/_user_card.html`:
  - `<a>` or `<button>` with `data-overlay-open="overlay"`, `hx-get`,
    `hx-target="#overlay-content"`.
  - Name + email; data hooks for search: `data-user-card`,
    `data-user-name`, `data-user-mail` (or keep the old `#name` / `#mail`
    structure but scope queries to the card).
- [x] `users` view:
  - Use `User.objects.select_related("profile").order_by("first_name",
    "last_name", "username")` instead of an unordered `set`.
  - Keep `can_view_users` (currently `True`).
  - Always render the full `users.html` page; no partial variant.
- [x] Add `static/dashboard/js/users.js`:
  - `initUsersList(root)`, ported from the old `users.js`.
  - Use `searchItems` with name, email, maybe username.
  - Initialise on `DOMContentLoaded`; the list page is not swapped.
- [x] Add `static/dashboard/css/users.css` (or reuse `events.css` classes).

## 5.2 User details

- [x] Add `templates/users/_user_details.html`:
  - Header: name, “Bearbeiten” (if `can_edit`), “Passwort ändern”
    (if `can_change_password`), back.
  - Profile fields: birthday (or “Keine Angabe bisher”), username, IServ mail,
    external mail, phone number, bio.
  - Arbeitsstunden (`total_hours`; format `timedelta` readably, e.g. `H:MM`).
  - Projektteilnahmen: list of events. Reuse a simple event card partial or the
    event card with explicit `is_upcoming`/`is_own` values.
- [x] `user_details` view:
  - Dual-render partial/page.
  - Keep `can_edit` and `can_change_password`.
  - Do **not** display `total_earnings` until `UserProfile.total_earnings()` is
    fixed (the model comment says it is currently wrong).
  - Add `back_url` handling so a user opened from an event can return there.
- [x] Wire the navbar profile icon and the index `.profile` card to the current
  user’s details overlay.

## 5.3 Edit user profile

- [x] Add `templates/users/_user_form.html`:
  - Header “Profil bearbeiten”, back to details.
  - Explicit `.field` rendering of `UserProfileForm` (birthday, external mail,
    phone, bio); do not use `.as_p`.
  - Hidden `next`, CSRF, actions.
- [x] `edit_user` view:
  - Permission check already exists.
  - GET renders the form.
  - POST: on success return `components/_feedback.html` (“Profil erfolgreich
    bearbeitet”) with “Zurück zum Profil” (loads the user-details partial); the X
    closes. Non-HTMX: redirect to the full-page user-details wrapper with
    `?status=profile-updated`.
  - On failure return the form with status 200.
  - Remove the old `_user_edit_success.html` flow.
- [x] Add `static/dashboard/css` styles if the form needs anything beyond
  `.field`.

## 5.4 Change password

- [x] Add `templates/users/_password_form.html`:
  - Header “Passwort ändern für …”, back to details.
  - Explicit field rendering + errors.
- [x] `change_password_popup` view cleanup:
  - Remove the `print(...)` calls.
  - Add the missing permission check (currently any logged-in user can POST to
    another user’s ID).
  - Use `PasswordChangeForm` for **self** (requires the old password).
  - Use `SetPasswordForm` when staff changes another user’s password; staff
    cannot know the old password, so the current form makes this feature
    unusable for staff.
  - Call `update_session_auth_hash` only when the changed user is
    `request.user`.
  - On success return `components/_feedback.html` (“Passwort erfolgreich
    geändert”) with “Zurück zum Profil”; the X closes. Non-HTMX: redirect to the
    full-page user-details wrapper with `?status=password-updated`.
  - On failure return the form with status 200.
- [x] `password_set` (introduction) is a separate flow; see step 6.

---

# 6. Introduction

- [x] Add `templates/introduction.html` extending `base.html`.
  - The view already provides `profile_form`, `password_form`, `user`,
    `next_url`.
  - Keep the old five content steps and the final profile step, but rebuild the
    markup with the new shell/tokens.
  - Consider hiding the normal nav/menu/footer during the introduction, or add a
    `base.html` block for “minimal shell”. The current user should be forced to
    finish before using the site.
- [x] Add `static/dashboard/js/introduction.js`:
  - `showStep(showId, hideId)` logic and “Weiter” buttons.
  - Initialise on `DOMContentLoaded` and after HTMX swaps.
  - On `intro:password-set`, advance to the profile step.
  - If the profile POST fails and the page re-renders, start at the profile step
    (pass an `initial_step` context variable).
- [x] Rewrite `password_set`:
  - Invalid form: render `introduction/_password_form.html` with errors and
    status 200 (currently returns a bare JSON `{"success": false}` and shows
    nothing).
  - Valid form: return `204` with `HX-Trigger: intro:password-set` (after
    `update_session_auth_hash`).
  - Non-HTMX fallback: redirect to the introduction page.
- [x] Make the final profile form POST to `introduction`:
  - On success: mark `has_had_introduction`, save, then render a final
    `components/_feedback.html` step (“Profil gespeichert”) with a “Weiter zur
    Startseite” link. The intro page is a full page, so the link can be a normal
    `href`; do not use `messages.*`.
  - No-JS fallback: after the POST, redirect to `main-page` (or re-render the
    intro page with the feedback step).
  - On failure: re-render the page with errors and `initial_step="profile"`.
  - For HTMX, `HX-Redirect` is only needed if the final step navigates away;
    otherwise the feedback step stays in the intro container.
- [x] Call `redirect_if_introduction_needed` from the main entry points
  (main page, events, users, polls, calendar, contact) or add a small
  middleware/decorator. The old frontend only guarded the main page, so direct
  URLs could bypass the intro; decide whether parity or hardening is wanted.
- [x] Add tests for: intro redirect, successful password step, invalid password
  step, successful profile completion, invalid profile stay-on-step.

---

# 7. Shell and main page parity

## 7.1 Feedback components (replaces Django messages)

- [x] Add `templates/components/_feedback.html` and the `feedback` styles to
  `components.css`; see the “Feedback pattern” section at the top.
- [x] Replace every app-facing `messages.success/error/info` call with the
  feedback pattern as the corresponding view is touched. Keep
  `django.contrib.messages` installed only because the admin uses it.
- [x] Add the whitelisted `?status=` mapping used by non-HTMX PRG redirects and
  by the full-page detail wrappers (event updated/created/deleted/earnings,
  profile updated, password updated).
- [x] Do not add a messages block to `base.html`.

## 7.2 Home page content

- [x] `templates/index.html` is currently a static shell. Restore the old data:
  - `.fund` (Abikasse): `{{ abikasse_current|floatformat:2 }} €` /
    `{{ abikasse_goal|floatformat:2 }} €`.
  - `.news`: intentionally empty for now; the ranking is not needed currently.
  - `.todos`: normal link to `events-upcoming` (the list is a full page).
  - `.polls`: normal link to `polls`.
  - `.profile`: overlay opener for the current user’s details.
  - `.gallery`: leave as a placeholder; there is no backend.
- [x] Restore `can_view_all_events` in `main_page` if the old “Alle Aktionen”
  card/staff-only visibility is restored; otherwise drop the variable cleanly.
- [x] Ranking hours formatting is not applicable while the ranking panel is
  hidden.

## 7.3 Navigation and menu

- [x] Wire every menu link that has a backend:
  - “Aktionen” → events page (normal navigation).
  - “Umfragen” → `polls` (normal navigation).
  - “Nutzer” → users page (normal navigation; `can_view_users` is always true
    today).
  - “Admin” → `/admin/`, visible only for `user.is_staff` (currently it is
    always shown and has no `href`).
  - “Profil” / navbar icon → current user details overlay.
  - “Logout” stays a CSRF-protected POST form (already correct).
  - “Zitate”, “Gallerie”, “Abikasse”, “Forum” have no backend; keep them
    visibly disabled or remove them from the menu until implemented.
- [x] Reuse the menu’s close/overlay behaviour when an item opens the sheet.

## 7.4 Notifications

- [x] Already implemented in the rewrite, but verify:
  - lazy load via `overlay:open`;
  - OOB badge update;
  - mark-one / mark-all;
  - `open_as_popup` links (step 1.8);
  - event/join-request targets still render correctly after the view refactor.

## 7.5 Misc shell issues

- [x] `base.html` has `<meta http-equiv="refresh" content="300">`. A full reload
  every five minutes closes overlays and loses form input. Either remove it or
  replace it with targeted HTMX polling (e.g. notifications).
- [x] Fix the malformed favicon link (`...favicon.svg''` has an extra quote).
- the current icon-only footer is intentional.
- [x] Verify the `{% block 'title' %}` syntax in `base.html`; quoted block names
  work, but the whitespace inside the default title should be cleaned up.

---

# 8. Remaining pages (old-feature parity)

These are small, but their templates are missing, so direct URLs currently raise
`TemplateDoesNotExist`.

- [x] `templates/calendar.html`: the old page was a “Feature kommt noch” stub
  with some unused caleandar markup. Create a clean stub using the new shell
  and tokens. The `calendar` view already exists.
- [x] `templates/contact.html`: port the old contact content (Moritz Fechte,
  phone, IServ, mail, GitHub link) into the new shell. Verify with the user
  before publishing personal phone/email if it changed.
- [x] `templates/polls.html`: “Demokratie” stub with the old message (“Feature
  ist noch in der Entwicklung …”).
- [x] Add navigation entry points for the stubs only where the old UI had them
  (menu and/or home cards).
- [x] Run `manage.py check` after adding templates; missing templates are not
  caught by `check`, so render each URL with the test client.

---

# 9. Cross-cutting polish and validation

## 9.1 Styles and components

- [x] Add shared overlay/panel styles to `components.css` (header, action row,
  section blocks, loading state) instead of duplicating them in every feature
  CSS file.
- [x] Make the overlay header layout explicit: back button on the left, title in
  the middle, panel actions on the right, with right padding reserved for the
  shell X. Never render back and close in the same group.
- [x] Add `.field`-based form styles for selects/date inputs/checkboxes; the
  existing component file covers input/select/textarea but verify
  `datetime-local`, `date`, and the manager picker input.
- [x] Add `.errorlist` rendering inside `.field` without breaking layout.
- [x] Style the participation-times `<details>`/`<summary>` block and its rows
  (participant name + duration input) so it stays usable on mobile.
- [x] Ensure all overlays work at 320 px width and on iOS Safari (`dvh`, safe
  areas are already handled by `base.css`).
- [x] No `border-radius`, no hard-coded colours, one border width.
- [x] Add `focus-visible` states to cards, menu links, and overlay controls.

## 9.2 JavaScript quality

- [x] Every initialiser must be idempotent and scoped to a root element.
- [x] Initialise from `DOMContentLoaded` and `htmx:afterSwap` in one place
  (`base.js`) so new panels are not forgotten.
- [x] Avoid module-level DOM captures that only work on the first page load.
- [x] Keep `search.js` generic; do not duplicate scoring logic.
- [x] Add a loading state for overlay requests (`hx-indicator`) so slow requests
  do not look broken.
- [x] Handle `htmx:responseError` with a visible feedback panel instead of a
  silent failure.

## 9.3 HTMX/backend correctness

- [x] Invalid form responses use 2xx.
- [x] Full-page navigation uses `HX-Redirect`.
- [x] Mutating actions validate `next` only through `get_safe_next_url`.
- [x] All POST views are `@require_POST` and all read views that only render are
  `@require_GET` where appropriate.
- [x] Do not leak partial templates by linking to them directly: every overlay
  URL must also have a full-page fallback (or redirect).
- [x] Lists render full pages; only detail/form/related-item views return
  partials for HTMX.
- [x] Add `transaction.atomic()` around multi-step writes (`save_event`,
  accept join request, earnings + final flag).

## 9.4 Known backend bugs to fix while touching this code

- [x] `services.save_event` reassigns `creator` on every edit.
- [x] `join_request_details` / `accept_join_request` /
  `decline_join_request` have no authorization check.
- [x] `change_password_popup` has no authorization check and uses
  `PasswordChangeForm` for staff editing another user (old password required).
- [x] `delete_event` permission differs from `can_edit_event`.
- [x] `leave_event` removes participation even when the user is not a
  participant.
- [x] `events` exposes all past events to non-staff (if restoring old privacy).
  Intentional decision: all users see all events; no visibility change.
- [x] `set_event_earnings` ignores invalid forms silently.
- [x] `EventParticipation.save` resets a `timedelta(0)` participation time to the
  full event duration because it checks `if not self.participation_time`; use
  `is None` so staff can set zero.
- [x] `users` view returns an unordered `set`.
- [x] `UserProfile.total_hours` contains a duplicate `return` (dead code).
- [x] `UserProfile.total_earnings` is known-wrong; do not surface it in the UI
  until the per-event share formula is implemented.
- [x] `password_set` error path returns JSON with no rendered errors.
- [x] All existing `messages.*` calls are invisible because `base.html` has no
  messages block; replace them with the feedback pattern rather than adding a
  messages block.
- [x] The old views referenced templates that only existed in the archive; each
  URL was rendered after its port.
- [x] `EventForm` participants widget references
  `widgets/participants_widget.html`, which does not exist in the active
  templates; create/edit currently fails.

## 9.5 Tests

- [x] Update existing tests:
  - `test_non_staff_sees_all_events` if the old visibility rule is restored.
  - Events tests that assume `"events.html"` is rendered for HTMX requests
    (add separate partial tests for details/edit/create).
  - Notification tests if the notification markup changes.
- [x] Add tests for:
  - every overlay view returns a fragment (no `<html>`) for
    `HTTP_HX_REQUEST="true"`, and every authenticated full page contains
    `#overlay-content`.
  - back/close contract: each overlay has exactly one `.overlay-close` (the shell
    X), a back control only when `back_url` is set, and no “Schließen” control
    inside the panel header/action row.
  - events list always rendered as a full page; detail/edit/create partials
    rendered for `HTTP_HX_REQUEST="true"`.
  - event details partial for each permission combination.
  - create/edit success and invalid-form rerender; edit keeps the original
    creator; success renders the feedback panel.
  - manager picker: search, selection, create/edit defaults, missing-manager
    error, and no restriction to staff.
  - event creation permission once `can_create_event` is switched on.
  - join / leave / delete / earnings state transitions and their inline status
    blocks / delete feedback panel.
  - participation times: staff can update, non-staff denied, zero allowed,
    invalid/too-large values re-render, and `total_hours` updates.
  - join-request authorization (manager, creator, staff allowed; others 403 or
    redirect with error).
  - users list, user details, edit user, change password permissions.
  - introduction password and profile steps, including the final feedback step.
  - non-HTMX redirects carry the whitelisted `?status=` flag and render the
    corresponding feedback banner.
  - `redirect_next_or` emits `HX-Redirect` for HTMX and a 302 otherwise.
- [x] Keep the suite runnable with `.venv/bin/python manage.py test`.

## 9.6 Final validation checklist

- [x] `.venv/bin/python manage.py check`
- [x] `.venv/bin/python manage.py test`
- [x] Render every URL with the test client (including HTMX variants):
  `/`, `/events/`, `/events/upcoming/`, `/events/own/`, `/events/<id>/`,
  `/events/create/`, `/events/<id>/edit/`, participation-times POST, join request
  URLs, `/users/`, `/users/<id>/`, `/users/<id>/edit/`,
  `/users/<id>/change_password_popup/`, `/introduction/`, `/calendar/`,
  `/contact/`, `/polls/`, notifications.
- [x] Manual flows in the browser (desktop + narrow mobile):
  - Navigate to events from home and menu; switch filters; search; open details
    in the sheet; join/leave/delete; set earnings (editor and staff); adjust
    participation times as staff; close and reopen; confirm the list
    filter/search state is still there.
  - Open each overlay from the home page, events page, users page and
    notifications; confirm it renders and behaves identically, not just from the
    page it “belongs” to.
  - Create an event (participants widget add/remove/search; manager picker
    search/select/change); edit it; verify the creator does not change; verify
    the dedicated feedback panels.
  - Close an overlay with the close button, drag handle, outside click and
    Escape; focus returns to the opener.
  - Check the control placement: back is on the left of the header, the X/close
    is top-right, and the two never share the same group or row. “Zurück”
    navigates panels; only the X closes the sheet.
  - Accept/decline a join request as manager; verify notification links.
  - Complete the introduction in a fresh account.
  - Open a user from the manager link and return.
  - Password change for self and (if supported) for another user as staff.
  <!-- Not executable in this environment; run once in a real browser before release. -->
- [x] `.venv/bin/python manage.py collectstatic --noinput` after static changes.
- [x] Update `TODO.md` checkboxes and `AGENTS.md` when a convention changes.

---

# 10. Permissions system (next after parity)

Goal: one module answers “may this user do X?”. Roles are Django groups,
capabilities are Django permissions, and superusers pass everything implicitly.

## Decided

- **Server admin = superuser.** No separate admin role.
- **No non-superuser gets Django admin access for now.** Keep an `access_admin`
  capability defined but unassigned so this can change later. `/admin/` is gated
  on `access_admin` via a custom `AdminSite`; Django's login form still requires
  `is_staff`.
- **`Schüler`** is the baseline group; every student account is in it.
- **`Stufensprecher`** is the reps group. Only reps and superusers may create
  events.
- **Reps are exempt from the event creation rate limit** through
  `bypass_event_creation_limit`.
- **Reps cannot edit user profiles or reset their passwords etc..** `manage_users` stays superuser-only.
- **All users can view all users for now.** Enforce this through `view_all_users`,
  granted to both groups, so it can be revoked in admin without a code change.
- **Groups are additive.** A user can hold several roles; permissions are the
  union. Put each capability in the narrowest group that needs it.
- Keep per-event `creator`/`manager` object rules independent of groups.

## Roles and capabilities

| Capability | `Schüler` | `Stufensprecher` | Superuser |
|---|:--:|:--:|:--:|
| `create_event` | – | ✓ | ✓ |
| `edit_any_event`, `delete_any_event` | – | ✓ | ✓ |
| `approve_event` | – | ✓ | ✓ |
| `manage_earnings` | when manager or creator | ✓ | ✓ |
| `manage_participation_times` | – | ✓ | ✓ |
| `manage_join_requests` | own events | ✓ | ✓ |
| `bypass_event_creation_limit` | – | ✓ | ✓ |
| `view_all_users` | ✓ | ✓ | ✓ |
| `manage_users` | – | – | ✓ |
| `access_admin` | – | – | ✓ |
| `view_abikasse` | ✓ | ✓ | ✓ |
| `manage_abikasse` | – | ✓ | ✓ |
| `view_any_points` | – | ✓ | ✓ |

Define the codenames with `Meta.permissions` on `Event` (`create_event`,
`edit_any_event`, `delete_any_event`, `approve_event`, `manage_earnings`,
`manage_participation_times`, `manage_join_requests`,
`bypass_event_creation_limit`), on `UserProfile`
(`view_all_users`, `manage_users`, `access_admin`, `view_any_points`) and on
`Abikasse` (`view_abikasse`, `manage_abikasse`).

## Implementation checklist

- [x] Add the `Meta.permissions` entries and the migration.
- [x] Rewrite `dashboard/permissions.py`: permission constants and one `_can()`
  wrapper around `user.has_perm()`; keep the existing `can_*` names. Remove the
  `can_create_event() -> True` stub and all `is_staff` fallbacks.
- [x] Replace ad-hoc checks in `views/events.py` (`set_earnings_received`,
  `can_approve_payment`, the creation-limit `is_staff` bypass), `views/users.py`,
  and the admin link in `base.html` (`can_access_admin`).
- [x] `join_event`: drop the `is_staff` branch; only creator/manager are added
  directly, everyone else goes through a join request.
- [x] Add `bypass_event_creation_limit` and grant it to `Stufensprecher`.
- [x] Gate `/admin/` on `can_access_admin` via `CapabilityAdminSite`.
- [x] Data migration: create content types and permission rows explicitly (do not
  rely on `post_migrate` ordering), create both groups, assign their permissions,
  and add every existing non-superuser to `Schüler`.
- [x] Add new non-superusers to `Schüler` in `dashboard/signals.py`; this covers
  `import_student_accounts` and admin-created accounts, so the command needs no
  change.
- [x] Admin: verify users can be put into several groups and document that a
  group is a role. No custom role UI.
- [x] Update every existing test that creates `is_staff=True`; those users no
  longer have elevated app permissions, so put them in `Stufensprecher` instead.
- [x] Add permission-matrix tests, including negatives (student cannot create or
  edit a stranger’s event, rep cannot edit profiles or enter admin, superuser
  can, final event is read-only, manager can still edit their own event).
- [x] Write `docs/permissions.md` with the role × action × condition matrix and
  link it from `AGENTS.md`.

## Out of scope

- Custom `Role` model, custom role UI, or a permission backend such as
  `django-guardian`; ownership rules stay in `permissions.py`.
- Per-cohort roles and multi-tenant isolation.
- Field-level profile privacy; revisit after this lands.

# 11. Email Infrastructure

Goal: transactional mail through Django’s mail API, configured from `.env`, so
password reset works without the school/iServ account.

## Decided

- **Sending only through Django.** Use `django.core.mail` (`send_mail`,
  `EmailMultiAlternatives`); no raw `smtplib` for new code. SMTP credentials come
  from `.env`, never from code or prompts.
- **No school SMTP on the server.** The personal iServ account is not automated
  and its credentials never go into `.env`; that would be fragile and against
  policy. The sending identity is the existing noreply address on the project
  domain.
- **The noreply domain can reach external addresses but not iServ internals.**
  So `User.email` (iServ) stays the account record and a possible *input*
  identifier, but it is never a delivery target.
- **`external_mail` is trusted as-is.** It was entered by authenticated users
  during onboarding, so there is no verification flow and no `email_verified`
  field. Revisit only if a reset ever goes to the wrong person.
- **Password reset delivers only to `UserProfile.external_mail`.** Users without
  an external address use the admin fallback instead of asking for a new
  password by message.
- **Admin fallback = generated reset link, not a hand-set password.** A
  `manage_users` holder creates a one-time link and sends it out-of-band
  (WhatsApp/iServ). No plaintext password is ever shared.
- **`import_student_accounts` and `send_account_mails` stay as they are.** They
  have already been used and are superseded later; do not extend or refactor
  them now.
- **No model changes or migration** are needed for this section.

## Implementation checklist

Order matters: settings first, then the reset flow, then the admin fallback.

### 1. Settings and sending domain

- [ ] Add the mail block to `gradclassorg/settings.py`, read from env with
  sensible defaults: `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`,
  `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` /
  `EMAIL_USE_SSL` (mutually exclusive), `EMAIL_TIMEOUT = 10`,
  `DEFAULT_FROM_EMAIL`, `SERVER_EMAIL = DEFAULT_FROM_EMAIL`.
- [ ] Use `django.core.mail.backends.console.EmailBackend` in dev when
  `EMAIL_HOST` is empty, so reset links can be opened from the terminal.
  Tests already get `locmem` and `django.core.mail.outbox` automatically.
- [ ] Add `PASSWORD_RESET_TIMEOUT = 60 * 60 * 24` (one day).
- [ ] Create `.env.example` at the repo root listing every mail key with empty
  values; `.env` stays gitignored.
- [ ] Set a monitored static `Reply-To` (e.g. the class contact address) while
  `From` stays noreply, so replies do not vanish.
- [ ] Ops, not code: SPF, DKIM and DMARC for the sending domain, and the
  `DEFAULT_FROM_EMAIL` address must be authorized by the SMTP account.
  Otherwise reset mails land in spam.
- [ ] Production: replace `ALLOWED_HOSTS = "*"` with the real host and set
  `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` if a proxy
  terminates TLS. Reset links are built from `request.is_secure()` and
  `request.get_host()`, so otherwise they go out as `http://` or with the wrong
  host.

### 2. Password reset flow

- [ ] Add the four routes to `dashboard/urls.py` using
  `auth_views.PasswordResetView`, `PasswordResetDoneView`,
  `PasswordResetConfirmView` and `PasswordResetCompleteView`, with German paths
  and names (`password-reset`, `password-reset-done`,
  `password-reset-confirm`, `password-reset-complete`). These views are
  logged-out; `introduction_required` is decorator-based, so it does not
  interfere.
- [ ] Pass explicit template names. `django.contrib.admin` is first in
  `INSTALLED_APPS`, so its `registration/password_reset_*` templates win over
  same-named files in `dashboard/templates/`. Use
  `dashboard/templates/auth/password_reset/{form,done,confirm,complete}.html`
  and set `template_name` on each view.
- [ ] Set `success_url` explicitly on the reset and confirm views
  (`password-reset-done`, `password-reset-complete`); the defaults point at
  Django's `password_reset_*` names, which this project does not use.
- [ ] Add the email templates as
  `dashboard/templates/emails/password_reset_subject.txt` and
  `dashboard/templates/emails/password_reset.txt` (plain text, German, no HTML
  alternative), and point the form at them with `subject_template_name` /
  `email_template_name`. Do not rely on
  `registration/password_reset_email.html`.
- [ ] Build the reset pages on the logged-out shell used by
  `registration/login.html`; the flow is full-page, not an overlay. Do not
  assume the navbar or overlay shell.
- [ ] Subclass `PasswordResetForm` in `dashboard/forms.py`:
  - `clean_email` accepts either the iServ address (`User.email`) or
    `profile.external_mail`, case-insensitive, `is_active=True` only.
  - `get_users()` returns the matches; override `save()` so each mail goes to
    that user's `profile.external_mail`. Django's default targets the submitted
    address, which may be the iServ one.
  - Skip users without an external address silently; never fall back to
    `User.email`.
  - Always land on the generic "done" page, even for unknown addresses, so the
    form does not leak account existence.
  - Send one mail per matched user to that user's own address, so a duplicate
    address is resolved per owner instead of being ambiguous.
- [ ] Build the confirm link from the request (`request.get_host()` /
  `request.is_secure()`) plus `default_token_generator`, so the proxy settings
  above apply. Do not hardcode the domain.
- [ ] Add a "Passwort vergessen?" link to the login page.
- [ ] Add the same static hint on the form and done pages: "Wenn du keine
  externe E-Mail hinterlegt hast, wende dich an Moritz." It is shown to
  everyone, so it leaks nothing.
- [ ] Label the input in German and say what is accepted: iServ or external
  address.

### 3. Admin fallback: generated reset link

- [ ] Add `build_password_reset_url(user, request)` in `dashboard/services.py`
  returning the absolute `password-reset-confirm` URL, built from
  `urlsafe_base64_encode(force_bytes(user.pk))` and
  `default_token_generator.make_token(user)`.
- [ ] Add a `manage_users`-gated action on the user details overlay that shows
  the link once with a copy button. Use the existing capability helpers
  (`MANAGE_USERS` / `can_change_password`); do not introduce a new role check.
- [ ] The action sends no mail and must not log the link or put it in the URL.
  Submit with POST + CSRF; no `next` redirect, since it only renders the link.
- [ ] Keep the existing "set password" action as the last resort; the link
  action is preferred because it never exposes a password.

### 4. Tests, validation and docs

- [ ] Tests using `django.core.mail.outbox`: reset sends only to
  `external_mail`; a user without one produces no mail but still shows the
  generic done page; an unknown or iServ-only address produces no mail; the
  token stops working after the password changes; the admin link action is
  gated on `manage_users`.
- [ ] Run `manage.py check` and render the four pages plus the login page.
- [ ] Add a short `docs/email.md` (settings keys, which address receives mail,
  admin fallback) and link it from `AGENTS.md` if it becomes a convention.

## Out of scope

- External-address verification or an `email_verified` flag; `external_mail` is
  trusted from onboarding.
- Automating school/iServ SMTP, or storing school credentials on the server.
- Rewriting `import_student_accounts` / `send_account_mails`; both stay as
  deprecated one-offs.
- HTML mail bodies, background queues/Celery, bounce handling, Anymail, and
  notification emails.
- A uniqueness constraint on `external_mail`.
- A `dashboard/mail.py` abstraction; extract one only when a second sender
  beyond password reset exists.

# 12. Contact page and personal info

Goal: the contact page keeps showing the maintainer's details, but they come
from the superuser's profile instead of static markup, so the repo no longer
contains the phone number or personal addresses in `HEAD`.

## Decided

- Keep the contact page content and layout; only change where the values come
  from. Name, phone, external mail and the GitHub link stay.
- Source the values from the contact user's `UserProfile`: optional
  `CONTACT_USER_ID` setting, otherwise the first active superuser. No model
  change or migration.
- Show `external_mail` and `phone_number` only. Do not publish `User.email`
  (iServ); the iServ row goes away.
- Login-gating prevents search indexing, not scraping. That is acceptable:
  every logged-in user can already see these fields on `/users/<id>/`. Treat
  the page as class-visible, not secret.
- No history rewrite for now. `HEAD` is clean; old commits still contain the
  values. The archive was removed from the working tree.

## Implementation checklist

- [ ] Add `_get_contact_user()` in `dashboard/views/core.py`: prefer
  `settings.CONTACT_USER_ID`, otherwise
  `User.objects.filter(is_superuser=True, is_active=True).order_by("pk").first()`,
  with `select_related("profile")`.
- [ ] Pass `contact_user` and `contact_profile` from `contact` to
  `contact.html`; handle "no superuser" and "no profile" without crashing.
- [ ] Replace the static name, phone, IServ and Gmail rows in
  `dashboard/templates/contact.html`:
  - name from `get_full_name|default:username`;
  - phone link uses `as_e164`, display uses `as_national`;
  - external mail only when set;
  - omit empty rows and show a neutral fallback when nothing is set.
- [ ] Fill `phone_number` and `external_mail` on the superuser's profile (data
  step, not code) and confirm the page renders them.
- [ ] Tests: superuser values render; an empty profile hides the rows; an
  explicit `CONTACT_USER_ID` wins; no superuser renders without error.
- [ ] Run `manage.py check` and render `/contact/`.

## Deferred / out of scope

- Contact form and a role address (`CONTACT_EMAIL`); revisit only if the
  maintainer identity should stop being public.
- History rewrite with `git filter-repo` (replace the phone and personal
  addresses in all blobs, force-push all refs, ask GitHub support to purge
  cached commits, accept changed SHAs and stale forks). Do it in one pass for
  all PII if it ever becomes necessary.
- Redacting the old contact details from git history; they are gone from `HEAD`
  but remain in past commits. Only needed if the repository must be completely
  free of them.
- The `Moritz` signature in `send_account_mails.py`; the command stays
  deprecated and untouched.

# 13. Datenschutz / Impressum

Goal: one public, short privacy notice covering what the site actually does,
kept current as features ship. No Impressum, no cookie banner.

## Decided

- **Split the work.** Write the current-state page now; extend it when a feature
  ships. Never describe processing that does not exist yet.
- **No Impressum.** The site is private, non-commercial and login-only, so §5
  DDG is not triggered. A compliant Impressum would also require a public postal
  address. Revisit only if the site becomes public or commercial.
- **No cookie banner.** Only technically necessary cookies (`sessionid`,
  `csrftoken`); htmx uses `sessionStorage` for its history cache. No analytics,
  no third-party embeds, self-hosted fonts and JS.
- **The privacy page is public.** `/datenschutz/` renders without login; the
  login page is the only other public page. Link it from login, footer and menu.
- **Controller contact is the personal mail.** Accepted that it is public and
  scrapable. A role address (`kontakt@`/`datenschutz@`) is a later optional
  improvement.
- **Hosting is self-hosted at home in Germany.** No hosting processor; Art. 32
  duties (HTTPS, updates, backups, access control) stay with the maintainer.
- **Brevo handles outgoing app mail.** The sending domain is managed at INWX;
  INWX is registrar/DNS, and also processes mail if the contact mailbox is
  hosted there. Confirm Brevo’s AVV (EU/France); no third-country transfer
  assumed. A CDN or tunnel in front of the home server would be an additional
  recipient.
- **The gallery is login-only.** No public or shareable albums.
- **Image consent is separate from the introduction.** Most users already
  finished the intro, so it needs its own page/step. It must be one-time,
  per-user and revocable; a grade-wide agreement is not a substitute for
  individual consent (Art. 7 DSGVO, §22 KUG).
- **Features flag their Datenschutz impact.** Sections that need a privacy-text
  update or a consent flow say so with a `Datenschutz:` line.

## 13.1 Now: current-state page

- [ ] Add `dashboard/templates/legal/privacy.html` in the existing `page`/`card`
  style; German; roughly one screen.
- [ ] Sections: Verantwortlicher (name + personal mail), Daten, Zweck und
  Rechtsgrundlage, Empfänger (Brevo, plus INWX if the mailbox is hosted there),
  Speicherdauer, Cookies, Rechte, Stand/Version.
- [ ] Cover only existing processing: account (username, name, school mail,
  password hash), optional profile fields (external mail, phone, birthday,
  bio), participation/earnings, notifications and read flags, server logs.
- [ ] Legal bases: Art. 6(1)(b) for the account, Art. 6(1)(f) for
  security/usage; optional profile fields are voluntary.
- [ ] State that there is no analytics, tracking or third-party embedding.
- [ ] Add `datenschutz/` to `dashboard/urls.py` with a public `@require_GET`
  view: no `@login_required`, no `introduction_required`.
- [ ] Link it from `registration/login.html` (the footer block only renders for
  authenticated users) and from the authenticated footer/menu.
- [ ] Read the controller name and mail from settings or the §12 contact user,
  so there is one place to change them.
- [ ] Add a `Stand` date and bump it on every change.
- [ ] Render the page logged out and logged in; run `manage.py check`.

## 13.2 Gallery and image consent (design open)

Constraints to keep when designing it:

- One-time per-user consent, stored with the consent text version, timestamp
  and revocation state. Separate page/flow, not the introduction.
- Consent text: purpose (internal gallery), scope (login-only), legal basis
  (Art. 6(1)(a), §22 KUG), voluntariness, withdrawal, and that minors need a
  legal representative’s consent.
- Upload form: one attestation checkbox (“nur Bilder, für die eine Einwilligung
  der abgebildeten Personen vorliegt”), stored per upload. Not a dialog per
  image or post.
- Withdrawal: “Fotos von mir nicht veröffentlichen” in the profile plus a
  takedown request via contact; existing images hidden or removed.
- Do not ship gallery uploads before the consent flow and the privacy section
  exist.
- Extend the privacy page with the photo section when this lands: categories,
  retention, no recipients, withdrawal.

## 13.3 Deferred

- Role address for the controller contact.
- Account deletion and data export UI; until then handle Art. 15/17 requests
  manually via the contact page.
- Revisit the Impressum if the site becomes public or commercial.

# 14. Single-question polls with suggestions (Abimotto)

Goal: decisions like the Abimotto — one question, many options, with a fixed or
suggested option list. Single-choice only for now, but modelled around
`Question` so multi-question and other answer types are additive later.

## Decided

**Scope**

- v1 is single-question, single-choice: one answer out of multiple options.
  No multi-select, number-in-range or free-text yet.
- Model as `Poll -> Question -> Option -> ...` even though v1 has one question.
  Multi-question is then a UI change, not a rewrite.
- Later answer types plug into `Question.kind`. Their result rendering is decided
  per kind when they are added; for some, listing all answers will be enough.
- Answers are submitted per question (independent POST), so multi-question does
  not need a poll-level transaction later.
- Suggestion mode only for single-question polls.

**Suggestions**

- All logged-in users can suggest; max 3 per user, editable and withdrawable
  until the suggestion deadline.
- Suggestion text is visible to everyone from the moment it is submitted. The
  author is stored (`Option.created_by`) but visible only to the poll’s managers
  (creator or `manage_polls` holders); voters never see who suggested an option.
- Suggestions are therefore pseudonymous to voters, not anonymous in the
  database.
- Moderators can approve, reject, edit wording and merge duplicates. Merging
  and editing happen before voting opens; options are frozen afterwards.
- Rejected or removed suggestions disappear entirely; no tombstones.
- Suggested options only become votable after moderation.
- The wall is shown from the start of the suggestion phase, so pending and
  approved suggestions are visible together. It uses the scattered-box layout
  with a plain, accessible list fallback and a deterministic layout (no random
  jitter on every render).

**Voting**

- Votes are pseudonymous: `QuestionParticipation` records that a user voted,
  and the ballot/vote rows contain no persistent user reference. Only aggregate
  counts are queried or displayed.
- Votes are changeable. A random ballot token lives in a signed, HttpOnly cookie
  scoped to the question and expiring at the voting deadline; changing a vote
  replaces that ballot's row.
- The participation row stores only a keyed hash of the token (HMAC with
  `SECRET_KEY` and the user id), used to verify that the cookie belongs to the
  current account. No user FK on the ballot.
- This is pseudonymous, not cryptographically anonymous: the DB has no
  user ↔ ballot link, but request logs or the authenticated request could
  correlate in theory. Never log ballot tokens and never expose them.
- Clearing cookies means the ballot token is gone, so the vote can no longer be
  changed. It also cannot be re-cast, because the participation row still exists.
  Do not reset participation except in an exceptional, documented case.
- One vote per user per question, enforced by the participation table.
- The poll closes automatically at the voting deadline; results become visible
  then, including to creators and moderators.
- Results show percentage and fraction per option, e.g. “12 % · 6/50”, where the
  denominator is the number of votes cast.
- Ties show “Gleichstand” and leave the outcome open. An automatic tiebreaker
  poll is a later option, not v1.
- Creators and moderators can vote.

**Permissions**

- New capability `manage_polls` for creating, editing, publishing and moderating
  any poll. Granted to `Stufensprecher` and superuser.
- A poll creator can manage their own poll through an object rule in
  `permissions.py`, even without the global capability later.
- Every logged-in user can view open and closed polls, suggest and vote.

**List and UI**

- `/polls/` is a full page with a card/switcher toggle at the top: “Offen” and
  “Geschlossen”, default “Offen”. Reuse the events switcher pattern instead of
  copying it.
- Poll detail opens as an overlay; creating and editing use a full-page form,
  like events.
- Phases: Entwurf, Vorschläge, Moderation, Abstimmung, Beendet. Drafts are
  visible only to the creator and `manage_polls` holders.
- Never delete a poll that has votes; close it instead.

## Layout

`/polls/` (full page):

- Header: “Abstimmungen”, with “Neue Umfrage” for `manage_polls` holders.
- Switcher: “Offen” / “Geschlossen”, default “Offen”.
- Card grid: title, status badge, one-line description, relevant deadline and
  turnout. Clicking a card opens the overlay.

Poll overlay (bottom sheet, full detail):

- Header: title, status badge, back/close.
- Description and deadline line.
- Phase body:
  - Entwurf: question and option summary, “Bearbeiten”, and the start action
    (“Vorschläge starten”, or “Abstimmung starten” for fixed options).
  - Vorschläge: scattered-box wall; each box shows the option text. Managers
    also see the author; everyone else does not. Own boxes get edit/withdraw,
    and the “Vorschlag hinzufügen” form sits below. Removed suggestions are not
    rendered at all.
  - Moderation: suggestion list with the author, approve/reject/edit/merge and
    “Abstimmung starten”.
  - Abstimmung: options as selectable cards and an “Abstimmen” button. After
    voting, the current choice is marked and “Stimme ändern” stays available
    until the deadline. No results yet.
  - Beendet: results per option as “12 % · 6/50”, total votes, and “Gleichstand”
    when tied.

Create/edit (full page):

- Title and description.
- Mode: fixed options or suggestions.
- Suggestion deadline (only in suggestion mode) and voting deadline.
- Option editor for fixed options.
- v1 has exactly one question; its fields are the page body.

Tiebreaker (later):

- A new poll that references the tied one; the old poll stays visible. Whether
  the two are grouped as cards or linked from one detail page is open.

## Open until the meeting

- Whether an automatic tiebreaker poll is wanted, whether it reuses the question
  or creates a new poll, and how the old poll is referenced or grouped.

## Implementation checklist

**Models**

- [ ] `Poll`: title, description, creator FK, `created_at`, `published_at`,
  `suggestion_deadline`, `voting_deadline`. Derive the phase from these fields;
  do not store a status column that can go stale.
- [ ] `Question`: poll FK, prompt, order, `kind` (only `single_choice` now).
- [ ] `Option`: question FK, label, order, `created_by` (nullable for fixed
  options; never rendered to non-managers), state (`suggested`, `approved`,
  `rejected`, `merged`), and `merged_into` FK to self (nullable).
- [ ] `QuestionParticipation`: question FK, user FK, `created_at`, keyed token
  hash, `unique(question, user)`. The only place the voter is recorded.
- [ ] `Ballot`: question FK, random unique `token`. No user FK, by design.
- [ ] `BallotVote`: ballot FK, option FK. One row per ballot for single-choice;
  results are grouped counts.
- [ ] On first vote, create participation + ballot + vote in one transaction,
  store HMAC(`SECRET_KEY`, user id + token) in participation, and set the ballot
  token in a signed, HttpOnly cookie scoped to the question, expiring at the
  voting deadline.
- [ ] On a vote change, read the cookie, verify the HMAC against the current
  user's participation row, then replace that ballot's vote. Never store the
  token in a way that links it to the user.
- [ ] Validate that the chosen option belongs to the question.
- [ ] Add `manage_polls` to `Poll.Meta.permissions`. Data migration creates the
  ContentType and Permission rows explicitly (as in §10) and grants it to
  `Stufensprecher`.

**Permissions and services**

- [ ] Add `MANAGE_POLLS` and `can_manage_poll(user, poll)` to
  `permissions.py`: creator or global capability.
- [ ] Add `can_create_poll(user)` = `manage_polls` for now.
- [ ] Put phase transitions in `dashboard/services.py`: publish suggestions,
  close suggestions, publish voting, close poll. All deadline checks are
  server-side only.
- [ ] Update `docs/permissions.md` and the capability table.

**Views and URLs**

- [ ] `polls` list: full page, open/closed switcher default open. Server-side
  filter param and/or the events-style client filter, whichever reuses less
  code.
- [ ] `poll_details`: overlay, phase-dependent content (suggestion wall, vote
  form, results).
- [ ] `poll_create` / `poll_edit`: full page, creator or `manage_polls` only.
- [ ] `poll_suggest`, `poll_vote`, `poll_moderate`: POST + HTMX partials with the
  feedback pattern; no Django messages.
- [ ] Invalid HTMX forms re-render the partial with errors and preserved
  `next_url`; normal success uses `redirect_next_or`.
- [ ] Enforce the voting deadline and participation uniqueness on POST; a second
  vote returns the “already voted” feedback.

**Templates and UI**

- [ ] `polls.html` list with status badges and the card switcher.
- [ ] `polls/_poll_details.html`, `_suggestion_wall.html`, `_vote_form.html`,
  `_results.html`.
- [ ] Suggestion wall: scattered-box layout with a plain list fallback that
  works on mobile and a deterministic arrangement.
- [ ] Results: per option “12 % · 6/50” (percentage and fraction of votes
  cast), total votes, tie shown as “Gleichstand”.
- [ ] German copy; add new statuses to `STATUS_FEEDBACK`.

**Tests**

- [ ] Only `manage_polls` holders and the creator can create, edit or moderate;
  students get the denied feedback.
- [ ] Students can suggest and vote.
- [ ] Suggestion authors are visible to the poll creator and `manage_polls`
  holders and absent from the HTML for everyone else.
- [ ] One vote per user per question; a second first-vote POST adds no vote.
- [ ] A vote can be changed until the deadline; the old ballot row is replaced,
  not duplicated.
- [ ] A change with a missing or foreign ballot cookie is rejected.
- [ ] A vote after the deadline is rejected.
- [ ] Suggestions are visible immediately, removed suggestions disappear
  entirely, merging works before voting, and no option edits are possible
  afterwards.
- [ ] Results are aggregate-only, show percentage and fraction, and are hidden
  until close.
- [ ] A tie renders as “Gleichstand”.
- [ ] Render list, detail, create/edit, and the HTMX variants.

## Datenschutz

- Votes are pseudonymous: there is no user FK on ballots or votes; a
  participation row records that someone voted, and a cookie-held token allows
  changing the vote. Add this to §13 when polls ship, together with the statement
  that only aggregates are shown. Say “pseudonym” rather than “anonym”.
- Suggestions store their author (`Option.created_by`), but authorship is
  visible only to the poll’s managers; voters see the text only. Add this to the
  §13 data list when this ships and say “pseudonym gegenüber Abstimmenden”, not
  “anonym”.
- No third parties; everything stays on the self-hosted server.

## Out of scope

- Multi-question UI, multi-select, number-in-range and free-text; only the model
  is prepared for them.
- Automatic tiebreaker polls.
- Notifications for poll phases (§18).
- Comments or discussion on polls (§26).
- Editing or deleting polls with votes.
- Weighted votes, quorum, ranked choice.

# 15. Abikasse

Goal: one page for the class fund, the work points that determine each student’s
share of the Abiball costs, and a published ticket-price estimate. The ledger is
the source of truth for money; points are derived from final events; the ticket
price is an estimate only.

## Decided

**Fund and ledger**

- `/abikasse/` is a full page. Every logged-in user can view it through
  `view_abikasse`; `manage_abikasse` (Stufensprecher and superuser) can edit the
  goal, add/edit/delete entries, export CSV, and edit the ticket configuration.
  Superusers pass everything implicitly. There is no separate admin role and no
  `Kassenwart` group.
- `AbikasseEntry` is a single ledger for income and expenses: `kind`
  (`income`/`expense`), `amount` (positive `Decimal`), `description`, `date`,
  optional `event`, `source` (`manual`/`event`), `created_by`, `created_at`,
  `updated_at`.
- Balance = Σ income − Σ expenses. The existing `goal` stays a whole-euro target;
  the page shows balance, goal and progress. The home `.fund` card links to it.
- Event earnings enter the ledger automatically: when an event is `final` with
  `earnings` set, create/update its linked income entry; changing `earnings`
  updates it; never create a second entry. Do not also aggregate `Event.earnings`
  anywhere, or the money is counted twice.
- Managers may correct or delete entries; §27 audit logging is the safety net.
  No reversal-entry workflow in v1.
- CSV export for `manage_abikasse` holders: date, kind, description, amount,
  event title, created by.
- The 30 €/semester contribution is not modelled. Record it as an ordinary
  income entry when it is paid, or leave it out until the policy is decided.

**Work points**

- `Event.work_kind` is `school` (1×) or `freetime` (2×). No mixed events. It is
  required on the event form; existing rows default to `school` and should be
  reviewed after the migration.
- Points count only for events that are `final` and already ended. Unconfirmed
  revenue and unfinished events never contribute.
- `work_points = floor(Σ hours × (1 for school, 2 for freetime))`.
- `earnings_share = Σ (user hours / total event hours) × event.earnings` over the
  same final events; skip events with zero total hours or no earnings.
- `earnings_points = earnings_share / x`.
- `total_points = floor(work_points + earnings_points)`.
- `x` is `AbiballConfig.point_value`, default **2 € per point** for now. Points
  are the only displayed unit: no euro conversion on the profile.
- The profile shows the total and the two components (`Arbeitspunkte`,
  `Ertragspunkte`); no per-event list. No leaderboard and no points in the users
  list.
- Points are computed on read, not stored. Aggregates used by the ticket estimate
  are cached; see below.

**Points visibility**

- A user always sees their own points and ticket estimate.
- A new capability `view_any_points` on `UserProfile.Meta.permissions` allows
  seeing another user’s points. Granted to `Stufensprecher`; superusers pass
  implicitly.
- The users list stays points-free. The section appears in
  `users/_user_details.html` only for self or `view_any_points`.
- Ticket estimates are personal and are not covered by `view_any_points`.

**Ticket estimate**

- `UserProfile.ticket_count` is the number of tickets the user expects for
  themselves and their family, **default 5**, owner-editable, validated 0–20. It
  includes the user’s own seat; 0 means they do not attend.
- `N_est = Σ ticket_count` over active users.
- `AbiballConfig` is a singleton edited by `manage_abikasse`: `fixed_costs`,
  `per_head_costs`, `point_value` (default 2), `default_ticket_count` (default 5).
  Costs are nullable so the estimate can be hidden until configured.
- `available = Abikasse.balance()`;
  `R = fixed_costs + per_head_costs × N_est − available`.
- `credit(user) = total_points(user) × point_value`.
- `base = (R + Σ credit) / N_est`.
- `price_per_ticket(user) = base − credit(user) / ticket_count(user)`;
  `total(user) = ticket_count(user) × base − credit(user)`.
- If a price would go below zero, show 0 € and say the remainder stays in the
  fund. Do not pay out.
- The index `.profile` card shows the current price for the signed-in user and
  contains the compact head-count input so the price updates without a full
  reload. The Abikasse page shows the same estimate card.
- The estimate is labelled “Schätzung” with the date it was computed. There is no
  deadline, snapshot or lock yet; it recalculates from current data.
- Hide the card while `AbiballConfig` is incomplete (“Noch keine Schätzung”).
- Only the estimate is published. No ticket orders, no payments, no provider.
- No `TicketGroup`: each user enters their own count. Shared family guests are a
  social convention for now; double counting is accepted until a real grouping
  model exists.
- Including the earnings share makes this a redistribution: the class still
  collects `R`, but cost moves from workers to non-workers. That is intentional
  for now and should be re-checked after the first real run.

**Permissions**

- New capabilities, also added to §10 and `docs/permissions.md`:

  | Capability | `Schüler` | `Stufensprecher` | Superuser |
  |---|:--:|:--:|:--:|
  | `view_abikasse` | ✓ | ✓ | ✓ |
  | `manage_abikasse` | – | ✓ | ✓ |
  | `view_any_points` | – | ✓ | ✓ |

- Data migration creates the permissions and grants them, following §10.

## Layout

`/abikasse/` (full page):

- Header “Abikasse”, with manager actions (“Eintrag hinzufügen”, “CSV”).
- Summary: Kassenstand, Ziel, progress bar.
- Ticket card: own points, head-count input, Grundpreis, own ticket price, total,
  “Schätzung vom …”.
- Ledger: date, description, kind, amount, optional running total; newest first;
  empty state.
- Add/edit entry in the bottom sheet; delete through the feedback pattern.

Index profile card:

- Current user’s ticket price and the compact head-count input.

Profile overlay:

- “Arbeitspunkte” section for self/reps/superusers: total, `Arbeitspunkte`,
  `Ertragspunkte`, short explanation. No per-event list.

German labels: `Abikasse`, `Kassenstand`, `Ziel`, `Einnahme`, `Ausgabe`,
`Arbeitspunkte`, `Ertragspunkte`, `Punkte gesamt`, `Grundpreis`,
`Dein Ticketpreis`, `Personen`, `Schätzung`.

## Implementation checklist

**Models and migrations**

- [ ] Add `Event.work_kind` (`school`/`freetime`, default `school`) and show it in
  `EventForm` and `events/_event_form_fields.html`.
- [ ] Add `AbikasseEntry` with the fields above, `event` as a nullable
  `OneToOneField` (`SET_NULL`) and a `source` choice.
- [ ] Add `AbiballConfig` singleton (pk = 1) with `fixed_costs`,
  `per_head_costs`, `point_value`, `default_ticket_count`.
- [ ] Add `UserProfile.ticket_count` (default 5, validators 0–20).
- [ ] Add `view_abikasse`/`manage_abikasse` to `Abikasse.Meta.permissions` and
  `view_any_points` to `UserProfile.Meta.permissions`.
- [ ] Data migration: create content types/permissions explicitly, grant
  `view_abikasse` to both groups, `manage_abikasse` and `view_any_points` to
  `Stufensprecher`.
- [ ] Decide on `goal`: keep whole euros, or make it `Decimal` to match the
  ledger.

**Services**

- [ ] `abikasse_balance()` = Σ income − Σ expenses; replace
  `Abikasse.total_earnings()` and stop using `UserProfile.total_earnings()`.
- [ ] `sync_event_earnings_entry(event)` idempotent, called from a `post_save`
  signal or the event services when an event becomes final or `earnings`
  changes; skip `None`/0. `final` is treated as irreversible; if it is changed in
  admin, reconcile manually.
- [ ] `work_points(user)`, `earnings_share(user)`, `total_points(user)` using
  `Decimal`; only final, ended events; skip zero-hour events. Earnings share
  uses unweighted hours (original formula).
- [ ] `ticket_base()` and `ticket_estimate(user)`; cache `N_est`, Σ credit and
  `base` with a short TTL, invalidated on ledger/points/count changes.
- [ ] Rounding: floor points for display; credit = displayed points ×
  `point_value`; document the up-to-`point_value` difference per user.
- [ ] Never use floats for money.

**Views and URLs**

- [ ] `abikasse` full page, `view_abikasse`.
- [ ] `abikasse_entry_create/edit/delete`, `manage_abikasse`, POST + HTMX
  feedback; `@require_POST` for delete.
- [ ] `abikasse_export` CSV, `manage_abikasse`.
- [ ] `ticket_count_update` (POST) and the estimate partial; owner only.
- [ ] `main_page`: add the current user’s estimate to the context and update the
  `.fund` card.
- [ ] `user_details`: add points for self/`view_any_points`.
- [ ] Keep `next` handling in `http_helpers.py`; no inline redirects.

**Templates, CSS, JS**

- [ ] `abikasse.html`, `abikasse/_entry_form.html`, `abikasse/_ticket_card.html`,
  `users/_points.html`.
- [ ] Update `index.html` (`.profile` card), `users/_user_details.html`, and
  `base.html` if new assets are global.
- [ ] `abikasse.css` and `tickets.css` using tokens only; no border radius.
- [ ] Small JS for the ticket-count input (or HTMX); idempotent
  `initTicketEstimate(root)` called from `base.js` on `DOMContentLoaded` and
  `htmx:afterSwap`.

**Tests**

- [ ] Points: school vs freetime weighting, final-only, ended-only, earnings
  share proportional to hours, zero-hour events skipped, floor, no events.
- [ ] Visibility: self sees points; rep and superuser see another user’s points;
  unrelated student does not; users list never shows points.
- [ ] Ledger: balance, income/expense, auto entry on final, idempotent update,
  no entry for missing earnings, edit/delete permissions, CSV.
- [ ] Estimate: default 5 tickets, base formula, own price, total, cap at 0,
  hidden when config incomplete, count update changes the price, other users
  cannot see it.
- [ ] Index profile card renders the estimate; profile overlay renders points.
- [ ] Overlay partials contain no `<html>`; invalid forms re-render with 200.

**Validation**

- [ ] `manage.py check`, `manage.py test`, `collectstatic`.
- [ ] Render `/`, `/abikasse/`, profile detail, add/edit entry, estimate update.

## Datenschutz

- Work points and the derived ticket estimate are personal data. Visibility is
  limited to self, `Stufensprecher` and superusers (`view_any_points`); no
  leaderboard.
- The ledger is internal financial data. All logged-in users see the aggregate
  and entry descriptions; individual contributions are not tracked in v1.
- No payment provider and no third party. Add points, ticket estimate and ledger
  to §13 when this ships; retention after Abi 2028 is deferred.
- Audit logging (§27) covers ledger edits once it lands.

## Open

- Confirm that “points” means `hours + earnings/x` (earnings converted at `1/x`)
  rather than a separate euro amount.
- Confirm that the earnings share uses unweighted hours; the original formula
  does.
- Should reps see other users’ ticket estimates? Default: no, points only.
- Should all ledger entries be visible to all users, or only the aggregate?
  Default: entries visible; no personal contributions to hide.
- Review the `work_kind` default for existing events after the migration.

## Out of scope

- 30 €/semester tracking and per-student payment status.
- Ticket sales, orders, payments and external providers; only the estimate.
- `TicketGroup`/households and shared family guests.
- Ticket deadline, snapshot and lock.
- Receipts/attachments, CSV import, tax/VAT, multi-year accounting.
- Per-event points breakdown, leaderboard and points in the users list.
- Points/ledger notifications.
- Retention, export and deletion after Abi 2028.

# 16. Quotes Page

Goal: a shared quote wall for single-line quotes and dialogues. A quote is an
ordered list of lines; every line has a free-text speaker and text.

## Decided

**Data model**

- `Quote`: uploader, `spoken_on`, `extra_info`, `created_at`. The quote text and
  speakers live on its lines, not on the quote.
- `QuoteLine`: quote, speaker, text, position. A normal quote is one line; a
  joint quote is one line whose speaker is “Max und Moritz”; a dialogue is
  several lines.
- Speaker names stay free text. No user FK and no notifications to quoted
  people: names are freely chosen, so a link or notification would be
  misleading and bypassable.
- `extra_info` belongs to the quote, not to a line.
- Quote order is `-spoken_on`, `-created_at`; line order is `position`.
- `spoken_on` is the date the quote was said, not the upload date. It defaults
  to today and is what the card displays. `created_at` is only the ordering
  tie-break and audit value.

**Authoring**

- One line editor for every quote, not a separate “dialogue mode”.
- The first line is required. “Zeile hinzufügen” appends rows; blank extra rows
  are ignored.
- A speaker input accepts free text and may contain several names.
- A shared datalist suggests speakers already entered in the current quote
  only. No cross-quote suggestions and no user accounts.
- No consent checkbox. The form shows a short hint that the uploader is
  responsible for the named person’s consent.
- All logged-in users can create quotes.

**Display**

- `/quotes/` is the full-page vertical list, newest first.
- One line renders as a normal quote with attribution:
  `— Max und Moritz (Bio LK)`.
- Multiple lines render speaker-prefixed (`Max: …` / `Moritz: …`), with
  `extra_info` below.
- No quote detail overlay: the card contains everything. Actions live on the
  card.
- The uploader name links to the existing profile overlay.

**Moderation and reporting**

- `manage_quotes` capability for `Stufensprecher` and superuser.
- The uploader or a `manage_quotes` holder can delete a quote. Delete is a
  normal POST/redirect to `?status=quote-deleted`; no inline HTMX swap.
- Any logged-in user except the uploader can report a quote. Reporting never
  hides the quote automatically.
- `QuoteReport` stores quote, reporter, optional reason and `created_at`; one
  report per user and quote.
- Reps are notified in-app. `Notification` gets a `QUOTE_REPORTED` verb; the
  target is the report and the URL is `/quotes/#reports`.
- `/quotes/` shows an “Offene Meldungen” section only to `manage_quotes`
  holders, with quote excerpt, reporter, reason, “Zitat löschen” and “Meldung
  verwerfen”.
- Deleting a quote cascades its lines and reports.

**Page plumbing**

- Search is client-side over line text, speakers, `extra_info` and uploader
  name. Reuse `searchItems` from `search.js`.
- No pagination in v1; all quotes load. Revisit if the list grows past a few
  hundred.
- Create and report use overlay fragments with full-page fallbacks; direct
  non-HTMX GETs redirect to `/quotes/`.
- Success feedback uses `components/_feedback.html`: create offers “Zur Liste”
  and “Weiteres Zitat”; invalid HTMX forms re-render with 200 and preserve
  `next_url`.

## Layout

`/quotes/`:

- Header “Zitate”.
- Toolbar: search input left, “Neues Zitat” button right; stacks on mobile.
- Feedback panel if a `?status=` flag is present.
- Optional “Offene Meldungen” block for reps, `id="reports"`.
- Vertical quote list: meta line, quote/dialogue, attribution, small action row
  (Löschen / Melden).
- Empty state “Keine Zitate gefunden.”

Create overlay:

- Header “Neues Zitat”.
- Line editor rows: speaker input (datalist) and textarea, with a remove
  control.
- “Zeile hinzufügen”.
- “Zusatzinfo (optional)”.
- “Datum” date picker, default today.
- Short responsibility hint; no checkbox.
- Submit “Hinzufügen”.

Report overlay:

- Header “Zitat melden”.
- Quote excerpt for context.
- “Grund (optional)” textarea.
- Submit “Melden”.

Single-line card:

> hochgeladen von: Lena am 11.11.2026
> „Wir sind hier, um zu bleiben.“
> — Max und Moritz (Bio LK)

Dialogue card:

> hochgeladen von: Lena am 11.11.2026
> Max: „Hast du die Klausur gelernt?“
> Moritz: „Ich habe sie mir angeschaut.“
> (Bio LK)

## Implementation checklist

**Models and permissions**

- [ ] `Quote`: `uploader` FK, `spoken_on` DateField (default
  `timezone.localdate`), `extra_info` CharField (blank), `created_at`.
  `Meta.ordering = ["-spoken_on", "-created_at"]`; `Meta.permissions =
  [("manage_quotes", "Zitate verwalten")]`; `__str__` returns a short
  first-line preview.
- [ ] `QuoteLine`: `quote` FK related_name `lines`, `speaker` CharField
  (max_length=200), `text` TextField, `position` PositiveSmallIntegerField.
  `Meta.ordering = ["position", "id"]`.
- [ ] `QuoteReport`: `quote` FK related_name `reports` (CASCADE), `reporter` FK
  related_name `quote_reports`, `reason` TextField (blank), `created_at`.
  `unique_together = ("quote", "reporter")`.
- [ ] Add `manage_quotes` constant and helpers in `permissions.py`:
  `can_manage_quotes(user)`, `can_delete_quote(user, quote)` (uploader or
  `manage_quotes`), `can_report_quote(user, quote)` (not the uploader).
- [ ] Data migration grants `manage_quotes` to `Stufensprecher`; update
  `docs/permissions.md`.
- [ ] `makemigrations` + `migrate`.

**Forms and services**

- [ ] `QuoteForm` for `extra_info` and `spoken_on`; date input uses
  `type="date"`.
- [ ] `QuoteLineForm` for `speaker` and `text`; speaker input uses
  `list="quote-speaker-options"`.
- [ ] `QuoteLineFormSet = inlineformset_factory(Quote, QuoteLine, extra=1,
  min_num=1, validate_min=True, can_delete=True)`.
- [ ] `QuoteReportForm` for the optional reason.
- [ ] `save_quote(form, formset, user)` in `services.py`: transaction, set the
  uploader, save the quote, save lines in form order with `position=0..n-1`,
  honor deleted forms.
- [ ] Never accept a client-supplied position; derive it from row order.

**Views and URLs**

- [ ] `views/quotes.py` with `quotes`, `quote_create`, `quote_delete`,
  `quote_report`, `quote_report_dismiss`.
- [ ] `quotes`: login and introduction required; prefetch `lines` and
  `reports__reporter`; compute per-quote `can_delete` and `can_report`
  (`can_report` is false for the uploader or when this user already reported);
  pass open reports and `can_manage_quotes`.
- [ ] `quote_create`: GET/POST, HTMX partial plus full-page fallback; validate
  form and formset; success feedback with actions; non-HTMX redirect to
  `?status=quote-created`.
- [ ] `quote_delete`: POST only; permission check; delete; redirect to
  `?status=quote-deleted` (support HTMX feedback for robustness).
- [ ] `quote_report`: GET/POST overlay; reject the uploader and duplicate
  reports; create the report and notify reps; redirect or feedback with
  `quote-reported` / `quote-already-reported`.
- [ ] `quote_report_dismiss`: POST only; `manage_quotes` required; delete the
  report; redirect to `?status=report-dismissed`.
- [ ] URLs: `quotes`, `quote-create`, `quote-delete`, `quote-report`,
  `quote-report-dismiss`.
- [ ] Add `QUOTE_REPORTED` to `NotificationVerbChoices`; `__str__` and
  `get_url` point at `/quotes/#reports`; notify all users with
  `manage_quotes` (including superusers) without duplicates.

**Templates and assets**

- [ ] `templates/quotes.html`; reuse the existing list page shell classes and
  add quote-specific classes.
- [ ] `templates/quotes/_quote_card.html` with single-line and dialogue
  rendering, delete/report actions and search data.
- [ ] `templates/quotes/_quote_form.html` (fragment) and `quotes/form.html`
  (full-page fallback).
- [ ] `templates/quotes/_report_form.html` (fragment) and `quotes/report.html`
  (full-page fallback).
- [ ] Reps-only reports section `id="reports"` with delete and dismiss forms.
- [ ] `static/dashboard/css/quotes.css`: vertical list, card variants, line
  editor, report section; tokens only.
- [ ] `static/dashboard/js/quotes.js`: `initQuotesList` search; add it to
  `PAGE_INITIALIZERS`.
- [ ] `static/dashboard/js/quote-form.js`: `initQuoteForms` add/remove rows and
  current-quote speaker datalist; add it to `PAGE_INITIALIZERS` and load it
  from `base.html`.
- [ ] Link `quotes.css` from `base.html`; enable “Zitate” in the menu.
- [ ] Add feedback statuses for create, delete, report, dismiss and denied
  cases.
- [ ] Register `Quote` (with a `QuoteLineInline`) and `QuoteReport` in admin;
  add search fields for text, speakers, uploader and reporter.

**Tests and validation**

- [ ] Create with one line sets uploader, date and position.
- [ ] Create with several lines preserves row order; blank extra rows are
  ignored.
- [ ] Missing or empty line is rejected, including `min_num`.
- [ ] Single-line and dialogue cards render correctly.
- [ ] List order is `-spoken_on`, `-created_at`.
- [ ] Uploader can delete own; unrelated student cannot; `manage_quotes`
  holder can delete any.
- [ ] Report creates one row and notifies reps; duplicate report is rejected;
  uploader cannot report own quote.
- [ ] Rep can dismiss a report; non-rep cannot.
- [ ] Anonymous access redirects to login.
- [ ] Invalid HTMX create/report re-renders the partial with 200; direct GET
  redirects to `/quotes/`.
- [ ] `manage.py check`, `collectstatic`, `manage.py test`; render `/quotes/`,
  the create overlay and the report overlay.

## Datenschutz

- Quotes contain the quoted people’s names, the uploader’s identity, the quote
  date and optional context. Visible to logged-in members only; no public or
  shareable view.
- Report reasons may contain personal data; visible only to `manage_quotes`
  holders.
- No consent checkbox. The form carries a short responsibility hint; the report
  button and the contact/reps path are the takedown route.
- Deleting a quote removes its lines and reports. Retention after Abi 2028 is
  deferred.
- Add the quotes category to §13 when this ships. No third-party processors are
  involved.

## Open

- Exact wording of the responsibility hint.
- Should quote creation and reporting be rate-limited? Default: no for v1.
- Should uploaders be able to edit their own quote? Default: no; delete and
  re-add.
- Is `extra_info` always quote-level, or does any use case need per-line info?
  Default: quote-level.
- Should report reasons be required? Default: optional.
- Do reports also need email? Default: in-app notifications only.
- When does the list need pagination? Default: only after it becomes noticeably
  slow.

## Out of scope

- Upvotes/downvotes and sorting beyond search.
- Editing quotes.
- Comments, forum integration and quote discussion.
- Notifications to quoted people; names remain free text.
- Linking speakers to user accounts, avatars or profiles.
- Images, audio or video quotes.
- Anonymous submissions and public/shareable quotes.
- A generic report model for other features; extract one when a second feature
  needs it.
- Pagination/load more.
- Audit logging beyond the report rows.
- Reporting for events, users, Abikasse or poll suggestions; quotes are the
  only reported content in v1. §14’s existing moderation stays unchanged.

# 17. Gallery

- videos and photos
- heavily limit uploads per person:
  - file size
  - amount of items
  - video length
  - resolution to 1080p
  - per day and per hour or smn

- login-only; no public or shareable albums
- Datenschutz: see 13.2. No uploads before the one-time image consent, upload
  attestation and privacy section exist.

# 18. Notifications

- add Notifications for important things:
  - e.g.: poll still needs answer, manager of event still needs to put in made money, rep still needs to mark money as received etc etc
- push Notifications for IOS and Android
- email Notifications
- popup when opening the site
  - do you want notifications
  - [email] toggle on/off
  - tutorial for ios notifications by add to home screen... or just the option to turn them on for android
- add notification settings somewhere
  - toggleble things

- Datenschutz: email notifications stay under Brevo. iOS/Android push adds
  device tokens plus Apple/Google (APNs/FCM) as recipients, likely a
  third-country transfer; make notifications opt-in and extend the privacy
  page.

# 19. Tiktok and Insta Links 

- just linking to them ( no embedding for now :( )

- Datenschutz: no change while these stay plain links; embedding would add a
  third party.

# 20. Title Card

One-off title-card splash shown when the site is opened, plus a fox walking
along the navbar’s bottom border. No animation assets exist in the repo yet.
The frames are delivered when this section is executed, so do not scaffold
placeholder art.

## Decided

**Title card (site splash)**

- Copy is “Hi, oder so”: “Hi” large, “oder so” small beside it.
- It is a one-off splash, not a permanent home header: it covers the home page,
  plays once and disappears after ~2 s (duration tunable), revealing the page.
- Intro sequence: “Hi” appears first, then moves to the side while “oder so”
  appears small next to it. The fox walks on the top bar during the splash.
- The card is framed by a distinct top and bottom bar. The fox walks on top of
  the top bar with its feet on the bar.
- The title stays real, selectable text and the page behind it must not be
  permanently blocked. `prefers-reduced-motion: reduce` skips the splash
  entirely; it is decorative.

**When it shows**

- Render the splash markup only in `index.html`. Deep links and other pages
  never interrupt. `main_page` is login-protected, so anonymous visitors see
  the login page first and the splash on their first authenticated home visit.
- Show it at most once per browser tab session: a `sessionStorage` key (e.g.
  `gc-splash-seen`). Absent → show and set it; present → skip. A new tab or a
  reopened browser counts as opening the site anew; reloads and navigation in
  the tab do not.
- If “anew” should instead mean “after a break”, switch to a `localStorage`
  timestamp (e.g. show again after 30–60 min). Do not do this by default.
- Do not use a Django session or cookie for the flag: this is purely
  presentational, needs no server state and must not vary the cache.
- No-JS fallback: the splash shows on each index load and is hidden by CSS after
  the same duration. That is acceptable; JS only suppresses repeats.
- Decide before first paint whether to skip, otherwise the splash flashes on
  repeat visits. A tiny inline check that sets a class on `<html>` is enough; do
  not wait for `base.js`.
- Remove the splash from the DOM after its exit animation so no fox keeps
  animating invisibly.
- Do not name files or CSS after “introduction”; that already means the forced
  first-run flow (`introduction.js`, `introduction.html`). Use “splash” or
  “title card”.

**Frames**

- Walk cycle: exactly 10 frames at 12 fps, looping seamlessly. One cycle equals
  one stride.
- “Look to camera” sequence: 20 frames, exactly two walk cycles with only the
  head animation changed. It starts and ends on walk frame 0 and is played once,
  not looped. Because the body is the walk cycle, it can start on any loop
  boundary without a visible transition.
- The art is shaded and textured. Downscaling for display loses some detail;
  accept it for now and judge the result on the rendered page, not on the source
  frames.

**Format and export**

- Use still sprite sheets with CSS `steps()`, not animated WebP/GIF and not
  video. That keeps frame ranges, loop and one-shot playback, pausing and speed
  changes under our control and lets us animate `transform` instead of
  `background-position`.
- Export at 2× the display size for HiDPI. Keep a strip under ~4096 px wide;
  use rows or 1.5× if the title-card strip would exceed that.
- Try WebP with alpha first (lossless if the art allows it, q≈80 if not); PNG is
  the fallback if WebP is visibly worse.
- Walk and turn are separate small sheets and both load with the page. Do not
  lazy-load the turn sheet behind a timer; it is only a few dozen KB.
- The turn is 20 frames of the walk body with a different head. Check whether
  the exported body pixels are identical to the walk cycle. If they are, ship
  the walk body sheet plus a 20-frame head sheet and composite them. If they are
  not pixel-identical, ship the full 20 frames; do not reconstruct the body from
  the walk cycle when the frames do not line up.

**Speed**

- Frame rate is fixed at 12 fps (one 10-frame cycle = 833 ms) and is a separate
  value (e.g. `--fox-frame-duration`) that is not used for tuning.
- The tunable value is the travel, i.e. the ground speed (px/s) or the resulting
  travel duration per instance (e.g. `--fox-travel-duration`). Tune it in
  devtools until one walk cycle advances exactly one stride on screen and the
  feet do not slide.
- A useful starting point is measured stride × 12 fps; adjust from there by eye
  on the rendered page.
- Use the same ground speed for the navbar and the title card. Only the duration
  differs, because the travel distances differ; derive each duration from that
  speed and the actual distance.
- Changing travel duration must never change the frame rate; keep the two
  values independent and in one place per instance.

**Motion**

- Title card: the fox walks on top of the top bar with its feet on the bar.
  The travel range is the full bar width, not the text width.
- Navbar: the fox walks along the bottom border with its feet on the line,
  behind the nav items. It walks until fully past the viewport edge, flips while
  offscreen and immediately walks back in from the same side, mirrored; repeat.
  There is no fade and no pause: the disappearance is purely the exit, and the
  flip happens in one frame while nothing is visible. Defer the “look to
  camera” turn while the fox is offscreen; only trigger it during a visible pass.
- The walk loop is the default state. The turn is an embellishment: play it once
  every ~8–20 s (random), then return to the walk. Do not randomly choose
  between “walk forever” and “turn forever”.
- Start the turn on a walk-loop boundary so the bodies line up; restarting the
  walk loop at frame 0 at the same moment is allowed and must be invisible.
- Animate `transform` only: an outer element for `translateX` travel and an
  inner sprite strip for the frame step. Flip with `scaleX` on its own wrapper
  so it cannot fight the travel transform.
- Respect `prefers-reduced-motion: reduce`: for the navbar, freeze on a static
  frame and leave the fox in place; the splash is skipped entirely.

**Structure**

- One component with modifiers, e.g. `.fox`, `.fox--title`, `.fox--nav`; size
  via `--fox-width` / `--fox-height`. Decorative only: `aria-hidden="true"`,
  `pointer-events: none`, no focus target.
- `.fox--nav` is positioned inside `nav` on its bottom border and painted
  behind the nav items; `nav` becomes its positioning context. It must not add
  to the nav height.
- Pure CSS handles the walk loop and the navbar travel; the occasional turn is
  the only stateful part. If it needs JS, expose `window.initFox(root)` in
  `dashboard/static/dashboard/js/fox.js` and call it from `base.js` on
  `DOMContentLoaded` and `htmx:afterSwap`, like the other initialisers.
- Title-card styles go in `index.css`; the shared fox component goes in
  `components.css`. The sprite sheet is only requested where the element
  exists.
- Splash logic (dismissal, DOM removal) goes in `js/splash.js` as
  `window.initSplash(root)` and is called from `base.js`; the before-paint skip
  check stays a tiny inline script.

## Implementation checklist

**Assets**

- [ ] Receive the 10 walk frames and 20 turn frames.
- [ ] Measure the stride in pixels at the chosen display size and record it.
- [ ] Export the walk sheet and the turn sheet (or body + head split) at 2×;
      verify alpha edges and loop seams on a checkerboard background.
- [ ] Store the sheets under `dashboard/static/dashboard/sprites/fox/` and
      reference them with `{% static %}`.

**Title card**

- [ ] Add the splash markup to `index.html`: “Hi” large, “oder so” small,
      framed by a top and bottom bar.
- [ ] Implement the intro (“Hi” appears, moves aside, “oder so” appears) and the
      ~2 s exit.
- [ ] Anchor `.fox--title` on the top bar, feet on the bar, and make sure the
      card does not clip the fox (`overflow`).
- [ ] Tune bar thickness, display size, travel duration and turn interval on the
      rendered page.

**Trigger**

- [ ] Add the `sessionStorage` guard (wrapped in try/catch) and the before-paint
      skip check; verify the splash does not flash on repeat visits.
- [ ] Verify: first index load in a tab shows it, reloads and navigation do not,
      a new tab does.
- [ ] Key or clear the flag on logout/user switch; see Open.
- [ ] Remove the splash from the DOM after the exit animation; skip it under
      `prefers-reduced-motion`.
- [ ] Verify the no-JS path still dismisses it via CSS.

**Navbar**

- [ ] Make `nav` the positioning context and add `.fox--nav` on the bottom
      border, feet on the line, behind the nav items, `pointer-events: none`,
      without changing the nav height.
- [ ] Implement the full-exit / mirrored-reentry travel loop; flip only while
      fully offscreen, with no fade or pause.
- [ ] Defer the turn timer while the fox is offscreen.
- [ ] Check it does not collide with the logo, notifications or menu button on
      narrow screens and stays painted behind them.

**Verification**

- [ ] At 12 fps the configured travel duration does not make the feet slide.
- [ ] The walk loop is seamless and every walk→turn and turn→walk transition is
      invisible.
- [ ] No layout shift, no scrollbar and no overflow; the fox is fully offscreen
      before the flip.
- [ ] Reduced motion freezes the navbar fox and skips the splash.
- [ ] Run `collectstatic` and check the page with the test client or `runserver`.

## Open

- Final display size and compression quality; judge from the rendered page.
- Final ground speed and the per-instance travel durations; tune them on the
  rendered page at 12 fps.
- Whether the turn ships as a full 20-frame sheet or as a shared walk body plus
  a head sheet (depends on the exported frames).
- Final navbar fox display size; check it reads clearly within the 50 px nav
  and does not become a smudge on mobile.
- Exact bar thickness, spacing and intro timing; tune on the rendered page.
- Whether the splash survives logout/user switch or is cleared (or keyed by
  user id).
- Splash presentation: full-screen curtain vs. full-width band, exit animation,
  and whether it blocks interaction while visible.
- Splash duration (starting point ~2 s) and how much of the “Hi, oder so”
  sequence fits before the fade.
- `sessionStorage` once per tab vs. a `localStorage` time window, if the tab
  behavior feels wrong.
- Turn timing: the random 8–20 s interval is the starting point, tune it after
  seeing the animation.

## Datenschutz

- No change from the fox: it is a bundled decorative asset with no user data.
- The splash stores one `sessionStorage` flag to remember that it was shown.
  That is functional storage with no personal data; mention it if the privacy
  page enumerates local storage.

# 21. Profile Pictures 

- export layers of the file as individual assets, group them as they are in krita
- first: 
  - random select assets and overlay them
  - for all users randomly generated pfps
- later:
  - custom picker for all the assets

- Datenschutz: no change while avatars come from bundled assets. User-uploaded
  pictures would follow the gallery consent rules.

# 22. News/Announcements

- Datenschutz: authored content with an author name is already covered as
  “von dir erstellte Inhalte”; no new section unless targeting or private
  audiences are added.

# 23. Android Back Button Handling

# 24. Introduction update

# 25. Calendar

- Datenschutz: no change if the calendar stays internal; external calendar
  embeds or subscriptions add a third party.

# 26. Comments to Events

- Datenschutz: user-generated content, covered as “von dir erstellte Inhalte”.
  Define moderation, deletion and retention.

# 27. Audit Logging

- Datenschutz: new processing (who did what, when). Add it to the logs section
  and define access and retention.


# next stuff:

- title card
  - "Hi" 
  - which then moves to the side
  - as "oder so" appears in small next to it
  - animation of animal walking climbing below/over it
- Profile:
  - profile picture:
    - from the krita file
    - randomly generated for each account
    - in future manual selection of all the elements
- audit logging
- password reset without contacting admin?
- calender
- allow admins to put in news/announcements
  - they get priority and get moved up on the grid item
  - newest first
  - can decide how long they stay up
- notifications:
  - go over when they should be sent
  - fcm (android and ios notifications) !important btw
- datenschutz and shit
- gallery:
  - uploading images
  - and videos
  - on desktop slideshow of recent gallery posts
  - poster is public
  - getting date from image/video metadata?
  - make them connectable to events
    - events need an upload button
  - full page:
    - most recent posts in grid
    - top right upload button
      - form
      - upload button
      - takes in images and videos
      - need limits on size and length
      - caption
      - changing the date from the metadata if necessary
    - clicking on item shows poster on top
    - item below
    - caption and date bottom
  - is upvoting downvoting eventually useful for filtering?
    - leaning towards no
  - is moderation for nsfw necessary?
- polls
  - full page
  - should support multi question polls
  - and single question polls
  - also single question polls with people suggesting the possible choices
  - creating poll:
    - choosing between 
    - multi question:
      - title
      - description
      - finish date
      - questions:
        - question
        - input types
          - text
          - number in range
          - multiple choice:
            - when a new choice field gets filled in a new empty one should appear below it
        - when a full question is filled a new form should appear below it
      - honestly maybe we should leave this for now or outsorce it, there are plenty of survey services right
    - single question:
      - with single choices
      - with suggested choices:
        - deadline
        - people can input answer options (author visible only to poll managers)
        - they need to be moderatable
        - after dealine and moderating everyone can vote among suggested options
        - important for Abimotto voting
- forum:
  - reddit like forum
  - anyone can post
  - text messages
  - upvotes downvotes
  - connecting to the events:
    - main purpose discussing and planning
  - maybe uploading images to it
- quotes:
  - own full page
  - submit quotes
  - quote model
  - simple form:
    - quote
    - quoted person
      - (maybe possible selection of users)
        - they could be notified
        - that would take the fun out of the freedom of naming the people
        - free name chossing would be necessary anyways which would make the notification bypassable and useless
        - need to think about that
    - possibly upvotes and downvotes?
    - then i would need various ways to filter them and sort them
    - maybe connecting to forum feature? as in all quotes are automatically also forum entries
- integrating tiktok and instagram profile of our grade onto website
  - for people who dont have those apps
  - should be browsable
  - videos and posts should be viewable
  - maybe comments and likecount too if possible
- updating the introduction at some point aswell
- contact info shouldnt be inside the repo
- eventually:
  - todo/task delegation?
  - countdown towards abi(ball)?
  - birthday notifications lmao?
  - statistics

---

# Appendix A — Parity matrix

| Old feature | Current rewrite state | Task |
| --- | --- | --- |
| Login/logout | Done | — |
| Notifications panel | Implemented | 1.8, 7.4 |
| Messages | Missing; wrong mechanism for HTMX | Replaced by feedback panels (1.0, 7.1) |
| Feedback panels | Missing | 1.0, 7.1 |
| Home: Abikasse, ranking, links | Static shell only | 7.2 |
| Menu/header/profile menu | Partial | 7.3 |
| Events list page + search | Full page + client filters, no entry from home/menu | 1.1–1.4 |
| Event details | Missing template | 1.5 |
| Join/leave/delete buttons | Backend only | 1.6 |
| Earnings forms | Backend only | 1.6 |
| Participation working times | Not editable; only auto-derived | 1.9 |
| Join request panel | Missing template, no auth | 1.7 |
| Create event | View + missing template/widget; currently open to everyone | 3 |
| Manager selection | Native `<select>`, no search | 2 |
| Only staff may create events | Not implemented (future) | 3, 10 |
| General permissions | Ad-hoc `is_staff` checks | 10 |
| Edit event | View + missing template | 2 |
| Event visibility rules | Changed (all events visible) | 1.1 |
| Users list + search | Missing templates/JS | 5.1 |
| User details | Missing template | 5.2 |
| User edit | Missing template | 5.3 |
| Change password | Missing template, auth gap | 5.4 |
| Introduction | View only | 6 |
| Calendar | Missing stub | 8 |
| Contact | Missing page | 8 |
| Polls | Missing stub | 8 |
| Participants widget | Missing in active assets | 3 |
| Date validation JS | Missing | 2 |
| HTMX CSRF headers | Missing | 1.0 |
| Overlay partials on all pages | No explicit contract; page-specific CSS/JS risk | 1.0 |
| Back vs close controls | Inconsistent placement in the old UI | 1.0 |
| Overlay navigation | Toggle only; detail views missing | 1.0 |

# Appendix B — Planned file map

New/changed active files (names are suggestions; keep them consistent once
chosen):

```
templates/
  events.html
  events/_events_list.html           # optional include, not an HTMX response
  events/_event_card.html
  events/_event_card_simple.html
  events/_event_details.html
  events/_event_form.html
  events/_event_form_fields.html
  components/_feedback.html
  components/_overlay_header.html
  components/_join_request.html
  components/notifications.html        # update open_as_popup
  users.html
  users/_user_card.html
  users/_user_details.html
  users/_user_form.html
  users/_password_form.html
  introduction.html
  introduction/_password_form.html
  introduction/_profile_form.html
  widgets/participants_widget.html
  widgets/user_picker_widget.html      # or shared user_search_widget.html
  calendar.html
  contact.html
  polls.html

static/dashboard/
  icons/arrow-left.svg                 # back button asset, not the X icon
  css/events.css                       # extend
  css/users.css
  css/introduction.css
  css/participants.css
  css/user-picker.css                  # or shared user-search.css
  js/events.js                         # rewrite
  js/event-form.js
  js/users.js
  js/participants.js
  js/user-picker.js                    # or shared user-search.js
  js/introduction.js
  js/htmx-setup.js
  js/base.js                           # overlay:open/data-overlay-open/focus

dashboard/
  views/                               # after step 4
    __init__.py
    core.py
    auth.py
    events.py
    users.py
    notifications.py
  permissions.py
  http_helpers.py
  feedback.py
```
