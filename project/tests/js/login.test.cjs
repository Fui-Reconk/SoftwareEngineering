const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { after, before, test } = require('node:test');
const vm = require('node:vm');

const project = path.resolve(__dirname, '../..');
const scripts = path.join(project, 'src/taces/presentation/static/js');
const password = 'Taces-demo-2026!';

function loginPage(username, secret, fetch, search = '') {
  let submit;
  let destination;
  const button = { disabled: false };
  const error = { hidden: true, textContent: '' };
  const form = {
    username: { value: username }, password: { value: secret },
    querySelector() { return button; },
    addEventListener(name, handler) { if (name === 'submit') submit = handler; },
  };
  const context = vm.createContext({
    fetch, setTimeout, URLSearchParams,
    document: {
      querySelector() { return null; },
      getElementById(id) {
        return { loginForm: form, loginError: error, entryNote: error }[id];
      },
    },
    window: {
      location: {
        search,
        assign(value) { destination = value; },
        replace(value) { destination = value; },
      },
    },
  });
  // Load exactly the same transport, fixture data and login handler as the page.
  for (const file of ['api.js', 'mock.js', 'pages/login.js']) {
    vm.runInContext(readFileSync(path.join(scripts, file), 'utf8'), context);
  }
  return {
    context, error, button,
    submit: () => submit({ preventDefault() {} }),
    destination: () => destination,
  };
}

test('the default login page sends demo credentials to the server instead of the old mock password gate', async () => {
  const requests = [];
  const page = loginPage('demo_teacher', password, async (route, options) => {
    requests.push({ route, options });
    return { ok: true, json: async () => ({ data: { account: { username: 'demo_teacher' } } }) };
  });
  await page.submit();
  assert.equal(requests.length, 1, 'the page must call the actual login endpoint');
  assert.equal(requests[0].route, '/api/auth/login');
  assert.equal(requests[0].options.headers['X-TACES-Request'], '1');
  assert.equal(requests[0].options.credentials, 'include');
  assert.deepEqual(JSON.parse(requests[0].options.body), { username: 'demo_teacher', password });
  assert.equal(page.error.hidden, true);
  assert.equal(page.destination(), '/workspace');
});

test('login respects a safe next destination and rejects a protocol-relative one', async () => {
  const fetch = async () => ({ ok: true, json: async () => ({ data: {} }) });
  const requested = loginPage('teacher', 'password', fetch, '?next=%2Fteacher%2Fcourse');
  await requested.submit();
  assert.equal(requested.destination(), '/teacher/course');

  const external = loginPage('teacher', 'password', fetch, '?next=%2F%2Fexample.com');
  await external.submit();
  assert.equal(external.destination(), '/workspace');
});

test('an expired workspace session returns to login with the workspace as next', async () => {
  let destination;
  const context = vm.createContext({
    document: { getElementById: () => ({ textContent: '' }) },
    window: {
      API: { get: async () => { throw { status: 401 }; } },
      location: { replace: (value) => { destination = value; } },
    },
  });
  vm.runInContext(readFileSync(path.join(scripts, 'pages/entry.js'), 'utf8'), context);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(destination, '/login?next=/workspace');
});

let server;
let base;
let serverExit;
let diagnostics = '';

before(async () => {
  // Run a real HTTP server and normal salted password hashing on temporary DBs.
  const python = process.env.TACES_TEST_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
  server = spawn(python, ['-u', '-c', `
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from werkzeug.serving import make_server
sys.path.insert(0, str(Path('src').resolve()))
from taces import create_app
from taces.business.courses.service import CourseService
with TemporaryDirectory(prefix='taces-page-login-') as directory:
    app = create_app({'TESTING': True, 'DATA_DIR': directory})
    db = app.extensions['taces_database']
    db.initialize()
    auth = app.extensions['taces_auth']
    password = 'Taces-demo-2026!'
    auth.bootstrap_admin('demo_admin', password)
    token, _ = auth.login('demo_admin', password)
    for username, role, course in [('demo_teacher','teacher','demo-main'),
                                   ('demo_other','teacher','demo-other'),
                                   ('demo_auditor','auditor',None),
                                   ('demo_disabled','teacher',None)]:
        account = auth.create_account(token, username, password, role)
        if course:
            CourseService(db, auth).create(token, {'course_id':course,'name':course,
                'teacher_id':account['user_id'],'term':'synthetic'})
        if username == 'demo_disabled':
            auth.update_account(token, account['user_id'], {'is_active':False})
    http = make_server('127.0.0.1', 0, app)
    worker = Thread(target=http.serve_forever, daemon=True)
    worker.start()
    print('http://127.0.0.1:' + str(http.server_port), flush=True)
    try:
        sys.stdin.readline()
    finally:
        http.shutdown()
        worker.join(timeout=5)
        http.server_close()
`], { cwd: project, stdio: ['pipe', 'pipe', 'pipe'], env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
  server.stderr.setEncoding('utf8');
  server.stderr.on('data', (chunk) => { diagnostics += chunk; });
  serverExit = new Promise((resolve) => server.once('exit', resolve));
  base = await new Promise((resolve, reject) => {
    let output = '';
    const timeout = setTimeout(() => reject(new Error(`HTTP server did not start: ${diagnostics}`)), 20000);
    server.once('error', (error) => { clearTimeout(timeout); reject(error); });
    server.once('exit', (code) => { clearTimeout(timeout); reject(new Error(`HTTP server exited ${code}: ${diagnostics}`)); });
    server.stdout.setEncoding('utf8');
    server.stdout.on('data', (chunk) => {
      output += chunk;
      const url = output.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (url) { clearTimeout(timeout); resolve(url[0]); }
    });
  });
});

after(async () => {
  if (!server || !server.pid) return;
  server.stdin.end();
  let timeout;
  try {
    const code = await Promise.race([
      serverExit,
      new Promise((_, reject) => {
        timeout = setTimeout(() => { server.kill(); reject(new Error('HTTP server did not shut down')); }, 10000);
      }),
    ]);
    assert.equal(code, 0, diagnostics);
  } finally {
    clearTimeout(timeout);
  }
});

function browserFetch() {
  let cookie = '';
  return async (route, options = {}) => {
    const headers = { ...options.headers };
    if (cookie) headers.Cookie = cookie;
    const response = await fetch(base + route, { ...options, headers });
    const session = response.headers.get('set-cookie');
    if (session) cookie = session.split(';')[0];
    return response;
  };
}

for (const [username, role, destination] of [
  ['demo_admin', 'admin', '/admin/config'],
  ['demo_teacher', 'teacher', '/teacher/demo-main'],
  ['demo_other', 'teacher', '/teacher/demo-other'],
  ['demo_auditor', 'auditor', '/admin/audit'],
]) {
  test(`the real login page establishes a cookie session and routes ${username} correctly`, async () => {
    const page = loginPage(username, password, browserFetch());
    await page.submit();
    assert.equal(page.error.hidden, true, page.error.textContent);
    assert.equal(page.destination(), '/workspace');
    const session = await page.context.window.API.get('/api/auth/me');
    assert.equal(session.account.username, username);
    assert.equal(session.account.role, role);
    vm.runInContext(readFileSync(path.join(scripts, 'pages/entry.js'), 'utf8'), page.context);
    const deadline = Date.now() + 5000;
    while (page.destination() === '/workspace' && page.error.hidden && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 10));
    }
    assert.equal(page.destination(), destination, page.error.textContent);
  });
}

for (const [name, username, secret] of [
  ['old mock password', 'demo_teacher', 'taces2026'],
  ['wrong password', 'demo_teacher', 'wrong-password'],
  ['disabled account', 'demo_disabled', password],
]) {
  test(`the real login page rejects ${name} and displays the backend error`, async () => {
    const page = loginPage(username, secret, browserFetch());
    await page.submit();
    assert.equal(page.destination(), undefined);
    assert.equal(page.error.hidden, false);
    assert.equal(page.button.disabled, false);
    assert.equal(page.error.textContent, '用户名或密码不正确。');
  });
}
