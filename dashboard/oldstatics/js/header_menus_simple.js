// dashboard/static/dashboard/js/header_menus_simple.js
(() => {
  const OPEN = 'open';

  // Toggle a given header-menu
  function toggleMenu(menu, btn) {
    if (menu.classList.contains(OPEN)) {
      closeMenu(menu, btn);
    } else {
      // close others
      document.querySelectorAll('.header-menu.' + OPEN).forEach(m => {
        if (m !== menu) closeMenu(m);
      });
      openMenu(menu, btn);
    }
  }

  function openMenu(menu, btn) {
    menu.classList.add(OPEN);
    if (btn) btn.setAttribute('aria-expanded', 'true');
  }

  function closeMenu(menu, btn) {
    menu.classList.remove(OPEN);
    const button = btn || menu.querySelector('button');
    if (button) button.setAttribute('aria-expanded', 'false');
  }

  // Click handler
  document.addEventListener('click', (ev) => {
    const btn = ev.target.closest('.header-menu > button, .notifications-title, .profile-btn');
    if (btn) {
      const menu = btn.closest('.header-menu');
      if (menu) {
        toggleMenu(menu, btn);
        ev.stopPropagation(); // avoid immediate outside-close
      }
      return;
    }
    // clicked outside -> close all
    document.querySelectorAll('.header-menu.open').forEach(m => closeMenu(m));
  });

  // Escape closes
  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape') {
      document.querySelectorAll('.header-menu.open').forEach(m => closeMenu(m));
    }
  });

  // Close on resize (prevent stale open)
  window.addEventListener('resize', () => {
    document.querySelectorAll('.header-menu.open').forEach(m => closeMenu(m));
  });
})();
