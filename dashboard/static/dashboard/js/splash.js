// Whether the title card shows at all is decided before first paint, by the
// inline check in index.html. This only takes it back out of the DOM.
function findSplashes(root) {
  const splashes = Array.from(root.querySelectorAll?.(".splash") ?? []);
  if (root instanceof Element && root.matches(".splash")) splashes.unshift(root);
  return splashes;
}

function initSplash(root = document) {
  findSplashes(root).forEach((splash) => {
    if (splash.dataset.splashInitialized === "true") return;
    splash.dataset.splashInitialized = "true";

    // CSS hides it under reduced motion, so there is nothing to animate out.
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      splash.remove();
      return;
    }

    splash.addEventListener("animationend", (event) => {
      // The title's own animations bubble through here as well.
      if (event.target === splash && event.animationName === "splash-out") {
        splash.remove();
      }
    });
  });
}

window.initSplash = initSplash;
