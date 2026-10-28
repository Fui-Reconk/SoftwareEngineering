const assert = require('node:assert/strict');
const { existsSync, readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const scriptPath = path.join(__dirname, '../../src/taces/presentation/static/js/pages/accounts.js');
const tick = () => new Promise(setImmediate);

function node() {
  let text = '';
  return {
    children: [], events: {}, attributes: {}, hidden: false, disabled: false, open: false, value: '',
    get textContent() { return text; },
    set textContent(value) { text = value; this.children = []; },
    append(...children) { this.children.push(...children); },
    appendChild(child) { this.children.push(child); },
    addEventListener(name, handler) { this.events[name] = handler; },
    setAttribute(name, value) { this.attributes[name] = value; },
    focus() { this.focused = true; },
    showModal() { this.open = true; },
    close() { if (this.open) { this.open = false; this.events.close?.(); } },
  };
}

async function render({ role = 'admin', accounts, patchFailure = null, getFailures = [], postWait = null } = {}) {
  assert.ok(existsSync(scriptPath), 'account management page script is missing');
  let data = (accounts || [
    { user_id: 'self', username: 'admin', role: 'admin', is_active: true },
    { user_id: 'teacher-1', username: 'teacher', role: 'teacher', is_active: true },
  ]).map(account => ({ ...account }));
  const elements = new Map();
  const requests = [];
  const redirects = [];
  function element(id) {
    if (!elements.has(id)) elements.set(id, node());
    return elements.get(id);
  }
  element('accountRole').value = 'teacher';
  element('accountStatus').value = 'true';
  const api = {
    async get(route) {
      requests.push({ method: 'GET', route });
      const failure = getFailures.shift();
      if (failure) throw failure;
      const params = new URLSearchParams(route.split('?')[1]);
      const offset = Number(params.get('offset'));
      const limit = Number(params.get('limit'));
      return { accounts: data.slice(offset, offset + limit).map(item => ({ ...item })) };
    },
    async post(route, body) {
      requests.push({ method: 'POST', route, body: JSON.parse(JSON.stringify(body)) });
      if (postWait) await postWait;
      const account = { user_id: 'created', username: body.username, role: body.role, is_active: true };
      data.push(account);
      return { account };
    },
    async patch(route, body) {
      requests.push({ method: 'PATCH', route, body: JSON.parse(JSON.stringify(body)) });
      if (patchFailure) throw patchFailure;
      const id = decodeURIComponent(route.split('/').pop());
      const account = data.find(item => item.user_id === id);
      if ('role' in body) account.role = body.role;
      if ('is_active' in body) account.is_active = body.is_active;
      return { account: { ...account } };
    },
  };
  const context = vm.createContext({
    document: { getElementById: element, createElement: node },
    window: { SHELL: { ready: Promise.resolve({ account: { user_id: 'self', role } }) }, API: api,
      location: { replace(url) { redirects.push(url); } } },
    URLSearchParams,
  });
  vm.runInContext(readFileSync(scriptPath, 'utf8'), context);
  await tick();
  return { elements, requests, redirects, async submit() {
    await element('accountForm').events.submit({ preventDefault() {} });
    await tick();
  }, async click(id) { await element(id).events.click(); await tick(); } };
}

function editButton(view, index) {
  return view.elements.get('accountRows').children[index].children[3].children[0];
}

test('admin can create an account with the fields required by the real API', async () => {
  const view = await render();
  await view.click('accountCreate');
  view.elements.get('accountUsername').value = 'new_teacher';
  view.elements.get('accountRole').value = 'teacher';
  view.elements.get('accountPassword').value = 'Long-password-2026!';
  await view.submit();
  assert.deepEqual(view.requests.find(request => request.method === 'POST'), {
    method: 'POST', route: '/api/admin/accounts', body: {
      username: 'new_teacher', role: 'teacher', password: 'Long-password-2026!',
    },
  });
  assert.equal(view.elements.get('accountPassword').value, '');
  assert.equal(view.elements.get('accountRows').children.length, 3);
  assert.equal(view.elements.get('accountSaved').hidden, false);
  assert.equal(view.elements.get('accountDialog').open, false);
});

test('editing another account sends only changed role, status and password', async () => {
  const view = await render();
  editButton(view, 1).events.click();
  assert.equal(view.elements.get('accountDialog').open, true);
  view.elements.get('accountRole').value = 'auditor';
  view.elements.get('accountStatus').value = 'false';
  view.elements.get('accountPassword').value = 'Reset-password-2026!';
  await view.submit();
  assert.deepEqual(view.requests.find(request => request.method === 'PATCH'), {
    method: 'PATCH', route: '/api/admin/accounts/teacher-1', body: {
      role: 'auditor', is_active: false, password: 'Reset-password-2026!',
    },
  });
  assert.equal(view.elements.get('accountPassword').value, '');
});

test('saving an unchanged account does not revoke its sessions', async () => {
  const view = await render();
  editButton(view, 1).events.click();
  await view.submit();
  assert.equal(view.requests.some(request => request.method === 'PATCH'), false);
  assert.match(view.elements.get('accountFormError').textContent, /没有.*更改/);
});

test('saving the current admin account asks for login after session revocation', async () => {
  const view = await render();
  editButton(view, 0).events.click();
  view.elements.get('accountPassword').value = 'New-password-2026!';
  await view.submit();
  assert.equal(view.elements.get('accountSessionEnded').hidden, false);
  assert.equal(view.elements.get('accountWorkspace').hidden, true);
  assert.equal(view.requests.filter(request => request.method === 'GET').length, 1);
});

test('backend conflicts remain visible and leave the edit form available', async () => {
  const view = await render({ patchFailure: { status: 409, message: '请先转移该教师的课程，再修改角色。' } });
  editButton(view, 1).events.click();
  view.elements.get('accountRole').value = 'auditor';
  await view.submit();
  assert.match(view.elements.get('accountFormError').textContent, /先转移/);
  assert.equal(view.elements.get('accountFormError').hidden, false);
  assert.equal(view.elements.get('accountFields').disabled, false);
  assert.equal(view.elements.get('accountDialog').open, true);
});

test('non-admin roles cannot load or use account management', async () => {
  const view = await render({ role: 'auditor' });
  assert.equal(view.requests.length, 0);
  assert.equal(view.elements.get('accountDenied').hidden, false);
  assert.equal(view.elements.get('accountWorkspace').hidden, true);
});

test('account lists can load beyond the first API page', async () => {
  const many = Array.from({ length: 51 }, (_, index) => ({
    user_id: `id-${index}`, username: `user-${index}`, role: 'teacher', is_active: true,
  }));
  const view = await render({ accounts: many });
  assert.equal(view.elements.get('accountRows').children.length, 50);
  assert.equal(view.elements.get('accountsMore').hidden, false);
  await view.click('accountsMore');
  assert.equal(view.elements.get('accountRows').children.length, 51);
  assert.equal(view.elements.get('accountsMore').hidden, true);
  assert.match(view.requests[1].route, /offset=50/);
});


test('a failed initial list request can be retried', async () => {
  const view = await render({ getFailures: [{ status: 0, message: '连不上服务，请重试。' }] });
  assert.match(view.elements.get('accountsError').textContent, /连不上服务/);
  assert.equal(view.elements.get('accountsRetry').hidden, false);
  await view.click('accountsRetry');
  assert.equal(view.elements.get('accountRows').children.length, 2);
  assert.equal(view.elements.get('accountsError').hidden, true);
  assert.equal(view.elements.get('accountsRetry').hidden, true);
});

test('retrying a failed next page preserves previously loaded accounts', async () => {
  const many = Array.from({ length: 51 }, (_, index) => ({
    user_id: `id-${index}`, username: `user-${index}`, role: 'teacher', is_active: true,
  }));
  const view = await render({ accounts: many, getFailures: [null, { status: 0, message: '加载失败' }] });
  await view.click('accountsMore');
  assert.equal(view.elements.get('accountRows').children.length, 50);
  assert.equal(view.elements.get('accountsRetry').hidden, false);
  await view.click('accountsRetry');
  assert.equal(view.elements.get('accountRows').children.length, 51);
  assert.deepEqual(view.requests.map(request => new URLSearchParams(request.route.split('?')[1]).get('offset')),
    ['0', '50', '50']);
  assert.equal(view.elements.get('accountsRetry').hidden, true);
});

test('an expired session returns the administrator to login', async () => {
  const view = await render({ patchFailure: { status: 401, message: '会话已过期。' } });
  editButton(view, 1).events.click();
  view.elements.get('accountStatus').value = 'false';
  await view.submit();
  assert.deepEqual(view.redirects, ['/login?next=%2Fadmin%2Faccounts']);
});


test('disabling the current account explains how it can be restored', async () => {
  const view = await render();
  editButton(view, 0).events.click();
  view.elements.get('accountStatus').value = 'false';
  await view.submit();
  assert.match(view.elements.get('accountSessionMessage')?.textContent || '', /停用.*其他管理员.*启用/);
  assert.equal(view.elements.get('accountSessionLogin')?.href, '/login');
});

test('changing the current admin role returns to the workspace after login', async () => {
  const view = await render();
  editButton(view, 0).events.click();
  view.elements.get('accountRole').value = 'auditor';
  await view.submit();
  assert.match(view.elements.get('accountSessionMessage')?.textContent || '', /角色.*重新登录/);
  assert.equal(view.elements.get('accountSessionLogin')?.href, '/login?next=%2Fworkspace');
});


test('create opens a fresh dialog and cancel clears sensitive input', async () => {
  const view = await render();
  assert.equal(view.elements.get('accountDialog').open, false);
  await view.click('accountCreate');
  assert.equal(view.elements.get('accountDialog').open, true);
  assert.equal(view.elements.get('accountFormTitle').textContent, '新建账号');
  view.elements.get('accountUsername').value = 'draft';
  view.elements.get('accountPassword').value = 'Draft-password-2026!';
  await view.click('accountCancel');
  assert.equal(view.elements.get('accountDialog').open, false);
  assert.equal(view.elements.get('accountPassword').value, '');
  await view.click('accountCreate');
  assert.equal(view.elements.get('accountUsername').value, '');
  assert.equal(view.elements.get('accountPassword').value, '');
});

test('editing opens a populated dialog and close returns to the list', async () => {
  const view = await render();
  editButton(view, 1).events.click();
  assert.equal(view.elements.get('accountDialog').open, true);
  assert.equal(view.elements.get('accountUsername').value, 'teacher');
  assert.equal(view.elements.get('accountFormTitle').textContent, '编辑账号');
  await view.click('accountClose');
  assert.equal(view.elements.get('accountDialog').open, false);
  assert.equal(view.requests.some(request => request.method === 'PATCH'), false);
});

test('Escape can close the dialog and clears the password', async () => {
  const view = await render();
  await view.click('accountCreate');
  view.elements.get('accountPassword').value = 'Draft-password-2026!';
  let prevented = false;
  view.elements.get('accountDialog').events.cancel({ preventDefault() { prevented = true; } });
  if (!prevented) view.elements.get('accountDialog').close();
  assert.equal(prevented, false);
  assert.equal(view.elements.get('accountDialog').open, false);
  assert.equal(view.elements.get('accountPassword').value, '');
});

test('a pending save prevents closing the dialog until the request settles', async () => {
  let release;
  const postWait = new Promise(resolve => { release = resolve; });
  const view = await render({ postWait });
  await view.click('accountCreate');
  view.elements.get('accountUsername').value = 'new_teacher';
  view.elements.get('accountPassword').value = 'Long-password-2026!';
  const pending = view.submit();
  await tick();
  let prevented = false;
  view.elements.get('accountDialog').events.cancel({ preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
  assert.equal(view.elements.get('accountClose').disabled, true);
  assert.equal(view.elements.get('accountDialog').open, true);
  release();
  await pending;
  assert.equal(view.elements.get('accountDialog').open, false);
});
