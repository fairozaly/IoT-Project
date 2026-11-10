(function () {
  'use strict';

  const body = document.body;
  const toggle = document.getElementById('themeToggle');
  if (!body || !toggle) return;

  const STORAGE_KEY = 'smartstore-theme';

  function setTheme(isDark) {
    body.classList.toggle('dark-mode', isDark);
    toggle.setAttribute('aria-pressed', String(isDark));
    toggle.setAttribute('title', isDark ? 'Switch to light mode' : 'Switch to dark mode');
    localStorage.setItem(STORAGE_KEY, isDark ? 'dark' : 'light');
  }

  const savedTheme = localStorage.getItem(STORAGE_KEY);
  if (savedTheme === 'dark' || savedTheme === 'light') {
    setTheme(savedTheme === 'dark');
  } else {
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    setTheme(prefersDark);
  }

  toggle.addEventListener('click', function () {
    const nextTheme = !body.classList.contains('dark-mode');
    setTheme(nextTheme);
  });
})();
