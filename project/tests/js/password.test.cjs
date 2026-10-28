const assert = require('node:assert/strict');
const { existsSync, readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const file = path.join(__dirname, '../../src/taces/presentation/static/js/pages/password.js');
const tick = () => new Promise(setImmediate);

async function page({ role = 'teacher', failure = null, delay = null } = {}) {
  assert.ok(existsSync(file), 'staff password script must exist');
  const fields = new Map(), calls = [], redirects = [];
  function el(id) {
    if (!fields.has(id)) fields.set(id, { value: '', hidden: true, disabled: false, events: {},
      addEventListener(name, fn) { this.events[name] = fn; }, focus() { this.focused = true; } });
    return fields.get(id);
  }
  const context = vm.createContext({ document: { getElementById: el }, window: {
    SHELL: { ready: Promise.resolve({ account: { role } }) },
    API: { async post(route, body) { calls.push([route, JSON.parse(JSON.stringify(body))]);
      if (delay) await delay; if (failure) throw failure; return { login_required: true }; } },
    location: { replace(url) { redirects.push(url); } },
  } });
  vm.runInContext(readFileSync(file, 'utf8'), context);
  await tick();
  return { fields, calls, redirects, async submit() { await el('passwordForm').events.submit({ preventDefault() {} }); } };
}

for (const role of ['admin', 'teacher', 'auditor']) {
  test(`${role} can change their own password and is asked to sign in again`, async () => {
    const view = await page({ role });
    view.fields.get('currentPassword').value = 'old-password';
    view.fields.get('newPassword').value = 'new-password-2026';
    view.fields.get('confirmPassword').value = 'new-password-2026';
    await view.submit();
    assert.deepEqual(view.calls, [['/api/auth/password', { current_password: 'old-password', new_password: 'new-password-2026' }]]);
    assert.equal(view.fields.get('passwordSuccess').hidden, false);
    assert.match(view.fields.get('passwordSuccess').textContent, /重新登录/);
    assert.equal(view.fields.get('currentPassword').value, '');
    assert.equal(view.fields.get('newPassword').value, '');
    assert.equal(view.fields.get('confirmPassword').value, '');
  });
}

test('mismatched new passwords do not send a request', async () => {
  const view = await page();
  view.fields.get('currentPassword').value = 'old-password';
  view.fields.get('newPassword').value = 'new-password-2026';
  view.fields.get('confirmPassword').value = 'another-password';
  await view.submit();
  assert.deepEqual(view.calls, []);
  assert.match(view.fields.get('passwordError').textContent, /不一致/);
});

test('wrong current password keeps the form available', async () => {
  const view = await page({ failure: { status: 403, message: '当前密码不正确。' } });
  view.fields.get('currentPassword').value = 'wrong';
  view.fields.get('newPassword').value = 'new-password-2026';
  view.fields.get('confirmPassword').value = 'new-password-2026';
  await view.submit();
  assert.match(view.fields.get('passwordError').textContent, /当前密码不正确/);
  assert.equal(view.fields.get('passwordFields').disabled, false);
  assert.equal(view.fields.get('passwordSuccess').hidden, true);
});

test('a pending password change cannot be submitted twice', async () => {
  let resolve;
  const view = await page({ delay: new Promise(done => { resolve = done; }) });
  view.fields.get('currentPassword').value = 'old-password';
  view.fields.get('newPassword').value = 'new-password-2026';
  view.fields.get('confirmPassword').value = 'new-password-2026';
  const pending = view.submit();
  await tick();
  await view.submit();
  assert.equal(view.calls.length, 1);
  resolve();
  await pending;
});


test('password length follows Unicode characters rather than UTF-16 units', async () => {
  const view = await page();
  const password = '😀'.repeat(128);
  view.fields.get('currentPassword').value = 'old-password';
  view.fields.get('newPassword').value = password;
  view.fields.get('confirmPassword').value = password;
  await view.submit();
  assert.equal(view.calls[0][1].new_password, password);
});
