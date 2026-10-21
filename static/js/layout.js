/* layout.js */ (function () { 'use strict';

const button = document.getElementById('notificationsToggle'); if (!button) return;

const alerts = []; const seen = Object.create(null); let unread = 0;


const wrapper = document.createElement('div'); wrapper.className = 'notification-wrapper'; button.parentNode.insertBefore(wrapper, button); wrapper.appendChild(button); wrapper.appendChild(panel);

const badge = document.createElement('span'); badge.className = 'notification-badge'; badge.hidden = true; badge.setAttribute('aria-label', 'Unread notifications'); button.appendChild(badge);

const list = panel.querySelector('.notification-list'); const clearButton = panel.querySelector('.notification-clear');

function updateBadge() { badge.textContent = unread > 99 ? '99+' : String(unread); badge.hidden = unread === 0; }

function renderAlerts() { list.replaceChildren();

if (alerts.length === 0) {
  const empty = document.createElement('p');
  empty.className = 'notification-empty';
  empty.textContent = 'You have no notifications.';
  list.appendChild(empty);
  return;
}

alerts.slice().reverse().forEach(function (alert) {
  const item = document.createElement('article');
  item.className = 'notification-item' +
    (alert.read ? ' is-read' : ' is-unread');

  const message = document.createElement('p');
  message.textContent = alert.message;

  const status = document.createElement('span');
  status.className = 'notification-status';
  status.textContent = alert.read ? 'Read' : 'Unread';

  item.appendChild(message);
  item.appendChild(status);

  item.addEventListener('click', function () {
    if (!alert.read) {
      alert.read = true;
      unread--;
      updateBadge();
      renderAlerts();
    }
  });

  list.appendChild(item);
});


}

function addAlert(item) { if (item.id == null || seen[item.id]) return;

seen[item.id] = true;

const alert = {
  id: item.id,
  message: item.message || 'New alert',
  read: false
};

alerts.push(alert);
unread++;

// Keep the panel manageable.
if (alerts.length > 100) {
  const removed = alerts.shift();
  if (!removed.read) unread--;
}

updateBadge();
renderAlerts();

// Reuse the toast system from toasts.js.
if (typeof window.showToast === 'function') {
  window.showToast(alert.message, 'error');
}


}

function pollAlerts() { fetch('/alerts') .then(function (response) { if (!response.ok) throw new Error('Failed to fetch alerts'); return response.json(); }) .then(function (items) { if (!Array.isArray(items)) return; items.forEach(addAlert); }) .catch(function (error) { console.error('Unable to fetch notifications:', error); }); }

button.setAttribute('aria-expanded', 'false');

button.addEventListener('click', function (event) { event.stopPropagation(); panel.hidden = !panel.hidden; button.setAttribute('aria-expanded', String(!panel.hidden));

if (!panel.hidden) {
  renderAlerts();
}


});

clearButton.addEventListener('click', function () { alerts.forEach(function (alert) { alert.read = true; });

unread = 0;
updateBadge();
renderAlerts();


});

document.addEventListener('click', function (event) { if (!wrapper.contains(event.target)) { panel.hidden = true; button.setAttribute('aria-expanded', 'false'); } });

renderAlerts(); updateBadge();

pollAlerts(); window.setInterval(pollAlerts, 5000); })();