// participants_widget.js
// Uses search.js -> searchItems(query, items, getFields)

function createSelectedItem(userId, userLabel) {
  const item = document.createElement("li");
  item.className = "participants-widget__selected-item";
  item.dataset.userId = userId;
  item.dataset.userLabel = userLabel;

  const label = document.createElement("span");
  label.textContent = userLabel;
  item.appendChild(label);

  const removeButton = document.createElement("button");
  removeButton.type = "button";
  removeButton.className = "participants-widget__remove";
  removeButton.dataset.removeUser = userId;
  removeButton.textContent = "Entfernen";
  item.appendChild(removeButton);

  return item;
}

function createHiddenInput(fieldName, userId) {
  const input = document.createElement("input");
  input.type = "hidden";
  input.name = fieldName;
  input.value = userId;
  input.dataset.hiddenUser = userId;
  return input;
}

function updateSelectedEmptyState(widget) {
  const selectedList = widget.querySelector("[data-selected-list]");
  const selectedItems = selectedList.querySelectorAll("[data-user-id]");
  const emptyItem = selectedList.querySelector("[data-empty-selected]");

  if (selectedItems.length === 0 && !emptyItem) {
    const placeholder = document.createElement("li");
    placeholder.className = "participants-widget__empty";
    placeholder.dataset.emptySelected = "true";
    placeholder.textContent = "keine Teilnehmer";
    selectedList.appendChild(placeholder);
  }

  if (selectedItems.length > 0 && emptyItem) {
    emptyItem.remove();
  }
}

function updateAvailableEmptyMessage(widget, visibleCount) {
  const emptyMessage = widget.querySelector("[data-empty-available]");
  const hasAny = visibleCount > 0;
  if (emptyMessage) {
    emptyMessage.classList.toggle(
      "participants-widget__available-empty--hidden",
      hasAny
    );
  }
}

function readInitialAvailableUsers(widget) {
  // read server-rendered available items into a plain-data array
  const container = widget.querySelector("[data-available-list]");
  if (!container) return [];

  // find direct child items that carry data-user-id (ignore template)
  const nodes = Array.from(container.querySelectorAll(".participants-widget__available-item[data-user-id]"));
  return nodes.map((el) => ({ id: el.dataset.userId, label: el.dataset.userLabel || el.querySelector('span')?.textContent.trim() || '' }));
}

function createAvailableNode(widget, user) {
  const container = widget.querySelector("[data-available-list]");
  const tpl = container.querySelector("#participant-available-tpl") || document.getElementById("participant-available-tpl");
  const node = tpl.content.firstElementChild.cloneNode(true);

  node.dataset.userId = user.id;
  node.dataset.userLabel = user.label;
  const span = node.querySelector("span");
  if (span) span.textContent = user.label;
  const addBtn = node.querySelector("[data-add-user]");
  if (addBtn) addBtn.dataset.userId = user.id;

  return node;
}

function renderAvailableList(widget, users) {
  const container = widget.querySelector("[data-available-list]");
  if (!container) return;

  // remove existing rendered items but keep the template element
  Array.from(container.children).forEach((child) => {
    if (child.tagName && child.tagName.toLowerCase() === "template") return;
    child.remove();
  });

  users.forEach((user) => container.appendChild(createAvailableNode(widget, user)));
  updateAvailableEmptyMessage(widget, users.length);
}

function filterAvailableUsers(widget) {
  const searchInput = widget.querySelector("[data-user-search]");
  const term = (searchInput && searchInput.value) ? searchInput.value.trim().toLowerCase() : "";

  const all = widget._allUserOptions || [];

  const visible = term
    ? searchItems(term, all, (option) => [option.label])
    : [...all].sort((a, b) => a.label.localeCompare(b.label, "de"));

  renderAvailableList(widget, visible);
}

function addParticipant(widget, userId) {
  const fieldName = widget.dataset.fieldName;
  const selectedList = widget.querySelector("[data-selected-list]");
  const hiddenInputsContainer = widget.querySelector("[data-hidden-inputs]");

  const all = widget._allUserOptions || [];
  const idx = all.findIndex((u) => u.id === userId);
  if (idx === -1) return;

  const user = all[idx];

  // prevent duplicates
  const alreadySelected = Array.from(
    selectedList.querySelectorAll("[data-user-id]")
  ).some((item) => item.dataset.userId === userId);

  if (alreadySelected) return;

  selectedList.appendChild(createSelectedItem(user.id, user.label));
  hiddenInputsContainer.appendChild(createHiddenInput(fieldName, user.id));

  // remove from available
  all.splice(idx, 1);
  widget._allUserOptions = all;

  updateSelectedEmptyState(widget);
  filterAvailableUsers(widget);
}

function removeParticipant(widget, userId) {
  const selectedList = widget.querySelector("[data-selected-list]");
  const hiddenInputsContainer = widget.querySelector("[data-hidden-inputs]");

  const selectedItem = Array.from(selectedList.querySelectorAll("[data-user-id]")).find(
    (item) => item.dataset.userId === userId
  );

  if (!selectedItem) return;

  const userLabel =
    selectedItem.dataset.userLabel || selectedItem.querySelector("span")?.textContent || "";
  selectedItem.remove();

  const hiddenInput = Array.from(
    hiddenInputsContainer.querySelectorAll("[data-hidden-user]")
  ).find((input) => input.value === userId);
  if (hiddenInput) hiddenInput.remove();

  // add user back to available data
  const all = widget._allUserOptions || [];
  all.push({ id: userId, label: userLabel });
  widget._allUserOptions = all;

  updateSelectedEmptyState(widget);
  filterAvailableUsers(widget);
}

function initParticipantsWidget(widget) {
  if (widget.dataset.participantsWidgetInitialized === "true") {
    return;
  }

  const searchInput = widget.querySelector("[data-user-search]");
  const container = widget.querySelector("[data-available-list]");

  if (!searchInput || !container) {
    return;
  }

  widget.dataset.participantsWidgetInitialized = "true";

  // Initialise all user options from server-rendered DOM into plain objects
  widget._allUserOptions = readInitialAvailableUsers(widget);

  // wire listeners
  searchInput.addEventListener("input", () => filterAvailableUsers(widget));

  // delegated click handler for add/remove
  widget.addEventListener("click", (event) => {
    const addBtn = event.target.closest("[data-add-user]");
    if (addBtn) {
      const id = addBtn.dataset.userId;
      if (id) addParticipant(widget, id);
      return;
    }

    const removeButton = event.target.closest("[data-remove-user]");
    if (removeButton) {
      removeParticipant(widget, removeButton.dataset.removeUser);
    }
  });

  // initial state updates
  updateSelectedEmptyState(widget);
  filterAvailableUsers(widget);
}

function initParticipantsWidgets(root = document) {
  root
    .querySelectorAll("[data-participants-widget]")
    .forEach((widget) => initParticipantsWidget(widget));
}

window.initParticipantsWidgets = initParticipantsWidgets;

document.addEventListener("DOMContentLoaded", () => {
  initParticipantsWidgets();
});

document.addEventListener("htmx:afterSwap", (event) => {
  initParticipantsWidgets(event.target);
});
