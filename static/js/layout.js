(function () {
  'use strict';

  const button = document.getElementById('notificationsToggle');
  if (!button) return;

  const panel = document.getElementById('notification-panel');
  const list = document.getElementById('notification-list');
  const markRead = document.getElementById('notifications-read');
  const badge = button.querySelector('.notification-badge');
  const messages = [...document.querySelectorAll('#toastContainer .toast')].map(toast => toast.textContent);
  let unread = messages.length;

  function render() {
    const entries = messages.map(message => {
      const item = document.createElement('li');
      item.textContent = message;
      return item;
    });
    const content = document.createElement(entries.length ? 'ul' : 'p');
    if (entries.length) content.append(...entries);
    else content.textContent = 'You have no notifications.';
    list.replaceChildren(content);
    markRead.disabled = unread === 0;
    badge.hidden = unread === 0;
    badge.textContent = unread > 99 ? '99+' : String(unread);
    button.setAttribute('aria-label', unread ? `Notifications, ${unread} unread` : 'Notifications');
  }

  function setOpen(open) {
    panel.hidden = !open;
    button.setAttribute('aria-expanded', String(open));
  }

  button.addEventListener('click', () => setOpen(panel.hidden));
  markRead.addEventListener('click', () => {
    unread = 0;
    render();
  });
  document.addEventListener('click', event => {
    if (!button.parentElement.contains(event.target)) setOpen(false);
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !panel.hidden) {
      setOpen(false);
      button.focus();
    }
  });

  async function pollAlerts() {
    try {
      const response = await fetch(button.dataset.alertUrl, {
        cache: 'no-store', signal: AbortSignal.timeout(8000)
      });
      if (!response.ok) return;
      const items = await response.json();
      for (const item of items) {
        messages.unshift(item.message);
        unread++;
        window.showToast(item.message, 'error');
      }
      if (messages.length > 100) messages.length = 100;
      unread = Math.min(unread, messages.length);
      if (items.length) render();
    } catch {
      // Retry on the next poll.
    } finally {
      setTimeout(pollAlerts, 5000);
    }
  }

  render();
  if (button.dataset.alertUrl) pollAlerts();
})();
