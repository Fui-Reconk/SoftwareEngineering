/* 登录页：只负责收集凭证、调接口、把失败原因写在原地。 */
(function () {
  'use strict';

  const form = document.getElementById('loginForm');
  const error = document.getElementById('loginError');
  if (!form) return;

  const submit = form.querySelector('button[type="submit"]');

  function showError(message) {
    error.textContent = message;
    error.hidden = false;
    submit.disabled = false;
  }

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    error.hidden = true;
    submit.disabled = true;
    try {
      await window.API.post('/api/auth/login', {
        username: form.username.value.trim(),
        password: form.password.value,
      });
      const next = new URLSearchParams(window.location.search).get('next');
      window.location.assign(next && next.startsWith('/') ? next : '/');
    } catch (failure) {
      showError(failure.status === 429
        ? '尝试次数过多，过一会儿再来。'
        : failure.message || '登录失败，请重试。');
    }
  });
})();
