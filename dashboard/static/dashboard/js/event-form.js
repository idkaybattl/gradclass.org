function parseEventDateTimeLocal(value) {
  if (!value) return null;

  const [datePart, timePart] = value.split("T");
  if (!datePart || !timePart) return null;

  const [year, month, day] = datePart.split("-").map(Number);
  const [hours, minutes] = timePart.split(":").map(Number);
  const parts = [year, month, day, hours, minutes];

  if (parts.some((part) => Number.isNaN(part))) return null;

  return new Date(year, month - 1, day, hours, minutes, 0, 0);
}

function updateEventFormDateValidation(form) {
  const startInput = form.querySelector("input[name$='starting_date']");
  const endInput = form.querySelector("input[name$='ending_date']");
  if (!startInput || !endInput) return true;

  endInput.min = startInput.value;
  endInput.setCustomValidity("");

  const startDate = parseEventDateTimeLocal(startInput.value);
  const endDate = parseEventDateTimeLocal(endInput.value);

  if (startDate && endDate && endDate <= startDate) {
    endInput.setCustomValidity("Das Ende muss nach dem Beginn liegen.");
  }

  return form.checkValidity();
}

function initEventForm(form) {
  if (form.dataset.eventFormInitialized === "true") return;

  const startInput = form.querySelector("input[name$='starting_date']");
  const endInput = form.querySelector("input[name$='ending_date']");
  if (!startInput || !endInput) return;

  form.dataset.eventFormInitialized = "true";

  const update = () => updateEventFormDateValidation(form);
  startInput.addEventListener("input", update);
  startInput.addEventListener("change", update);
  endInput.addEventListener("input", update);
  endInput.addEventListener("change", update);

  update();
}

function initEventForms(root = document) {
  if (root.matches?.("form[data-event-form]")) {
    initEventForm(root);
  }

  root
    .querySelectorAll?.("form[data-event-form]")
    .forEach((form) => initEventForm(form));
}

window.initEventForms = initEventForms;
