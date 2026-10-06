// Keep this file safe and passive when htmx is present; htmx handles notifications via markup.
(function () {
  const safeGetCookie = (name) => {
    try {
      const value = `; ${document.cookie}`;
      const parts = value.split(`; ${name}=`);
      if (parts.length === 2) return parts.pop().split(';').shift();
    } catch (_) { }
    return null;
  };
  const csrfToken = safeGetCookie('csrftoken');

  function updateNotificationIcon(icon, notificationCount) {
    // no-op placeholder; implement icon badge update if you add an icon element
  }

  // Legacy fetch-based flow (used only if htmx is not loaded)
  function updateNotifications(widget) {
    if (!widget) return;
    const url = widget.getAttribute("data-url");
    fetch(url)
      .then(response => response.text())
      .catch(error => console.error('Error fetching notifications:', error))
      .then(notifications => {
        if (!notifications) return;
        widget.querySelector(".notifications-list").innerHTML = notifications;

        // parse html to get notificationCount
        const countEl = widget.querySelector("#notification-count");
        const notificationCount = countEl ? countEl.innerHTML : 0;

        const icon = widget.closest("notification-icon");
        updateNotificationIcon(icon, notificationCount);
      });
  }

  function markAllRead(event) {
    const url = event.target.getAttribute("data-url");
    fetch(url, {
      method: "POST",
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken || ''
      },
    })
      .then(response => response.json())
      .then(data => {
        if (data && data.success) {
          updateNotifications(document.getElementById("notifications"));
        }
      })
      .catch(error => {
        console.error('Error marking all notifications as read:', error);
      });
  }

  // When htmx is present, do not attach legacy behavior to avoid duplicate requests
  document.addEventListener('DOMContentLoaded', function () {
    if (window.htmx) {
      return; // htmx-driven via attributes in base.html and notifications.html
    }
    const notificationsRoot = document.getElementById("notifications");
    if (!notificationsRoot) return;
    updateNotifications(notificationsRoot);
    const markAll = document.getElementById("mark-all-as-read");
    if (markAll) {
      markAll.addEventListener('click', markAllRead);
    }
  });
})();
