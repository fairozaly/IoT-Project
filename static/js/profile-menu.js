(function () {
  'use strict';

  const button = document.getElementById('profileMenuButton');
  const menu = document.getElementById('profile-menu');
  if (!button || !menu) return;

  const items = [...menu.querySelectorAll('[role="menuitem"]')];

  function setOpen(open, moveFocus) {
    menu.hidden = !open;
    button.setAttribute('aria-expanded', String(open));
    if (open && moveFocus && items[0]) items[0].focus();
  }

  button.addEventListener('click', () => setOpen(menu.hidden, true));

  document.addEventListener('click', event => {
    if (!button.parentElement.contains(event.target)) setOpen(false, false);
  });

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !menu.hidden) {
      event.preventDefault();
      setOpen(false, false);
      button.focus();
    }
  });

  items.forEach(item => {
    item.addEventListener('keydown', event => {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        const offset = event.key === 'ArrowDown' ? 1 : -1;
        const nextIndex = (items.indexOf(item) + offset + items.length) % items.length;
        items[nextIndex].focus();
      }
      if (event.key === 'Home') {
        event.preventDefault();
        items[0].focus();
      }
      if (event.key === 'End') {
        event.preventDefault();
        items[items.length - 1].focus();
      }
    });
  });
})();
