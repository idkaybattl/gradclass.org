function addOptionRow(list) {
  const template = list.querySelector("[data-option-template]");
  const items = list.querySelector(".option-list__items");
  if (!template || !items) return;

  const row = template.content.firstElementChild.cloneNode(true);
  items.append(row);
  row.querySelector("[data-option-input]")?.focus();
}

function initOptionList(list) {
  if (!list || list.dataset.optionListInitialized === "true") return;

  const items = list.querySelector(".option-list__items");
  const addButton = list.querySelector("[data-option-add]");
  if (!items || !addButton) return;

  list.dataset.optionListInitialized = "true";

  addButton.addEventListener("click", () => addOptionRow(list));

  items.addEventListener("click", (event) => {
    const remove = event.target.closest("[data-option-remove]");
    if (!remove) return;

    // The clicked button is removed below; stop the click here so the global
    // overlay-outside handler does not see a detached target and close the panel.
    event.preventDefault();
    event.stopPropagation();
    remove.closest("[data-option-row]")?.remove();
  });

  // Pointer dragging works for mouse and touch; the handle also supports the
  // arrow keys, so reordering does not depend on dragging.
  let dragging = null;

  items.addEventListener("pointerdown", (event) => {
    const handle = event.target.closest("[data-option-drag]");
    if (!handle) return;

    event.preventDefault();
    dragging = handle.closest("[data-option-row]");
    dragging?.classList.add("option-list__item--dragging");
    handle.setPointerCapture(event.pointerId);
  });

  items.addEventListener("pointermove", (event) => {
    if (!dragging) return;

    const target = document
      .elementFromPoint(event.clientX, event.clientY)
      ?.closest("[data-option-row]");
    if (!target || target === dragging || !items.contains(target)) return;

    const rect = target.getBoundingClientRect();
    const before = event.clientY < rect.top + rect.height / 2;
    items.insertBefore(dragging, before ? target : target.nextSibling);
  });

  const stopDragging = () => {
    dragging?.classList.remove("option-list__item--dragging");
    dragging = null;
  };
  items.addEventListener("pointerup", stopDragging);
  items.addEventListener("pointercancel", stopDragging);

  items.addEventListener("keydown", (event) => {
    const handle = event.target.closest("[data-option-drag]");
    if (!handle) return;
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;

    event.preventDefault();
    const row = handle.closest("[data-option-row]");
    if (!row) return;

    if (event.key === "ArrowUp") {
      row.previousElementSibling?.before(row);
    } else {
      row.nextElementSibling?.after(row);
    }
    handle.focus();
  });
}

function syncPollFormFields(form) {
  const mode = form.querySelector("select[name='mode']");
  const suggestionFields = form.querySelectorAll(
    "[data-poll-suggestion-field]",
  );
  const optionFields = form.querySelector("[data-poll-option-field]");
  const suggestions = mode?.value === "suggestions";

  suggestionFields.forEach((field) => {
    field.hidden = !suggestions;
  });
  if (optionFields) optionFields.hidden = suggestions;
}

function initPollForm(form) {
  if (form.dataset.pollFormInitialized === "true") return;
  form.dataset.pollFormInitialized = "true";

  const mode = form.querySelector("select[name='mode']");
  mode?.addEventListener("change", () => syncPollFormFields(form));

  form
    .querySelectorAll("[data-option-list]")
    .forEach((list) => initOptionList(list));

  syncPollFormFields(form);
}

function initPollForms(root = document) {
  if (root.matches?.("form[data-poll-form]")) initPollForm(root);
  root
    .querySelectorAll?.("form[data-poll-form]")
    .forEach((form) => initPollForm(form));
}

window.initPollForms = initPollForms;
