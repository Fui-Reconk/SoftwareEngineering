/* 管理员账号：读写走现有账号 API；敏感字段只在提交时发送。 */
(function () {
  'use strict';

  const byId = (id) => document.getElementById(id);
  const workspace = byId('accountWorkspace');
  const denied = byId('accountDenied');
  const sessionEnded = byId('accountSessionEnded');
  const sessionMessage = byId('accountSessionMessage');
  const sessionLogin = byId('accountSessionLogin');
  const rows = byId('accountRows');
  const empty = byId('accountsEmpty');
  const loadingNote = byId('accountsLoading');
  const listError = byId('accountsError');
  const retry = byId('accountsRetry');
  const more = byId('accountsMore');
  const form = byId('accountForm');
  const fields = byId('accountFields');
  const title = byId('accountFormTitle');
  const username = byId('accountUsername');
  const role = byId('accountRole');
  const status = byId('accountStatus');
  const statusField = byId('accountStatusField');
  const password = byId('accountPassword');
  const passwordLabel = byId('accountPasswordLabel');
  const passwordHint = byId('accountPasswordHint');
  const sessionHint = byId('accountSessionHint');
  const formError = byId('accountFormError');
  const saved = byId('accountSaved');
  const save = byId('accountSave');
  const cancel = byId('accountCancel');
  const PAGE_SIZE = 50;
  const roles = { teacher: '教师', admin: '管理员', auditor: '审计员' };
  let session;
  let selected = null;
  let offset = 0;
  let rowButtons = [];
  let loading = false;
  let saving = false;
  let retryReset = true;

  function updateControls() {
    const busy = loading || saving;
    fields.disabled = busy;
    more.disabled = busy;
    retry.disabled = busy;
    rowButtons.forEach((button) => { button.disabled = busy; });
  }

  function clearMessages() {
    formError.hidden = true;
    saved.hidden = true;
  }

  function beginCreate() {
    selected = null;
    title.textContent = '新建账号';
    username.value = '';
    username.readOnly = false;
    role.value = 'teacher';
    status.value = 'true';
    statusField.hidden = true;
    password.value = '';
    password.required = true;
    passwordLabel.textContent = '初始密码';
    passwordHint.textContent = '12–128 个字符。';
    sessionHint.hidden = true;
    save.textContent = '创建账号';
    cancel.hidden = true;
    clearMessages();
  }

  function beginEdit(account) {
    if (loading || saving) return;
    selected = account;
    title.textContent = '编辑账号';
    username.value = account.username;
    username.readOnly = true;
    role.value = account.role;
    status.value = String(account.is_active);
    statusField.hidden = false;
    password.value = '';
    password.required = false;
    passwordLabel.textContent = '重置密码';
    passwordHint.textContent = '留空则不修改；填写时须为 12–128 个字符。';
    sessionHint.hidden = false;
    save.textContent = '保存修改';
    cancel.hidden = false;
    clearMessages();
    title.focus();
  }

  function addRow(account) {
    const row = document.createElement('tr');
    const name = document.createElement('td');
    const roleCell = document.createElement('td');
    const state = document.createElement('td');
    const actions = document.createElement('td');
    const edit = document.createElement('button');
    name.textContent = account.username;
    roleCell.textContent = roles[account.role] || account.role;
    state.textContent = account.is_active ? '启用' : '停用';
    state.className = account.is_active ? 'accounts-status active' : 'accounts-status';
    edit.type = 'button';
    edit.className = 'btn';
    edit.textContent = '编辑';
    edit.setAttribute('aria-label', `编辑账号 ${account.username}`);
    edit.addEventListener('click', () => beginEdit(account));
    actions.appendChild(edit);
    row.append(name, roleCell, state, actions);
    rows.appendChild(row);
    rowButtons.push(edit);
  }

  function loginAgain() {
    window.location.replace('/login?next=%2Fadmin%2Faccounts');
  }

  async function loadAccounts(reset) {
    if (loading) return;
    loading = true;
    retryReset = reset;
    listError.hidden = true;
    retry.hidden = true;
    loadingNote.hidden = false;
    if (reset) {
      offset = 0;
      rows.textContent = '';
      rowButtons = [];
      empty.hidden = true;
      more.hidden = true;
    }
    updateControls();
    try {
      const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
      const page = await window.API.get(`/api/admin/accounts?${params.toString()}`);
      if (!page || !Array.isArray(page.accounts)) throw new Error('账号列表格式有误，请稍后重试。');
      page.accounts.forEach(addRow);
      offset += page.accounts.length;
      empty.hidden = offset !== 0;
      more.hidden = page.accounts.length < PAGE_SIZE;
    } catch (failure) {
      if (failure.status === 401) {
        loginAgain();
        return;
      }
      listError.textContent = failure.message || '账号列表取不到，请重试。';
      listError.hidden = false;
      more.hidden = true;
      retry.hidden = false;
    } finally {
      loading = false;
      loadingNote.hidden = true;
      updateControls();
    }
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (saving || loading || !session || session.account.role !== 'admin') return;
    clearMessages();
    let request;
    let editingSelf = false;
    let selfDisabled = false;
    let selfDemoted = false;
    if (selected) {
      const changes = {};
      if (role.value !== selected.role) changes.role = role.value;
      if ((status.value === 'true') !== selected.is_active) changes.is_active = status.value === 'true';
      if (password.value !== '') changes.password = password.value;
      if (Object.keys(changes).length === 0) {
        formError.textContent = '没有需要保存的更改。';
        formError.hidden = false;
        return;
      }
      editingSelf = selected.user_id === session.account.user_id;
      selfDisabled = editingSelf && changes.is_active === false;
      selfDemoted = editingSelf && changes.role !== undefined && changes.role !== 'admin';
      request = () => window.API.patch(`/api/admin/accounts/${encodeURIComponent(selected.user_id)}`, changes);
    } else {
      const payload = { username: username.value.trim(), role: role.value, password: password.value };
      request = () => window.API.post('/api/admin/accounts', payload);
    }
    saving = true;
    updateControls();
    try {
      await request();
      password.value = '';
      if (editingSelf) {
        if (selfDisabled) {
          sessionMessage.textContent = '当前账号已停用，请联系其他管理员重新启用后登录。';
          sessionLogin.textContent = '前往登录';
          sessionLogin.href = '/login';
        } else if (selfDemoted) {
          sessionMessage.textContent = '当前账号的角色已更新，请重新登录。';
          sessionLogin.href = '/login?next=%2Fworkspace';
        }
        workspace.hidden = true;
        sessionEnded.hidden = false;
        sessionEnded.focus();
        return;
      }
      const message = selected ? '账号已更新。' : '账号已创建。';
      beginCreate();
      saved.textContent = message;
      saved.hidden = false;
      await loadAccounts(true);
    } catch (failure) {
      if (failure.status === 401) {
        loginAgain();
        return;
      }
      formError.textContent = failure.message || '保存失败，请重试。';
      formError.hidden = false;
    } finally {
      saving = false;
      updateControls();
    }
  });

  cancel.addEventListener('click', () => { beginCreate(); title.focus(); });
  more.addEventListener('click', () => loadAccounts(false));
  retry.addEventListener('click', () => loadAccounts(retryReset));

  window.SHELL.ready.then((result) => {
    if (!result) return;
    session = result;
    if (session.account.role !== 'admin') {
      workspace.hidden = true;
      denied.hidden = false;
      return;
    }
    workspace.hidden = false;
    denied.hidden = true;
    beginCreate();
    return loadAccounts(true);
  }).catch(() => {
    denied.textContent = '账号信息取不到，请刷新后重试。';
    denied.hidden = false;
  });
})();