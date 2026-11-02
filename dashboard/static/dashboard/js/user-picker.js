// Shared single/multi user picker. Uses search.js -> searchItems(...).
function readUserOptions(results) {
  return Array.from(results.querySelectorAll("[data-user-id]")).map((node) => ({
    id: node.dataset.userId,
    label: node.dataset.userLabel || node.textContent.trim(),
    node,
  }));
}

function selectedUserIdSet(widget) {
  const container = widget.querySelector("[data-selected-list]");
  return new Set(
    Array.from(container.querySelectorAll("[data-user-id]")).map(
      (node) => node.dataset.userId
    )
  );
}

function createUserChip(widget, user) {
  const container = widget.querySelector("[data-selected-list]");
  const chip = document.createElement(
    container.tagName.toLowerCase() === "ul" ? "li" : "span"
  );
  chip.className = "user-search__chip";
  chip.dataset.userId = user.id;
  chip.dataset.userLabel = user.label;

  const label = document.createElement("span");
  label.textContent = user.label;

  chip.append(label);

  if (widget.dataset.multiple !== "true") return chip;

  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "user-search__remove";
  remove.dataset.removeUser = user.id;
  remove.setAttribute("aria-label", `${user.label} entfernen`);
  remove.textContent = "Entfernen";

  chip.append(remove);
  return chip;
}

function createUserHiddenInput(widget, userId) {
  const input = document.createElement("input");
  input.type = "hidden";
  input.name = widget.dataset.fieldName;
  input.value = userId;
  input.dataset.hiddenUser = userId;
  return input;
}

function updateUserEmptyState(widget) {
  if (widget.dataset.multiple !== "true") return;

  const container = widget.querySelector("[data-selected-list]");
  const empty = container.querySelector("[data-empty-selected]");
  const hasSelection = selectedUserIdSet(widget).size > 0;

  if (!hasSelection && !empty) {
    const placeholder = document.createElement("li");
    placeholder.className = "user-search__empty";
    placeholder.dataset.emptySelected = "true";
    placeholder.textContent = "keine Teilnehmer";
    container.appendChild(placeholder);
  }

  if (hasSelection && empty) empty.remove();
}

function initUserPicker(widget) {
  if (widget.dataset.userSearchInitialized === "true") return;

  const searchInput = widget.querySelector("[data-user-search]");
  const results = widget.querySelector("[data-user-results]");
  if (!searchInput || !results) return;

  widget.dataset.userSearchInitialized = "true";

  const multiple = widget.dataset.multiple === "true";
  const selectedList = widget.querySelector("[data-selected-list]");
  const hiddenInputs = widget.querySelector("[data-hidden-inputs]");
  const emptyMessage = widget.querySelector("[data-user-empty]");
  const allOptions = readUserOptions(results);

  let visibleOptions = [];
  let activeIndex = -1;

  function clearActive() {
    allOptions.forEach((option) => {
      option.node.classList.remove("is-active");
      option.node.setAttribute("aria-selected", "false");
    });
    searchInput.removeAttribute("aria-activedescendant");
  }

  function setActive(index) {
    clearActive();
    activeIndex = index;

    const option = visibleOptions[activeIndex];
    if (!option) return;

    option.node.classList.add("is-active");
    option.node.setAttribute("aria-selected", "true");
    searchInput.setAttribute("aria-activedescendant", option.node.id);
  }

  function openResults() {
    results.hidden = false;
    searchInput.setAttribute("aria-expanded", "true");
  }

  function closeResults() {
    results.hidden = true;
    searchInput.setAttribute("aria-expanded", "false");
    activeIndex = -1;
    clearActive();
  }

  function renderResults(query) {
    const chosen = multiple ? selectedUserIdSet(widget) : new Set();
    const matches = query
      ? searchItems(query, allOptions, (option) => [option.label])
      : [...allOptions].sort((a, b) => a.label.localeCompare(b.label, "de"));

    visibleOptions = matches.filter((option) => !chosen.has(option.id));

    allOptions.forEach((option) => {
      option.node.hidden = true;
    });
    visibleOptions.forEach((option) => {
      option.node.hidden = false;
      results.appendChild(option.node);
    });

    if (emptyMessage) emptyMessage.hidden = visibleOptions.length > 0;
    activeIndex = -1;
    clearActive();
  }

  function selectUser(user) {
    if (!user) return;

    if (multiple) {
      if (!selectedUserIdSet(widget).has(user.id)) {
        selectedList.appendChild(createUserChip(widget, user));
        hiddenInputs.appendChild(createUserHiddenInput(widget, user.id));
      }
    } else {
      selectedList.replaceChildren(createUserChip(widget, user));
      hiddenInputs.replaceChildren(createUserHiddenInput(widget, user.id));
    }

    searchInput.value = "";
    updateUserEmptyState(widget);
    renderResults("");

    if (multiple) {
      openResults();
    } else {
      closeResults();
    }
  }

  function removeUser(userId) {
    const selected = Array.from(
      selectedList.querySelectorAll("[data-user-id]")
    ).find((node) => node.dataset.userId === userId);
    if (!selected) return;

    selected.remove();

    if (multiple) {
      const hidden = Array.from(
        hiddenInputs.querySelectorAll("[data-hidden-user]")
      ).find((input) => input.value === userId);
      if (hidden) hidden.remove();
    } else {
      hiddenInputs.replaceChildren();
    }

    updateUserEmptyState(widget);
    renderResults(searchInput.value);
  }

  searchInput.addEventListener("focus", () => {
    renderResults(searchInput.value);
    openResults();
  });

  searchInput.addEventListener("input", () => {
    renderResults(searchInput.value);
    openResults();
  });

  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeResults();
      return;
    }

    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();

      if (results.hidden) {
        renderResults(searchInput.value);
        openResults();
      }

      if (visibleOptions.length === 0) return;

      const direction = event.key === "ArrowDown" ? 1 : -1;
      const nextIndex =
        activeIndex === -1
          ? direction === 1
            ? 0
            : visibleOptions.length - 1
          : (activeIndex + direction + visibleOptions.length) %
          visibleOptions.length;
      setActive(nextIndex);
      return;
    }

    if (event.key === "Enter" && !results.hidden && activeIndex >= 0) {
      event.preventDefault();
      selectUser(visibleOptions[activeIndex]);
    }

    if (event.key === "Tab") closeResults();
  });

  searchInput.addEventListener("blur", () => {
    window.setTimeout(() => {
      if (!widget.contains(document.activeElement)) closeResults();
    }, 100);
  });

  results.addEventListener("pointerdown", (event) => {
    if (event.target.closest("[data-user-id]")) event.preventDefault();
  });

  results.addEventListener("click", (event) => {
    const optionNode = event.target.closest("[data-user-id]");
    if (!optionNode) return;

    // Keep the document-level overlay dismiss handler from treating the click
    // as an outside click after the results list is re-rendered.
    event.preventDefault();
    event.stopPropagation();

    selectUser(
      allOptions.find((option) => option.id === optionNode.dataset.userId)
    );
  });

  widget.addEventListener("click", (event) => {
    const removeButton = event.target.closest("[data-remove-user]");
    if (!removeButton) return;

    // Removing the chip detaches the event target; stop propagation so the
    // document-level overlay dismiss handler does not close the sheet.
    event.preventDefault();
    event.stopPropagation();
    removeUser(removeButton.dataset.removeUser);
  });

  updateUserEmptyState(widget);
  renderResults("");
}

function initUserPickers(root = document) {
  if (root.matches?.("[data-user-search-widget]")) {
    initUserPicker(root);
  }

  root
    .querySelectorAll?.("[data-user-search-widget]")
    .forEach((widget) => initUserPicker(widget));
}

window.initUserPickers = initUserPickers;

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => initUserPickers());
} else {
  initUserPickers();
}

document.addEventListener("htmx:afterSwap", (event) => {
  initUserPickers(event.detail.target);
});
