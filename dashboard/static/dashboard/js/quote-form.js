function initQuoteForm(form) {
  if (form.dataset.quoteFormInitialized === "true") return;

  const lines = form.querySelector("[data-quote-lines]");
  const addButton = form.querySelector("[data-quote-add-line]");
  const template = form.querySelector("[data-quote-line-template]");
  const totalForms = form.querySelector('input[name$="-TOTAL_FORMS"]');
  const datalist = form.querySelector("[data-quote-speaker-options]");
  if (!lines || !addButton || !template || !totalForms || !datalist) return;

  form.dataset.quoteFormInitialized = "true";

  function refreshSpeakers() {
    const names = new Set();
    form.querySelectorAll('input[name$="-speaker"]').forEach((input) => {
      const name = input.value.trim();
      if (name) names.add(name);
    });

    datalist.replaceChildren(
      ...Array.from(names, (name) => {
        const option = document.createElement("option");
        option.value = name;
        return option;
      })
    );
  }

  addButton.addEventListener("click", () => {
    const index = Number.parseInt(totalForms.value, 10);
    const html = template.innerHTML.replaceAll("__prefix__", String(index));
    const wrapper = document.createElement("div");
    wrapper.innerHTML = html.trim();

    const row = wrapper.firstElementChild;
    if (!row) return;

    lines.appendChild(row);
    totalForms.value = String(index + 1);
    refreshSpeakers();
  });

  lines.addEventListener("input", (event) => {
    if (event.target.matches('input[name$="-speaker"]')) refreshSpeakers();
  });

  lines.addEventListener("click", (event) => {
    const button = event.target.closest("[data-quote-remove-line]");
    if (!button) return;

    // The clicked button is removed below; stop the click here so the global
    // overlay-outside handler does not see a detached target and close the panel.
    event.preventDefault();
    event.stopPropagation();

    const row = button.closest("[data-quote-line]");
    const deleteInput = row?.querySelector('input[name$="-DELETE"]');
    if (deleteInput) deleteInput.checked = true;
    row?.remove();
    refreshSpeakers();
  });

  refreshSpeakers();
}

function initQuoteForms(root = document) {
  const forms = [];
  if (root.matches?.("[data-quote-form]")) forms.push(root);
  forms.push(...(root.querySelectorAll?.("[data-quote-form]") ?? []));
  forms.forEach(initQuoteForm);
}

window.initQuoteForms = initQuoteForms;
