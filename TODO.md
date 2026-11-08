# TODO — Frontend rewrite parity

Goal: bring the new frontend (`dashboard/templates/`, `dashboard/static/dashboard/`)
back to the feature set of the previous frontend (`dashboard/oldtemplates/`,
`dashboard/oldstatics/`, and the `main` branch views), then split `views.py` into
maintainable modules.

Ground rules from `AGENTS.md`:

- Do not edit `oldtemplates/` or `oldstatics/`; they are the reference only.
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
- [x] Port the old date validation from `oldstatics/js/events.js` to
  `static/dashboard/js/event-form.js`:
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
  `EventForm` points at `widgets/participants_widget.html`, but that file only
  exists under `oldtemplates/`. The create/edit form currently raises
  `TemplateDoesNotExist`.
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
- [x] Old `view` functions reference templates that only exist in
  `oldtemplates/`; after each step, render the URL and confirm.
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
  capability defined but unassigned so this can change later. `/admin/` still
  requires `is_staff`, because Django gates the admin site on that flag.
- **`Schüler:in`** is the baseline group; every student account is in it.
- **`Stufensprecher:in`** is the reps group. Only reps and superusers may create
  events.
- **Reps cannot edit user profiles or reset their passwords etc..** `manage_users` stays superuser-only.
- **All users can view all users for now.** Enforce this through `view_all_users`,
  granted to both groups, so it can be revoked in admin without a code change.
- **Groups are additive.** A user can hold several roles; permissions are the
  union. Put each capability in the narrowest group that needs it.
- Keep per-event `creator`/`manager` object rules independent of groups.

## Roles and capabilities

| Capability | `Schüler:in` | `Stufensprecher:in` | Superuser |
|---|:--:|:--:|:--:|
| `create_event` | – | ✓ | ✓ |
| `edit_any_event`, `delete_any_event` | – | ✓ | ✓ |
| `approve_event` | – | ✓ | ✓ |
| `manage_earnings` | when manager or creator | ✓ | ✓ |
| `manage_participation_times` | – | ✓ | ✓ |
| `manage_join_requests` | own events | ✓ | ✓ |
| `view_all_users` | ✓ | ✓ | ✓ |
| `manage_users` | – | – | ✓ |
| `access_admin` | – | – | ✓ |

Define the codenames with `Meta.permissions` on `Event` (`create_event`,
`edit_any_event`, `delete_any_event`, `approve_event`, `manage_earnings`,
`manage_participation_times`, `manage_join_requests`) and on `UserProfile`
(`view_all_users`, `manage_users`, `access_admin`).

## Implementation checklist

- [ ] Add the `Meta.permissions` entries and the migration.
- [ ] Rewrite `dashboard/permissions.py`: permission constants and one `_can()`
  wrapper around `user.has_perm()`; keep the existing `can_*` names. Remove the
  `can_create_event() -> True` stub and all `is_staff` fallbacks.
- [ ] Replace ad-hoc checks in `views/events.py` (`set_earnings_received`,
  `can_approve_payment`, the creation-limit `is_staff` bypass), `views/users.py`,
  and the admin link in `base.html` (`can_access_admin`).
- [ ] `join_event`: drop the `is_staff` branch; only creator/manager are added
  directly, everyone else goes through a join request.
- [ ] Data migration: create content types and permission rows explicitly (do not
  rely on `post_migrate` ordering), create both groups, assign their permissions,
  and add every existing non-superuser to `Schüler:in`.
- [ ] Add new non-superusers to `Schüler:in` in `dashboard/signals.py`; this covers
  `import_student_accounts` and admin-created accounts, so the command needs no
  change.
- [ ] Admin: verify users can be put into several groups and document that a
  group is a role. No custom role UI.
- [ ] Tests: replace `is_staff=True` fixtures with group membership; cover the
  matrix and negatives (student cannot create or edit a stranger’s event, rep
  cannot edit profiles or enter admin, superuser can, final event is read-only,
  manager can still edit their own event).
- [ ] Write `docs/permissions.md` with the role × action × condition matrix and
  link it from `AGENTS.md`.

## Out of scope

- Custom `Role` model, custom role UI, or a permission backend such as
  `django-guardian`; ownership rules stay in `permissions.py`.
- Per-cohort roles and multi-tenant isolation.
- Field-level profile privacy; revisit after this lands.

# 11. Email Infrastructure

## 11.1 General Email System

## 11.2 Password Reset via sending E-Mail

# 12. remove personal contact info from repo

# 13. (Datenschutz/Impressum)

# 14. Abikasse

# 15. Single Question Votings with Suggestions (Abimotto)
- keep the questions modular so that they can be reused in multiquestion polls
- single questions with different answer types:
  - number in range
  - multiselect
  - ...

# 16. Quotes Page

- vertical list of quotes newest to oldest
- searchbar on top
- on its right "neues Zitat" button
  - overlay
  - quote field
  - quoted person field
  - extra info field
  - date picker autofilled as today
  - submit button
- displayed quotes shown as:
  > hochgeladen von: [uploader] am [date]
  > "[quote]"
  > - [quoted person] ([extra infos])

# 17. Gallery

- videos and photos
- heavily limit uploads per person:
  - file size
  - amount of items
  - video length
  - resolution to 1080p
  - per day and per hour or smn

# 18. Notifications

- push Notifications for IOS and Android
- email Notifications
- popup when opening the site
  - do you want notifications
  - [email] toggle on/off
  - tutorial for ios notifications by add to home screen... or just the option to turn them on for android
- add notification settings somewhere
  - toggleble things

# 19. Tiktok and Insta Links 

- just linking to them ( no embedding for now :( )

# 20. Title Card

- with fox animation i have done :]

# 21. Profile Pictures 

- export layers of the file as individual assets, group them as they are in krita
- first: 
  - random select assets and overlay them
  - for all users randomly generated pfps
- later:
  - custom picker for all the assets

# 22. News/Announcements

# 23. Android Back Button Handling

# 24. Introduction update

# 25. Calendar

# 26. Comments to Events

# 27. Audit Logging


# next stuff:

- title card
  - "Hi" 
  - which then moves to the side
  - as "oder so" appears in small next to it
  - animation of animal walking climbing below/over it
- Abikasse:
  - its own page
  - editing of the goal value
  - adding to the current income:
    - possibly a model for additional income that gets a description and an amount
  - still needs deciding: should the base 30euro a semester be in the available money from the beginning or come in as the semesters go on and the money gets payed??
- Profile:
  - profile picture:
    - from the krita file
    - randomly generated for each account
    - in future manual selection of all the elements
  - calculation of current Abiball ticket price:
    - point system:
      - 1 point per school work hour
      - 2 points per freetime work hour
      - rounded down
      - 1 point x euro in personal income
        - x still needs to be voted on
        - personal income as in fraction of total workhours of all workers at event * event income accumulated over all participated events
    - sum of remaining costs + all points of all users in euro
    - then divide by amount of tickets
    - then subtract personal points in euro distributed over all tickets for them and family
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
        - people can input answer options (not anonymously)
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
