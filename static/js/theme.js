(() => {
  const storageKey = 'gj-theme';
  const themes = ['obsidian', 'daylight'];
  const topActions = document.querySelector('.top-actions');
  const profileLink = topActions?.querySelector('.profile');
  const workspaceToggle = document.querySelector('body[data-page] [data-theme-toggle]');

  if (topActions && profileLink && workspaceToggle) {
    topActions.insertBefore(workspaceToggle, profileLink);
  }

  function applyTheme(theme) {
    const selected = themes.includes(theme) ? theme : 'obsidian';
    document.documentElement.dataset.theme = selected;

    document.querySelectorAll('[data-theme-toggle]').forEach(button => {
      const nextTheme = selected === 'obsidian' ? 'daylight' : 'obsidian';
      button.setAttribute('aria-label', `Switch to ${nextTheme} theme`);
      button.setAttribute('aria-pressed', String(selected === 'daylight'));
      button.querySelector('[data-theme-label]').textContent = nextTheme === 'daylight'
        ? 'Daylight'
        : 'Obsidian';
    });
  }

  let savedTheme = 'obsidian';
  try {
    savedTheme = localStorage.getItem(storageKey) || savedTheme;
  } catch {}
  applyTheme(savedTheme);

  document.querySelectorAll('[data-theme-toggle]').forEach(button => {
    button.addEventListener('click', () => {
      const nextTheme = document.documentElement.dataset.theme === 'obsidian'
        ? 'daylight'
        : 'obsidian';
      applyTheme(nextTheme);
      try {
        localStorage.setItem(storageKey, nextTheme);
      } catch {}
    });
  });

  window.addEventListener('storage', event => {
    if (event.key === storageKey) applyTheme(event.newValue);
  });
})();