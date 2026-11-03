const overlays = Array.from(document.querySelectorAll(".overlay"));
const defaultOverlay = document.querySelector(".overlay--sheet");

// Only one overlay may be open at a time.
let activeOverlay = null;

// A dragged handle closes its overlay after moving this share of its size.
const CLOSE_THRESHOLD = 1 / 4;

// Each overlay picks how its handle dismisses it via data-dismiss.
const DISMISS_DIRECTIONS = {
  down: { axis: "y", sign: 1 },
  up: { axis: "y", sign: -1 },
  right: { axis: "x", sign: 1 },
};

function setTriggersExpanded(overlay, expanded) {
  document
    .querySelectorAll(`[data-overlay-toggle="${overlay.id}"]`)
    .forEach((trigger) => trigger.setAttribute("aria-expanded", String(expanded)));
}

function focusOverlayPanel(overlay) {
  const target =
    overlay.querySelector("[data-overlay-title]") ??
    overlay.querySelector(".overlay-close");
  if (target instanceof HTMLElement) target.focus({ preventScroll: true });
}

function getReturnFocus(opener) {
  if (opener instanceof HTMLElement) return opener;
  if (activeOverlay?._returnFocus instanceof HTMLElement) {
    return activeOverlay._returnFocus;
  }
  return document.activeElement instanceof HTMLElement
    ? document.activeElement
    : null;
}

function openOverlayElement(overlay, markup, opener) {
  if (!overlay) return;

  // Keep the first opener around while navigating between panels in the sheet.
  if (!overlay.classList.contains("open")) {
    overlay._returnFocus = getReturnFocus(opener);
  }

  // Opening a second overlay closes the first one.
  if (activeOverlay && activeOverlay !== overlay) {
    closeOverlayElement(activeOverlay, { restoreFocus: false });
  }

  const content = overlay.querySelector(".overlay-content");
  if (markup !== undefined && content) content.innerHTML = markup;
  if (content) content.scrollTop = 0;

  overlay.classList.remove("dragging");
  overlay.style.transform = "";
  overlay.classList.add("open");
  activeOverlay = overlay;

  setTriggersExpanded(overlay, true);
  overlay.dispatchEvent(new CustomEvent("overlay:open", { bubbles: true }));
  focusOverlayPanel(overlay);
}

function closeOverlayElement(overlay, { restoreFocus = true } = {}) {
  if (!overlay) return;

  const returnFocus = overlay._returnFocus;
  overlay.classList.remove("open", "dragging");
  overlay.style.transform = "";

  if (activeOverlay === overlay) activeOverlay = null;
  setTriggersExpanded(overlay, false);
  overlay._returnFocus = null;

  if (
    restoreFocus &&
    returnFocus instanceof HTMLElement &&
    document.contains(returnFocus)
  ) {
    returnFocus.focus({ preventScroll: true });
  }
}

// Kept for callers of the original single-overlay API.
function openOverlay(markup) {
  openOverlayElement(defaultOverlay, markup);
}

function closeOverlay() {
  closeOverlayElement(activeOverlay);
}

// Closing a toggle happens in the capture phase so the element's htmx trigger
// does not refetch the panel that is being closed (e.g. the profile button).
document.addEventListener(
  "click",
  (event) => {
    const element = event.target instanceof Element ? event.target : null;
    if (!element) return;

    const toggle = element.closest("[data-overlay-toggle]");
    if (!toggle) return;

    const overlay = document.getElementById(toggle.dataset.overlayToggle);
    if (overlay && overlay === activeOverlay) {
      closeOverlayElement(overlay);
      event.preventDefault();
      event.stopPropagation();
    }
  },
  true,
);

document.addEventListener("click", (event) => {
  const element = event.target instanceof Element ? event.target : null;
  if (!element) return;

  const closeButton = element.closest(".overlay-close");
  if (closeButton) {
    closeOverlayElement(closeButton.closest(".overlay"));
    return;
  }

  const trigger = element.closest("[data-overlay-open]");
  if (trigger) {
    const overlay = document.getElementById(trigger.dataset.overlayOpen);
    if (overlay) {
      openOverlayElement(overlay, undefined, trigger);
      return;
    }
  }

  const toggle = element.closest("[data-overlay-toggle]");
  if (toggle) {
    const overlay = document.getElementById(toggle.dataset.overlayToggle);
    if (overlay === activeOverlay) closeOverlayElement(overlay);
    else openOverlayElement(overlay, undefined, toggle);
    return;
  }

  // Clicking anywhere outside the open overlay closes it.
  if (activeOverlay && !activeOverlay.contains(element)) {
    closeOverlayElement(activeOverlay);
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeOverlayElement(activeOverlay);
});

// A swapped panel starts at the top and focuses its heading.
document.addEventListener("htmx:afterSwap", (event) => {
  const target = event.detail.target;
  if (!(target instanceof Element)) return;

  const content = target.closest(".overlay-content");
  if (!content) return;

  content.scrollTop = 0;
  const heading = content.querySelector("[data-overlay-title]");
  if (heading instanceof HTMLElement) heading.focus({ preventScroll: true });
});

/* Drag to dismiss */

let drag = null;

function startDrag(event, handle, overlay) {
  if (event.button || !overlay.classList.contains("open")) return;

  drag = {
    overlay,
    startX: event.clientX,
    startY: event.clientY,
    dismiss: DISMISS_DIRECTIONS[overlay.dataset.dismiss] ?? DISMISS_DIRECTIONS.down,
  };

  overlay.classList.add("dragging");
  handle.setPointerCapture(event.pointerId);
}

// Distance the pointer has moved in the dismiss direction, never negative.
function getDragDistance(event, dragState) {
  const { dismiss, startX, startY } = dragState;
  const moved = dismiss.axis === "x" ? event.clientX - startX : event.clientY - startY;
  return Math.max(0, moved * dismiss.sign);
}

function endDrag() {
  if (!drag) return;

  drag.overlay.classList.remove("dragging");
  drag.overlay.style.transform = "";
  drag = null;
}

overlays.forEach((overlay) => {
  const handle = overlay.querySelector(".overlay-handle");
  if (handle) {
    handle.addEventListener("pointerdown", (event) => startDrag(event, handle, overlay));
  }
});

window.addEventListener("pointermove", (event) => {
  if (!drag) return;

  const offset = getDragDistance(event, drag) * drag.dismiss.sign;
  drag.overlay.style.transform =
    drag.dismiss.axis === "x" ? `translateX(${offset}px)` : `translateY(${offset}px)`;
});

window.addEventListener("pointerup", (event) => {
  if (!drag) return;

  const { overlay, dismiss } = drag;
  const size = dismiss.axis === "x" ? overlay.offsetWidth : overlay.offsetHeight;
  const shouldClose = getDragDistance(event, drag) > size * CLOSE_THRESHOLD;

  endDrag();

  if (shouldClose) closeOverlayElement(overlay);
});

window.addEventListener("pointercancel", endDrag);
