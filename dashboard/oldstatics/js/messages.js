function dismissMessage(messageEl) {
  if (!messageEl || messageEl.classList.contains("is-hiding")) return;

  messageEl.classList.add("is-hiding");
  window.setTimeout(() => {
    messageEl.remove();
  }, 200);
}

function setupMessage(messageEl) {
  const dismissButton = messageEl.querySelector("[data-dismiss-message]");
  const dismissAfterRaw = messageEl.dataset.dismissAfter;
  const dismissAfter = Number.parseInt(dismissAfterRaw || "", 10);

  if (dismissButton) {
    dismissButton.addEventListener("click", () => dismissMessage(messageEl));
  }

  if (!Number.isNaN(dismissAfter) && dismissAfter > 0) {
    messageEl.style.setProperty("--dismiss-duration", `${dismissAfter}ms`);
    messageEl.classList.add("is-timed");

    window.setTimeout(() => {
      dismissMessage(messageEl);
    }, dismissAfter);
  }
}

document.querySelectorAll("[data-site-message]").forEach(setupMessage);
