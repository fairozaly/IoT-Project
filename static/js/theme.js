document.addEventListener('DOMContentLoaded', () => {
    const themeToggle = document.getElementById('themeToggle');
    const body = document.body;

    // Check if the user previously picked dark mode
    const currentTheme = localStorage.getItem('theme');
    if (currentTheme === 'dark') {
        body.classList.add('dark-mode');
        themeToggle.textContent = 'Light mode';
        themeToggle.setAttribute('aria-label', 'Enable light mode');
    }

    // Listen for clicks on the toggle button
    themeToggle.addEventListener('click', () => {
        // Toggle the CSS class on the body element
        body.classList.toggle('dark-mode');
        
        // Update local settings and button text accordingly
        if (body.classList.contains('dark-mode')) {
            localStorage.setItem('theme', 'dark');
            themeToggle.textContent = 'Light mode';
            themeToggle.setAttribute('aria-label', 'Enable light mode');
        } else {
            localStorage.setItem('theme', 'light');
            themeToggle.textContent = 'Dark mode';
            themeToggle.setAttribute('aria-label', 'Enable dark mode');
        }
    });
});
