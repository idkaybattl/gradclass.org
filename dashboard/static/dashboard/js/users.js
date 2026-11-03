function initUsersList(root = document) {
  const page = root.matches?.("[data-users-page]")
    ? root
    : root.querySelector?.("[data-users-page]");
  const grid = page?.querySelector("[data-users-grid]");
  const emptyState = page?.querySelector("[data-users-empty]");
  const searchInput = page?.querySelector("[data-user-search]");
  if (!page || !grid || !emptyState || !searchInput) return;
  if (page.dataset.usersInitialized === "true") return;

  const allCards = Array.from(grid.querySelectorAll("[data-user-card]"));
  page.dataset.usersInitialized = "true";

  function searchFields(card) {
    return [
      card.dataset.userName ?? "",
      card.dataset.userMail ?? "",
      card.dataset.userUsername ?? "",
    ];
  }

  function render() {
    const query = searchInput.value.trim();
    const cards = query ? searchItems(query, allCards, searchFields) : allCards;

    grid.replaceChildren(...cards, emptyState);
    emptyState.hidden = cards.length > 0;
  }

  searchInput.addEventListener("input", render);
  render();
}

window.initUsersList = initUsersList;
