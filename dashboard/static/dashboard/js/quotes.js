function initQuotesList(root = document) {
  const page = root.matches?.("[data-quotes-page]")
    ? root
    : root.querySelector?.("[data-quotes-page]");
  const list = page?.querySelector("[data-quotes-list]");
  const emptyState = page?.querySelector("[data-quotes-empty]");
  const searchInput = page?.querySelector("[data-quotes-search]");
  if (!page || !list || !emptyState || !searchInput) return;
  if (page.dataset.quotesInitialized === "true") return;

  const allCards = Array.from(list.querySelectorAll("[data-quote-card]"));

  page.dataset.quotesInitialized = "true";

  function searchFields(card) {
    return [
      card.dataset.quoteText ?? "",
      card.dataset.quoteSpeakers ?? "",
      card.dataset.quoteInfo ?? "",
      card.dataset.quoteUploader ?? "",
    ];
  }

  function render() {
    const query = searchInput.value.trim();
    const cards = query
      ? searchItems(query, allCards, searchFields)
      : allCards;

    list.replaceChildren(...cards, emptyState);
    emptyState.hidden = cards.length > 0;
  }

  searchInput.addEventListener("input", render);

  render();
}

window.initQuotesList = initQuotesList;
