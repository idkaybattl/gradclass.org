// Minimal htmx setup: add Django CSRF & X-Requested-With headers to all requests
(function () {
  if (!window.htmx) return;

  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return null;
  }

  document.body.addEventListener('htmx:configRequest', function (evt) {
    const headers = evt.detail.headers || (evt.detail.headers = {});
    const token = getCookie('csrftoken');
    if (token) headers['X-CSRFToken'] = token;
    headers['X-Requested-With'] = 'XMLHttpRequest';
  });

  // Optional: open the big popup dialog if content is swapped into it programmatically
  document.body.addEventListener('htmx:afterSwap', function (evt) {
    const target = evt.detail.target;
    if (!target) return;
    if (target.id === 'popup-big') {
      if (typeof window.openPopupById === 'function') {
        window.openPopupById('popup-big');
      }
    }
  });
})();
