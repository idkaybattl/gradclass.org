const INTRO_STEP_ALIASES = {
  welcome: "intro-welcome",
  features: "intro-features",
  closing: "intro-closing",
  password: "intro-password",
  email: "intro-email",
  profile: "intro-profile",
};

function normalizeStepId(value) {
  if (!value) return null;
  if (INTRO_STEP_ALIASES[value]) return INTRO_STEP_ALIASES[value];
  return value.startsWith("intro-") ? value : `intro-${value}`;
}

function showStep(showId, hideId) {
  const step = document.getElementById(showId);
  if (!step) return;

  const container = step.closest("[data-introduction]") ?? document;
  container.querySelectorAll("[data-intro-step]").forEach((other) => {
    other.hidden = other !== step;
  });

  if (hideId) {
    const hideEl = document.getElementById(hideId);
    if (hideEl && hideEl !== step) hideEl.hidden = true;
  }
}

function focusStep(stepId) {
  const step = document.getElementById(stepId);
  const first = step?.querySelector(
    "button:not([disabled]), a[href], input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex='-1'])"
  );
  if (first instanceof HTMLElement) first.focus({ preventScroll: true });
}

function findIntroduction(root) {
  if (root instanceof Element && root.matches("[data-introduction]")) {
    return root;
  }
  return root.querySelector?.("[data-introduction]") ?? null;
}

function handleIntroClick(event) {
  const target = event.target instanceof Element ? event.target : null;
  const button = target?.closest("button[data-from][data-to]");
  if (!button) return;

  const showId = normalizeStepId(button.dataset.to);
  if (!showId) return;

  event.preventDefault();
  showStep(showId, normalizeStepId(button.dataset.from));
  focusStep(showId);
}

function initIntroduction(root = document) {
  const container = findIntroduction(root);
  if (!container || container.dataset.introInitialized === "true") return;

  container.dataset.introInitialized = "true";
  container.addEventListener("click", handleIntroClick);

  showStep(normalizeStepId(container.dataset.initialStep) ?? "intro-welcome");
}

window.initIntroduction = initIntroduction;

document.addEventListener("intro:password-set", () => {
  showStep("intro-email", "intro-password");
  focusStep("intro-email");
});

document.addEventListener("intro:email-set", () => {
  showStep("intro-profile", "intro-email");
  focusStep("intro-profile");
});
