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

function sortSelectOptions(select) {
  const options = Array.from(select.options).sort((a, b) =>
    a.text.localeCompare(b.text, "de")
  );

  select.innerHTML = "";
  options.forEach((option) => select.add(option));
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

function updateAvailableState(widget) {
  const select = widget.querySelector("[data-user-select]");
  const addButton = widget.querySelector("[data-add-user]");
  const emptyMessage = widget.querySelector("[data-empty-available]");
  const hasAnyOptions = select.options.length > 0;

  emptyMessage.classList.toggle(
    "participants-widget__available-empty--hidden",
    hasAnyOptions
  );

  if (!hasAnyOptions) {
    select.disabled = true;
    addButton.disabled = true;
    return;
  }

  select.disabled = false;
}

function filterAvailableUsers(widget) {
  const searchInput = widget.querySelector("[data-user-search]");
  const select = widget.querySelector("[data-user-select]");
  const addButton = widget.querySelector("[data-add-user]");
  const term = searchInput.value.trim().toLowerCase();

  const visibleOptions = [];

  Array.from(select.options).forEach((option) => {
    const label = (option.dataset.userLabel || option.textContent).toLowerCase();
    const isVisible = label.includes(term);
    option.hidden = !isVisible;
    if (isVisible) {
      visibleOptions.push(option);
    }
  });

  if (visibleOptions.length > 0) {
    select.value = visibleOptions[0].value;
  } else {
    select.value = "";
  }

  addButton.disabled = visibleOptions.length === 0;
}

function addParticipant(widget) {
  const fieldName = widget.dataset.fieldName;
  const select = widget.querySelector("[data-user-select]");
  const selectedList = widget.querySelector("[data-selected-list]");
  const hiddenInputsContainer = widget.querySelector("[data-hidden-inputs]");

  const selectedOption = select.selectedOptions[0];
  if (!selectedOption || selectedOption.hidden) {
    return;
  }

  const userId = selectedOption.value;
  const userLabel = selectedOption.dataset.userLabel || selectedOption.textContent;

  const alreadySelected = Array.from(
    selectedList.querySelectorAll("[data-user-id]")
  ).some((item) => item.dataset.userId === userId);

  if (alreadySelected) {
    return;
  }

  selectedList.appendChild(createSelectedItem(userId, userLabel));
  hiddenInputsContainer.appendChild(createHiddenInput(fieldName, userId));
  selectedOption.remove();

  updateSelectedEmptyState(widget);
  updateAvailableState(widget);
  filterAvailableUsers(widget);
}

function removeParticipant(widget, userId) {
  const select = widget.querySelector("[data-user-select]");
  const selectedList = widget.querySelector("[data-selected-list]");
  const hiddenInputsContainer = widget.querySelector("[data-hidden-inputs]");

  const selectedItem = Array.from(selectedList.querySelectorAll("[data-user-id]")).find(
    (item) => item.dataset.userId === userId
  );

  if (!selectedItem) {
    return;
  }

  const userLabel =
    selectedItem.dataset.userLabel ||
    selectedItem.querySelector("span")?.textContent ||
    "";
  selectedItem.remove();

  const hiddenInput = Array.from(
    hiddenInputsContainer.querySelectorAll("[data-hidden-user]")
  ).find((input) => input.value === userId);
  if (hiddenInput) {
    hiddenInput.remove();
  }

  const option = document.createElement("option");
  option.value = userId;
  option.dataset.userLabel = userLabel;
  option.textContent = userLabel;
  select.add(option);
  sortSelectOptions(select);

  updateSelectedEmptyState(widget);
  updateAvailableState(widget);
  filterAvailableUsers(widget);
}

function initParticipantsWidget(widget) {
  if (widget.dataset.participantsWidgetInitialized === "true") {
    return;
  }

  const searchInput = widget.querySelector("[data-user-search]");
  const addButton = widget.querySelector("[data-add-user]");
  const select = widget.querySelector("[data-user-select]");

  if (!searchInput || !addButton || !select) {
    return;
  }

  widget.dataset.participantsWidgetInitialized = "true";

  addButton.addEventListener("click", () => addParticipant(widget));
  searchInput.addEventListener("input", () => filterAvailableUsers(widget));
  select.addEventListener("dblclick", () => addParticipant(widget));

  widget.addEventListener("click", (event) => {
    const removeButton = event.target.closest("[data-remove-user]");
    if (!removeButton) {
      return;
    }
    removeParticipant(widget, removeButton.dataset.removeUser);
  });

  sortSelectOptions(select);
  updateSelectedEmptyState(widget);
  updateAvailableState(widget);
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
