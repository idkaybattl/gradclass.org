const overlay = document.querySelector(".overlay");
const handle = overlay.querySelector(".overlay-handle");
const content = overlay.querySelector(".overlay-content");

// openOverlay("<h2>Hallo</h2>") or openOverlay() to open with the current content
function openOverlay(markup) {
  if (markup !== undefined) content.innerHTML = markup;
  content.scrollTop = 0;
  overlay.classList.add("open");
}

function closeOverlay() {
  overlay.classList.remove("open", "dragging");
  overlay.style.transform = "";
}

let startY = null;

handle.addEventListener("pointerdown", (event) => {
  if (event.button) return;
  startY = event.clientY;
  overlay.classList.add("dragging");
  handle.setPointerCapture(event.pointerId);
});

window.addEventListener("pointermove", (event) => {
  if (startY === null) return;
  overlay.style.transform = `translateY(${Math.max(0, event.clientY - startY)}px)`;
});

window.addEventListener("pointerup", (event) => {
  if (startY === null) return;
  const offset = event.clientY - startY;
  startY = null;
  if (offset > overlay.offsetHeight / 4) {
    closeOverlay();
  } else {
    overlay.classList.remove("dragging");
    overlay.style.transform = "";
  }
});

window.addEventListener("pointercancel", () => {
  startY = null;
  overlay.classList.remove("dragging");
  overlay.style.transform = "";
});

overlay.querySelector(".overlay-close").addEventListener("click", closeOverlay);

document.addEventListener("pointerdown", (event) => {
  if (overlay.classList.contains("open") && !overlay.contains(event.target)) closeOverlay();
});
