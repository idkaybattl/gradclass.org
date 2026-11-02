// Add Django's CSRF token and the usual AJAX marker to every htmx request.
(function () {
  if (!window.htmx) return;

  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(";").shift();
    return null;
  }

  document.addEventListener("htmx:configRequest", (event) => {
    const headers = event.detail.headers || (event.detail.headers = {});
    const token = getCookie("csrftoken");
    if (token) headers["X-CSRFToken"] = token;
    headers["X-Requested-With"] = "XMLHttpRequest";
  });
})();
