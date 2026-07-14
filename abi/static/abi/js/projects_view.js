// global storage for all viewable projects
let allProjects = [];

function filterProjects(widget) {
  const searchInput = widget.querySelector("[data-project-search]");
  const term = searchInput.value.toLowerCase();
  const projects_grid = widget.querySelector(".projects-grid");

  if (projects_grid.querySelector(".empty-projects")) { return; }

  if (term.trim() == "") {
    allProjects.forEach((option) => projects_grid.appendChild(option));
    return;
  }

  const visibleOptions = term
    ? searchItems(term, allProjects, (option) => [
      option.querySelector("#title").innerHTML,
      option.querySelector("#starting-datetime").innerHTML,
      option.querySelector("#ending-datetime").innerHTML,
      option.querySelector("#description").innerHTML,
    ])
    : allUserOptions.sort(
      (a, b) =>
        a.querySelector("#project-title").value.localeCompare(
          b.querySelector("#project-title").value, "de"
        )
    );

  projects_grid.innerHTML = "";
  visibleOptions.forEach((option) => projects_grid.appendChild(option));
}

document.addEventListener("DOMContentLoaded", () => {
  const widget = document.querySelector(".projects-page");

  const searchInput = widget.querySelector("[data-project-search]");
  searchInput.addEventListener("input", () => filterProjects(widget));

  allProjects = Array.from(document.querySelectorAll(".project-card"));
  filterProjects(widget);
});
