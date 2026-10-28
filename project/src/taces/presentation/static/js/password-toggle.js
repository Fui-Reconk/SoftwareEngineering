/* Passwords stay masked by default and are hidden again after submit or dialog close. */
(function () {
  'use strict';

  document.querySelectorAll('[data-password-toggle]').forEach((button) => {
    const input = document.getElementById(button.getAttribute('aria-controls'));
    if (!input || input.type !== 'password') return;

    function setVisible(visible) {
      input.type = visible ? 'text' : 'password';
      const label = visible ? button.dataset.hideLabel : button.dataset.showLabel;
      button.setAttribute('aria-pressed', String(visible));
      button.title = label;
    }

    button.addEventListener('click', () => setVisible(input.type === 'password'));
    const form = button.closest('form');
    if (form) form.addEventListener('submit', () => setVisible(false), { capture: true });
    const dialog = button.closest('dialog');
    if (dialog) dialog.addEventListener('close', () => setVisible(false));
    window.addEventListener('pageshow', (event) => { if (event.persisted) setVisible(false); });
  });
})();
