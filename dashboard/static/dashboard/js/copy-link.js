function findCopyFields(root) {
  const fields = Array.from(root.querySelectorAll?.("[data-copy-field]") ?? []);
  if (root instanceof Element && root.matches("[data-copy-field]")) {
    fields.unshift(root);
  }
  return fields;
}

async function copyFromField(button, input) {
  input.focus();
  input.select();

  try {
    await navigator.clipboard.writeText(input.value);
  } catch {
    // Clipboard API needs a secure context; the selection fallback also works.
    document.execCommand("copy");
  }

  const label = button.dataset.label ?? button.textContent;
  button.dataset.label = label;
  button.textContent = "Kopiert";
  window.setTimeout(() => {
    button.textContent = label;
  }, 2000);
}

function initCopyFields(root = document) {
  findCopyFields(root).forEach((field) => {
    if (field.dataset.copyInitialized === "true") return;

    const button = field.querySelector("[data-copy-button]");
    const input = field.querySelector("input, textarea");
    if (!button || !input) return;

    field.dataset.copyInitialized = "true";
    button.addEventListener("click", () => copyFromField(button, input));
  });
}

window.initCopyFields = initCopyFields;
