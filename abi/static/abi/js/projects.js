function openDetails(id) {
  document.getElementById("details-" + id).style.display = "block";
}
function closeDetails(id) {
  document.getElementById("details-" + id).style.display = "none";
}

function openEdit(id) {
  closeDetails(id);
  document.getElementById("edit-" + id).style.display = "block";
}

function closeEdit(id) {
  document.getElementById("edit-" + id).style.display = "none";
  openDetails(id);
}
