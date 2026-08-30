
/* introduction.js – minimal, generalized move-step handler */

const moveButtons = document.querySelectorAll('button[data-from][data-to]');

function normalizeStepId(val) {
  if (!val) return null;
  return val.startsWith('step-') ? val : `step-${val}`;
}

function showStep(showId, hideId) {
  const showEl = document.getElementById(showId);
  const hideEl = document.getElementById(hideId);
  if (showEl) showEl.classList.remove('hidden');
  if (hideEl) hideEl.classList.add('hidden');
}
window.showStep = showStep; // used by htmx in your template

moveButtons.forEach((btn) => {
  btn.addEventListener('click', (e) => {
    e.preventDefault();
    const from = normalizeStepId(btn.dataset.from);
    const to = normalizeStepId(btn.dataset.to);
    if (!to) return;
    showStep(to, from);

    // focus first interactive element inside target step (optional)
    const target = document.getElementById(to);
    if (target) {
      const first = target.querySelector(
        'button:not([disabled]), a[href], input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      if (first) first.focus();
    }
  });
});
