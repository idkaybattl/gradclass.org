function getPopupById(id) {
  if (!id) {
    return null;
  }
  return document.getElementById(id);
}

function openPopupById(id) {
  const popup = getPopupById(id);
  if (!popup) {
    return;
  }
  popup.classList.add("popup--open");
}

function closePopup(popup) {
  if (!popup) {
    return;
  }
  popup.classList.remove("popup--open");
}

function closeAllPopups() {
  document
    .querySelectorAll("[data-popup].popup--open")
    .forEach((popup) => closePopup(popup));
}

document.addEventListener("click", (event) => {
  const openTrigger = event.target.closest("[data-popup-open]");
  if (openTrigger) {
    openPopupById(openTrigger.dataset.popupOpen);
    return;
  }

  const switchTrigger = event.target.closest("[data-popup-switch]");
  if (switchTrigger) {
    closePopup(switchTrigger.closest("[data-popup]"));
    openPopupById(switchTrigger.dataset.popupSwitch);
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
