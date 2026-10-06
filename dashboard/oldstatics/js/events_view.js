// global storage for all viewable events
let allEvents = [];

function filterEvents(widget) {
  const searchInput = widget.querySelector("[data-event-search]");
  const term = searchInput.value.toLowerCase();
  const events_grid = widget.querySelector(".events-grid");

  if (events_grid.querySelector(".empty-events")) { return; }

  if (term.trim() == "") {
    allEvents.forEach((option) => events_grid.appendChild(option));
    return;
  }

  const visibleOptions = term
    ? searchItems(term, allEvents, (option) => [
      option.querySelector("#title").innerHTML,
      option.querySelector("#starting-datetime").innerHTML,
      option.querySelector("#ending-datetime").innerHTML,
      option.querySelector("#description").innerHTML,
    ])
    : allEvents.sort(
      (a, b) =>
        a.querySelector("#event-title").innerHTML.localeCompare(
          b.querySelector("#event-title").innerHTML, "de"
        )
    );

  events_grid.innerHTML = "";
  visibleOptions.forEach((option) => events_grid.appendChild(option));
}

document.addEventListener("DOMContentLoaded", () => {
  const widget = document.querySelector(".events-page");

  const searchInput = widget.querySelector("[data-event-search]");
  searchInput.addEventListener("input", () => filterEvents(widget));

  allEvents = Array.from(document.querySelectorAll(".event-card"));
  filterEvents(widget);
});
