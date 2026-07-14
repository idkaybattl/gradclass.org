

function pad2(value) {
  return String(value).padStart(2, "0");
}

function formatDateTimeLocal(date) {
  return (
    date.getFullYear() +
    "-" +
    pad2(date.getMonth() + 1) +
    "-" +
    pad2(date.getDate()) +
    "T" +
    pad2(date.getHours()) +
    ":" +
    pad2(date.getMinutes())
  );
}

function getNowRoundedToMinute() {
  const now = new Date();
  now.setSeconds(0, 0);
  return now;
}

function parseDateTimeLocal(value) {
  if (!value) {
    return null;
  }

  const [datePart, timePart] = value.split("T");
  if (!datePart || !timePart) {
    return null;
  }

  const [year, month, day] = datePart.split("-").map(Number);
  const [hours, minutes] = timePart.split(":").map(Number);

  if ([year, month, day, hours, minutes].some((number) => Number.isNaN(number))) {
    return null;
  }

  return new Date(year, month - 1, day, hours, minutes, 0, 0);
}

function updateProjectFormDateValidation(form) {
  const startInput = form.querySelector("input[name$='starting_date']");
  const endInput = form.querySelector("input[name$='ending_date']");

  if (!startInput || !endInput) {
    return true;
  }

  endInput.min = startInput.value;

  startInput.setCustomValidity("");
  endInput.setCustomValidity("");

  const startDate = parseDateTimeLocal(startInput.value);
  const endDate = parseDateTimeLocal(endInput.value);

  if (startDate && endDate && endDate <= startDate) {
    endInput.setCustomValidity("Das Ende muss nach dem Beginn liegen.");
  }

  return form.checkValidity();
}

function initProjectFormValidation(form) {
  if (form.dataset.projectFormInitialized === "true") {
    return;
  }

  const startInput = form.querySelector("input[name$='starting_date']");
  const endInput = form.querySelector("input[name$='ending_date']");
  if (!startInput || !endInput) {
    return;
  }

  form.dataset.projectFormInitialized = "true";

  const update = () => updateProjectFormDateValidation(form);
  startInput.addEventListener("input", update);
  startInput.addEventListener("change", update);
  endInput.addEventListener("input", update);
  endInput.addEventListener("change", update);

  form.addEventListener("submit", (event) => {
    const isValid = updateProjectFormDateValidation(form);
    if (!isValid) {
      event.preventDefault();
      form.reportValidity();
    }
  });

  update();
}

function initProjectForms(root = document) {
  root
    .querySelectorAll("form[data-project-form]")
    .forEach((form) => initProjectFormValidation(form));
}

async function submitProjectForm(form) {
  const response = await fetch(form.action, {
    method: "POST",
    body: new FormData(form),
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });

  if (response.redirected) {
    window.location.assign(response.url);
    return;
  }

  const popup = form.closest("[data-popup]");
  if (popup) {
    renderPopupContent(popup, await response.text());
  }
}

document.addEventListener("submit", async (event) => {
  const form = event.target.closest("form[data-project-form]");
  if (!form || event.defaultPrevented) {
    return;
  }

  event.preventDefault();
  await submitProjectForm(form);
});
