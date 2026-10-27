const eventsPage = document.querySelector("[data-events-page]");

if (eventsPage) {
  const grid = eventsPage.querySelector("[data-events-grid]");
  const emptyState = eventsPage.querySelector("[data-events-empty]");
  const searchInput = eventsPage.querySelector("[data-events-search]");
  const ownToggle = eventsPage.querySelector("[data-events-own]");
  const filterButtons = Array.from(
    eventsPage.querySelectorAll("[data-events-filter]")
  );
  const allCards = Array.from(grid.querySelectorAll("[data-event-card]"));

  let activeFilter =
    filterButtons.find(
      (button) => button.getAttribute("aria-pressed") === "true"
    )?.dataset.eventsFilter ?? "all";

  function searchFields(card) {
    return [
      card.querySelector(".event-card__title")?.textContent ?? "",
      card.querySelector(".event-card__time")?.textContent ?? "",
      card.dataset.description ?? "",
    ];
  }

  function matchesFilter(card, filter) {
    if (filter === "upcoming") return card.dataset.upcoming === "true";
    if (filter === "past") return card.dataset.upcoming === "false";
    return true;
  }

  function sortCards(cards, filter) {
    return [...cards].sort((a, b) => {
      const comparison =
        Date.parse(a.dataset.startingDate) - Date.parse(b.dataset.startingDate);
      return filter === "past" ? -comparison : comparison;
    });
  }

  function render() {
    const query = searchInput.value.trim();
    const ownOnly = ownToggle.checked;

    let cards = allCards.filter(
      (card) =>
        matchesFilter(card, activeFilter) &&
        (!ownOnly || card.dataset.own === "true")
    );

    cards = query
      ? searchItems(query, cards, searchFields)
      : sortCards(cards, activeFilter);

    grid.replaceChildren(...cards, emptyState);
    emptyState.hidden = cards.length > 0;
  }

  filterButtons.forEach((button) => {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.eventsFilter;
      filterButtons.forEach((other) => {
        other.setAttribute("aria-pressed", String(other === button));
      });
      render();
    });
  });

  ownToggle.addEventListener("change", render);
  searchInput.addEventListener("input", render);

  render();
}
