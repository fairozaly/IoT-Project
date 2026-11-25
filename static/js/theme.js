(function () {
  'use strict';

  const body = document.body;
  const toggle = document.getElementById('themeToggle');
  const preference = document.getElementById('theme-preference');
  const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
  const storageKey = 'smartstore-theme';
  let theme = 'system';
  try {
    const saved = localStorage.getItem(storageKey);
    if (saved === 'light' || saved === 'dark') theme = saved;
  } catch {
    // The selected theme still applies to this page when storage is unavailable.
  }

  function applyTheme() {
    const isDark = theme === 'dark' || (theme === 'system' && systemTheme.matches);
    body.classList.toggle('dark-mode', isDark);
    if (preference) preference.value = theme;
    if (toggle) {
      const label = isDark ? 'Switch to light mode' : 'Switch to dark mode';
      toggle.setAttribute('aria-pressed', String(isDark));
      toggle.setAttribute('aria-label', label);
      toggle.title = label;
    }
  }

  function setTheme(value) {
    theme = value;
    applyTheme();
    try {
      localStorage.setItem(storageKey, value);
    } catch {
      // A storage restriction does not prevent changing the current theme.
    }
  }

  preference?.addEventListener('change', () => setTheme(preference.value));
  toggle?.addEventListener('click', () => setTheme(body.classList.contains('dark-mode') ? 'light' : 'dark'));
  systemTheme.addEventListener('change', applyTheme);
  applyTheme();
})();
