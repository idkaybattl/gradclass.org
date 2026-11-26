// Confirmation dialog for irreversible actions. Elements opt in with
// data-confirm (message), data-confirm-title and data-confirm-action. It covers
// htmx requests (htmx:confirm) and plain form submissions alike.
(() => {
  const dialog = document.getElementById("confirm-dialog");
  if (!(dialog instanceof HTMLElement)) return;

  const titleElement = dialog.querySelector(".confirm-dialog__title");
  const messageElement = dialog.querySelector(".confirm-dialog__message");
  const acceptButton = dialog.querySelector(".confirm-dialog__accept");
  const cancelButton = dialog.querySelector(".confirm-dialog__cancel");

  let onConfirm = null;
  let confirmedForm = null;

  function readOptions(trigger) {
    return {
      title: trigger.dataset.confirmTitle || "Aktion bestätigen",
      message: trigger.dataset.confirm || "",
      action: trigger.dataset.confirmAction || "Bestätigen",
    };
  }

  function ask(trigger, callback) {
    const options = readOptions(trigger);

    if (typeof dialog.showModal !== "function") {
      if (window.confirm(options.message)) callback();
      return;
    }

    titleElement.textContent = options.title;
    messageElement.textContent = options.message;
    acceptButton.textContent = options.action;

    onConfirm = callback;
    dialog.returnValue = "";
    dialog.showModal();
    cancelButton.focus();
  }

  dialog.addEventListener("close", () => {
    const callback = onConfirm;
    onConfirm = null;
    if (dialog.returnValue === "confirm" && callback) callback();
  });

  // Clicking the backdrop targets the dialog element itself.
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close("cancel");
  });

  document.addEventListener("htmx:confirm", (event) => {
    const trigger = event.detail.elt?.closest?.("[data-confirm]");
    if (!trigger) return;

    event.preventDefault();
    ask(trigger, () => event.detail.issueRequest(true));
  });

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.matches("[data-confirm]")) {
      return;
    }
    // htmx forms already asked through htmx:confirm. If htmx did not load,
    // they fall back to a normal submission and still need the question.
    if (
      window.htmx &&
      (form.hasAttribute("hx-post") || form.hasAttribute("hx-get"))
    ) {
      return;
    }

    if (confirmedForm === form) {
      confirmedForm = null;
      return;
    }

    event.preventDefault();
    ask(form, () => {
      confirmedForm = form;
      form.requestSubmit();
      // Clear the guard even if validation kept requestSubmit from submitting.
      setTimeout(() => {
        if (confirmedForm === form) confirmedForm = null;
      }, 0);
    });
  });
})();
