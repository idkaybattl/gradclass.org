function getPopupById(id) {
  if (!id) {
    return null;
  }
  return document.getElementById(id);
}

function openPopupById(id) {
  openPopup(getPopupById(id));
}

// also close all other popups
function openPopup(popup) {
  if (!popup) {
    return;
  }
  closeAllPopups(popup);
  if (typeof popup.showModal === "function" && !popup.open) {
    popup.showModal();
  }
  popup.classList.add("popup--open");
}

function closePopup(popup) {
  if (!popup) {
    return;
  }
  popup.classList.remove("popup--open");
  popup.removeAttribute("aria-labelledby");
  if (typeof popup.close === "function" && popup.open) {
    popup.close();
  }
}

function closeAllPopups(exceptPopup = null) {
  document
    .querySelectorAll("[data-popup].popup--open, dialog[data-popup][open]")
    .forEach((popup) => {
      if (popup !== exceptPopup) {
        closePopup(popup);
      }
    });
}

function showLoadingState(popup) {
  popup.innerHTML = '<div class="popup-content">loading...</div>';
}

function renderPopupContent(popup, content) {
  popup.innerHTML = content;
  const title = popup.querySelector("h2[id]");
  if (title) {
    popup.setAttribute("aria-labelledby", title.id);
  }
  initProjectForms(popup);
  window.initParticipantsWidgets?.(popup);
}

function getPopupUrl(url) {
  const popupUrl = new URL(url, window.location.href);
  if (!popupUrl.searchParams.has("next")) {
    popupUrl.searchParams.set(
      "next",
      window.location.pathname + window.location.search
    );
  }
  return popupUrl;
}

async function loadAndRenderPopupContent(popup, url) {
  showLoadingState(popup);

  try {
    const response = await fetch(getPopupUrl(url), {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    const content = await response.text();
    renderPopupContent(popup, content);
  } catch (err) {
    popup.innerHTML = "Failed to load content.";
    console.error(err);
  }
}

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

  const now = getNowRoundedToMinute();
  const nowString = formatDateTimeLocal(now);

  startInput.min = nowString;
  endInput.min = startInput.value || nowString;

  startInput.setCustomValidity("");
  endInput.setCustomValidity("");

  const startDate = parseDateTimeLocal(startInput.value);
  const endDate = parseDateTimeLocal(endInput.value);

  if (startDate && startDate <= now) {
    startInput.setCustomValidity("Der Beginn muss in der Zukunft liegen.");
  }

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

document.addEventListener("click", async (event) => {
  const openTrigger = event.target.closest("[data-popup-open]");
  if (openTrigger) {
    const popup = document.getElementById(openTrigger.dataset.popupOpen);
    openPopup(popup);

    // fetch data if necessary
    const url = openTrigger.dataset.popupUrl;
    if (url) {
      await loadAndRenderPopupContent(popup, url);
    }
    return;
  }

  const closeTrigger = event.target.closest("[data-popup-close]");
  if (closeTrigger) {
    closePopup(closeTrigger.closest("[data-popup]"));
    return;
  }

  if (event.target.matches("[data-popup]")) {
    closePopup(event.target);
  }
});

document.addEventListener("submit", async (event) => {
  const form = event.target.closest("form[data-project-form]");
  if (!form || event.defaultPrevented) {
    return;
  }

  event.preventDefault();
  await submitProjectForm(form);
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") {
    return;
  }
  closeAllPopups();
});

document.addEventListener("DOMContentLoaded", () => {
  initProjectForms();

  const initialPopupMarker = document.querySelector("[data-popup-initial]");
  if (!initialPopupMarker) {
    return;
  }
  openPopupById(initialPopupMarker.dataset.popupInitial);
});
