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

- [ ] `templates/calendar.html`: the old page was a “Feature kommt noch” stub
  with some unused caleandar markup. Create a clean stub using the new shell
  and tokens. The `calendar` view already exists.
- [ ] `templates/contact.html`: port the old contact content (Moritz Fechte,
  phone, IServ, mail, GitHub link) into the new shell. Verify with the user
  before publishing personal phone/email if it changed.
- [ ] `templates/polls.html`: “Demokratie” stub with the old message (“Feature
  ist noch in der Entwicklung …”).
- [ ] Add navigation entry points for the stubs only where the old UI had them
  (menu and/or home cards).
- [ ] Run `manage.py check` after adding templates; missing templates are not
  caught by `check`, so render each URL with the test client.

---

# 9. Cross-cutting polish and validation

## 9.1 Styles and components

- [ ] Add shared overlay/panel styles to `components.css` (header, action row,
  section blocks, loading state) instead of duplicating them in every feature
  CSS file.
- [ ] Make the overlay header layout explicit: back button on the left, title in
  the middle, panel actions on the right, with right padding reserved for the
  shell X. Never render back and close in the same group.
- [ ] Add `.field`-based form styles for selects/date inputs/checkboxes; the
  existing component file covers input/select/textarea but verify
  `datetime-local`, `date`, and the manager picker input.
- [ ] Add `.errorlist` rendering inside `.field` without breaking layout.
- [ ] Style the participation-times `<details>`/`<summary>` block and its rows
  (participant name + duration input) so it stays usable on mobile.
- [ ] Ensure all overlays work at 320 px width and on iOS Safari (`dvh`, safe
  areas are already handled by `base.css`).
- [ ] No `border-radius`, no hard-coded colours, one border width.
- [ ] Add `focus-visible` states to cards, menu links, and overlay controls.

## 9.2 JavaScript quality

- [ ] Every initialiser must be idempotent and scoped to a root element.
- [ ] Initialise from `DOMContentLoaded` and `htmx:afterSwap` in one place
  (`base.js`) so new panels are not forgotten.
- [ ] Avoid module-level DOM captures that only work on the first page load.
- [ ] Keep `search.js` generic; do not duplicate scoring logic.
- [ ] Add a loading state for overlay requests (`hx-indicator`) so slow requests
  do not look broken.
- [ ] Handle `htmx:responseError` with a visible feedback panel instead of a
  silent failure.

## 9.3 HTMX/backend correctness

- [ ] Invalid form responses use 2xx.
- [ ] Full-page navigation uses `HX-Redirect`.
- [ ] Mutating actions validate `next` only through `get_safe_next_url`.
- [ ] All POST views are `@require_POST` and all read views that only render are
  `@require_GET` where appropriate.
- [ ] Do not leak partial templates by linking to them directly: every overlay
  URL must also have a full-page fallback (or redirect).
- [ ] Lists render full pages; only detail/form/related-item views return
  partials for HTMX.
- [ ] Add `transaction.atomic()` around multi-step writes (`save_event`,
  accept join request, earnings + final flag).

## 9.4 Known backend bugs to fix while touching this code

- [ ] `services.save_event` reassigns `creator` on every edit.
- [ ] `join_request_details` / `accept_join_request` /
  `decline_join_request` have no authorization check.
- [ ] `change_password_popup` has no authorization check and uses
  `PasswordChangeForm` for staff editing another user (old password required).
- [ ] `delete_event` permission differs from `can_edit_event`.
- [ ] `leave_event` removes participation even when the user is not a
  participant.
- [ ] `events` exposes all past events to non-staff (if restoring old privacy).
- [ ] `set_event_earnings` ignores invalid forms silently.
- [ ] `EventParticipation.save` resets a `timedelta(0)` participation time to the
  full event duration because it checks `if not self.participation_time`; use
  `is None` so staff can set zero.
- [ ] `users` view returns an unordered `set`.
- [ ] `UserProfile.total_hours` contains a duplicate `return` (dead code).
- [ ] `UserProfile.total_earnings` is known-wrong; do not surface it in the UI
  until the per-event share formula is implemented.
- [ ] `password_set` error path returns JSON with no rendered errors.
- [ ] All existing `messages.*` calls are invisible because `base.html` has no
  messages block; replace them with the feedback pattern rather than adding a
  messages block.
- [ ] Old `view` functions reference templates that only exist in
  `oldtemplates/`; after each step, render the URL and confirm.
- [ ] `EventForm` participants widget references
  `widgets/participants_widget.html`, which does not exist in the active
  templates; create/edit currently fails.

## 9.5 Tests

- [ ] Update existing tests:
  - `test_non_staff_sees_all_events` if the old visibility rule is restored.
  - Events tests that assume `"events.html"` is rendered for HTMX requests
    (add separate partial tests for details/edit/create).
  - Notification tests if the notification markup changes.
- [ ] Add tests for:
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
- [ ] Keep the suite runnable with `.venv/bin/python manage.py test`.

## 9.6 Final validation checklist

- [ ] `.venv/bin/python manage.py check`
- [ ] `.venv/bin/python manage.py test`
- [ ] Render every URL with the test client (including HTMX variants):
  `/`, `/events/`, `/events/upcoming/`, `/events/own/`, `/events/<id>/`,
  `/events/create/`, `/events/<id>/edit/`, participation-times POST, join request
  URLs, `/users/`, `/users/<id>/`, `/users/<id>/edit/`,
  `/users/<id>/change_password_popup/`, `/introduction/`, `/calendar/`,
  `/contact/`, `/polls/`, notifications.
- [ ] Manual flows in the browser (desktop + narrow mobile):
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
- [ ] `.venv/bin/python manage.py collectstatic --noinput` after static changes.
- [ ] Update `TODO.md` checkboxes and `AGENTS.md` when a convention changes.

---

# 10. General permissions system (next after parity)

Goal: stop making every decision through `request.user.is_staff`. “Staff or not”
is too coarse for real classes: they will want several admins, a teacher/advisor,
event coordinators, ordinary students, and different visibility rules. The future
“only staff may create events” restriction is the first consumer of this system.

## Model

- [ ] Prefer Django’s built-in auth **groups + permissions** before adding a custom
  role table. Define domain capabilities as permission codenames (custom
  `Meta.permissions` on the relevant models where useful) and check them through
  one module.
- [ ] Keep `dashboard/permissions.py` as the **only** place that answers “may this
  user do X?”. Views and templates must not re-implement `is_staff` logic.
- [ ] Combine two kinds of rules in the helpers:
  - **Capability** (role/group permission): create events, approve events,
    manage earnings, manage users, view all users, edit any event, manage site
    config.
  - **Object relationship** (ownership): creator/manager may edit their own
    event; participants may leave; staff/coordinators may edit any event until
    it is final.
- [ ] Deny by default. Every new action gets a named `can_*` helper and a test.
  Views return 403 or the feedback/error pattern instead of silently redirecting.
- [ ] Templates receive booleans from the view (`can_edit`, `can_delete`,
  `can_create_event`, `can_view_users`, …). Do not call permission helpers from
  templates.

## Suggested capabilities and roles

- [ ] Capabilities, at minimum:
  - `create_event` (future staff-only restriction)
  - `edit_any_event`, `delete_any_event`
  - `approve_event` / finalise event
  - `manage_earnings` (set earnings, mark earnings received)
  - `manage_participation_times` (staff adjustment of individual working times)
  - `manage_join_requests`
  - `view_all_events` / `view_past_events`
  - `view_all_users`
  - `manage_users` (edit profiles, reset passwords)
  - `manage_site_config` (branding, legal pages, feature flags)
  - `moderate_gallery` (only if the gallery feature is added)
- [ ] Suggested groups:
  - **Site admin**: everything, including Django admin and site config.
  - **Staff/advisor**: approve events, manage earnings, view all users/events.
  - **Coordinator**: create/edit events, manage join requests, maybe manage
    earnings; not necessarily Django admin.
  - **Student**: create events only if enabled; join/leave; edit own events;
    view what the privacy policy allows.
- [ ] Keep the per-event `creator`/`manager` rules independent of groups; a
  student manager can still edit their event even if they cannot edit all events.
- [ ] Decide the visibility defaults explicitly: user directory, profile fields,
  past events, earnings. These are privacy decisions as much as permissions.

## Implementation steps

- [ ] Inventory every current authorization decision (`grep` for `is_staff`,
  `is_superuser`, `can_*`, `creator`, `manager`, `participants`) and map each to a
  capability or object rule.
- [ ] Add the `can_*` helpers and role groups in a data migration so existing
  deployments get sensible defaults.
- [ ] Replace `can_create_event`’s temporary `return True` with the real
  capability check; keep the same helper name so the view/button code does not
  change again.
- [ ] Replace the other ad-hoc checks in views one at a time; keep `is_staff` as
  an admin fallback during the transition, then remove the fallback.
- [ ] Add a small admin screen or document how to manage groups in Django admin;
  self-hosters need a non-code way to appoint admins/coordinators.
- [ ] Write a permission matrix in `docs/permissions.md` / `AGENTS.md`:
  role × action × object condition.
- [ ] Add tests for the matrix, including negative cases (student cannot edit a
  stranger’s event, coordinator cannot change site config, manager can edit own
  event, final event is read-only).
- [ ] Add audit logging for sensitive changes (earnings, finalisation, user
  profile/password changes, role changes).

## Deliberately out of scope for now

- Per-cohort roles and multi-tenant isolation (see the generalisation discussion;
  do not build until a single-tenant deployment is stable).
- A full custom role UI. Django groups + a documented matrix are enough first.
- Field-level permissions. Start with view/action-level rules and object
  ownership; add field-level visibility only if the privacy policy requires it.

This becomes the next major work item after the parity rewrite, before the
broader multi-class generalisation work (config, Docker, setup, i18n).

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
