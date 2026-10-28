/* 账号本人改密；成功后服务端撤销此账号的所有会话。 */
(function () {
  'use strict';
  const el = (id) => document.getElementById(id);
  const form = el('passwordForm');
  const fields = el('passwordFields');
  const current = el('currentPassword');
  const next = el('newPassword');
  const confirm = el('confirmPassword');
  const error = el('passwordError');
  const success = el('passwordSuccess');
  const login = el('passwordLogin');
  let ready = false;
  let saving = false;

  window.SHELL.ready.then((session) => {
    if (!session) return;
    ready = true;
    form.hidden = false;
  }).catch(() => {
    error.textContent = '账号信息暂时取不到，请刷新后重试。';
    error.hidden = false;
    form.hidden = false;
    fields.disabled = true;
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!ready || saving) return;
    error.hidden = true;
    if (!current.value || [...next.value].length < 12 || [...next.value].length > 128) {
      error.textContent = '请填写当前密码，新密码须为 12–128 个字符。';
      error.hidden = false;
      return;
    }
    if (next.value !== confirm.value) {
      error.textContent = '两次输入的新密码不一致。';
      error.hidden = false;
      return;
    }
    saving = true;
    fields.disabled = true;
    try {
      await window.API.post('/api/auth/password', { current_password: current.value, new_password: next.value });
      current.value = '';
      next.value = '';
      confirm.value = '';
      ready = false;
      form.hidden = true;
      success.textContent = '密码已修改，所有设备的登录已退出。请使用新密码重新登录。';
      success.hidden = false;
      login.hidden = false;
      login.focus();
    } catch (failure) {
      if (failure.status === 401) {
        window.location.replace('/login?next=%2Faccount%2Fpassword');
      } else {
        error.textContent = failure.message || '修改失败，请稍后重试。';
        error.hidden = false;
      }
    } finally {
      saving = false;
      if (ready) fields.disabled = false;
    }
  });
})();
