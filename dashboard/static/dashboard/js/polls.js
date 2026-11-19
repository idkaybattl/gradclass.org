function matchesPollFilter(phase, filter) {
  if (filter === "closed") return phase === "closed";
  if (filter === "drafts") return phase === "draft";
  if (filter === "all") return true;
  return phase !== "closed" && phase !== "draft";
}

function initPollsList(root = document) {
  const page = root.matches?.("[data-polls-page]")
    ? root
    : root.querySelector?.("[data-polls-page]");
  const grid = page?.querySelector("[data-polls-grid]");
  const emptyState = page?.querySelector("[data-polls-empty]");
  if (!page || !grid || !emptyState) return;
  if (page.dataset.pollsInitialized === "true") return;

  const buttons = Array.from(page.querySelectorAll("[data-polls-filter]"));
  const cards = Array.from(grid.querySelectorAll("[data-poll-card]"));
  if (buttons.length === 0) return;

  page.dataset.pollsInitialized = "true";

  let activeFilter =
    buttons.find((button) => button.getAttribute("aria-pressed") === "true")
      ?.dataset.pollsFilter ?? "open";

  function render() {
    let visible = 0;

    cards.forEach((card) => {
      const show = matchesPollFilter(card.dataset.phase, activeFilter);
      card.hidden = !show;
      if (show) visible += 1;
    });

    emptyState.hidden = visible > 0;
  }

  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.pollsFilter;
      buttons.forEach((other) => {
        other.setAttribute("aria-pressed", String(other === button));
      });
      render();
    });
  });

  render();
}

window.initPollsList = initPollsList;
