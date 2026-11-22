// The walk cycle is pure CSS. This only schedules the occasional "look to
// camera" turn, which plays the 20-frame sheet once and hands back to the walk.
const TURN_DELAY_MIN = 3000;
const TURN_DELAY_MAX = 9000;
const TURN_RETRY_DELAY = 1000;

function findFoxes(root) {
  const foxes = Array.from(root.querySelectorAll?.(".fox") ?? []);
  if (root instanceof Element && root.matches(".fox")) foxes.unshift(root);
  return foxes;
}

function randomTurnDelay() {
  return TURN_DELAY_MIN + Math.random() * (TURN_DELAY_MAX - TURN_DELAY_MIN);
}

// The part of the fox's box that its mask shows, or null when the fox is not
// masked (the title card).
function getVisibleBounds(fox) {
  const styles = getComputedStyle(fox);
  const clearLeft = parseFloat(styles.getPropertyValue("--fox-nav-clear-left"));
  const clearRight = parseFloat(styles.getPropertyValue("--fox-nav-clear-right"));
  const parent = fox.parentElement;

  if (Number.isNaN(clearLeft) || Number.isNaN(clearRight) || !parent) {
    return null;
  }

  const bounds = parent.getBoundingClientRect();
  return { left: bounds.left + clearLeft, right: bounds.right - clearRight };
}

function isVisible(fox) {
  const sprite = fox.querySelector(".fox__flip");
  if (!sprite) return false;

  const rect = sprite.getBoundingClientRect();
  const bounds = getVisibleBounds(fox);
  if (!bounds) return rect.right > 0 && rect.left < window.innerWidth;

  return rect.left >= bounds.left && rect.right <= bounds.right;
}

function scheduleTurn(fox, delay = randomTurnDelay()) {
  window.setTimeout(() => {
    if (!fox.isConnected) return;

    // Only embellish a visible pass; look again shortly while it is out of view.
    if (!isVisible(fox)) {
      scheduleTurn(fox, TURN_RETRY_DELAY);
      return;
    }

    playTurn(fox);
  }, delay);
}

function playTurn(fox) {
  const sprite = fox.querySelector(".fox__sprite");
  if (!sprite) return;

  function finish(event) {
    if (event.target !== sprite || event.animationName !== "fox-turn") return;

    sprite.removeEventListener("animationend", finish);
    sprite.classList.remove("fox__sprite--turn");
    scheduleTurn(fox);
  }

  // The walk restarts at frame 0 on every iteration, and the turn sheet starts
  // on that same pose, so swapping there cannot be seen.
  function start() {
    sprite.removeEventListener("animationiteration", start);
    sprite.addEventListener("animationend", finish);
    sprite.classList.add("fox__sprite--turn");
  }

  sprite.addEventListener("animationiteration", start);
}

function initFox(root = document) {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  findFoxes(root).forEach((fox) => {
    if (fox.dataset.foxInitialized === "true") return;

    fox.dataset.foxInitialized = "true";
    scheduleTurn(fox);
  });
}

window.initFox = initFox;
