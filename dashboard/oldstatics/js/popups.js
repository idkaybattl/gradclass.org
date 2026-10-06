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

// TODO: make prettier
function showLoadingState(popup) {
  popup.innerHTML = '<div class="popup-content">loading...</div>';
}

function renderPopupContent(popup, content) {
  popup.innerHTML = content;
  const title = popup.querySelector("h2[id]");
  if (title) {
    popup.setAttribute("aria-labelledby", title.id);
  }
  htmx.process(popup);
  initEventForms(popup);
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

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") {
    return;
  }
  closeAllPopups();
});

document.addEventListener("DOMContentLoaded", () => {
  initEventForms();

  const initialPopupMarker = document.querySelector("[data-popup-initial]");
  if (!initialPopupMarker) {
    return;
  }
  openPopupById(initialPopupMarker.dataset.popupInitial);
});
