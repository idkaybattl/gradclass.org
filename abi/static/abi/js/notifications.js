const csrfToken = getCookie('csrftoken');

function updateNotificationIcon(icon, notificationCount) {

}

function updateNotifications(widget) {
  // Logic to fetch and update notification data
  const url = widget.getAttribute("data-url");
  fetch(url)
    .then(response => response.text()) // Assuming the response is HTML
    .catch(error => console.error('Error fetching notifications:', error))
    .then(notifications => {
      widget.querySelector(".notifications-list").innerHTML = notifications;
      widget.querySelectorAll('#mark-as-read').forEach(button => {
        button.addEventListener('click', markAsRead);
      });

      // parse html to get notificationCount
      const notificationCount = widget.querySelector("#notification-count").innerHTML;

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
      'X-CSRFToken': csrfToken
    },
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        updateNotifications(document.getElementById("notifications"));
      }
    })
    .catch(error => {
      console.error('Error marking all notifications as read:', error);
    });
}

function markAsRead(event) {
  const url = event.target.getAttribute("data-url");
  fetch(url, {
    method: "POST",
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken
    },
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        const clickedButton = event.target;
        clickedButton.closest('.notification').remove();
        updateNotifications(document.getElementById("notifications"));
      }
    })
    .catch(error => {
      console.error('Error marking notification as read:', error);
    });
}

// Attach event listeners
document.addEventListener('DOMContentLoaded', function () {
  updateNotifications(document.getElementById("notifications"));
  document.getElementById("mark-all-as-read").addEventListener('click', markAllRead);

});
