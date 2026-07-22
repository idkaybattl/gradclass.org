
/* -------------------------------------------------
   introduction.js – step navigation for the intro page
   ------------------------------------------------- */

const forwardBtn = document.getElementById('to-step-2');
const backLink = document.getElementById('back-to-step-1');   // ← new

/* -----------------------------------------------------------------
   Helper – show/hide a step
   ----------------------------------------------------------------- */
function showStep(showId, hideId) {
  const showEl = document.getElementById(showId);
  const hideEl = document.getElementById(hideId);
  if (showEl) showEl.classList.remove('hidden');
  if (hideEl) hideEl.classList.add('hidden');
}

/* -----------------------------------------------------------------
   Forward: step‑1 → step‑2
   ----------------------------------------------------------------- */
if (forwardBtn) {
  forwardBtn.addEventListener('click', () => {
    showStep('step-2', 'step-1');

    // focus the first interactive element inside step‑2
    const firstInput = document.querySelector(
      '#step-2 form input, #step-2 form textarea, #step-2 form select'
    );
    if (firstInput) firstInput.focus();
  });
}

/* -----------------------------------------------------------------
   Backward: step‑2 → step‑1
   ----------------------------------------------------------------- */
if (backLink) {
  backLink.addEventListener('click', (e) => {
    e.preventDefault();               // stop the default anchor jump
    showStep('step-1', 'step-2');

    // move focus back to the “Weiter” button (or the first focusable
    // element inside step‑1 if you prefer)
    if (forwardBtn) forwardBtn.focus();
  });
}
