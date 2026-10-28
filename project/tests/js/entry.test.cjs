const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const source = readFileSync(path.join(__dirname, '../../src/taces/presentation/static/js/pages/entry.js'), 'utf8');
const tick = () => new Promise(setImmediate);

async function render({ role = 'teacher', courses = [], failures = [], waitForCourses = null } = {}) {
  const elements = new Map();
  const requests = [];
  const redirects = [];
  const csrf = { content: '' };
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      textContent: '', hidden: true, disabled: false, events: {},
      addEventListener(name, handler) { this.events[name] = handler; },
    });
    return elements.get(id);
  }
  const context = vm.createContext({
    document: { getElementById: element, querySelector: () => csrf },
    window: {
      location: { replace(value) { redirects.push(value); } },
      API: {
        async get(route) {
          requests.push(['GET', route]);
          const failure = failures.shift();
          if (failure) throw failure;
          if (route === '/api/courses' && waitForCourses) await waitForCourses();
          return route === '/api/auth/me'
            ? { account: { role, username: 'teacher' }, csrf_token: 'csrf' }
            : { courses };
        },
        async post(route) { requests.push(['POST', route]); },
      },
    },
  });
  vm.runInContext(source, context);
  await tick();
  return { elements, requests, redirects, csrf, courses, failures,
    async click(id) { await element(id).events.click(); await tick(); } };
}

test('workspace transition hides actions while teacher courses are still loading', async () => {
  let release;
  const pending = new Promise(resolve => { release = resolve; });
  const view = await render({ courses: [{ course_id: 'course-1' }], waitForCourses: () => pending });
  assert.equal(view.elements.get('entryTitle').textContent, '正在进入工作区');
  for (const id of ['entryRetry', 'entryLogout', 'entryPassword']) {
    assert.equal(view.elements.get(id).hidden, true, id);
  }
  release();
  await tick();
  assert.deepEqual(view.redirects, ['/teacher/course-1']);
});

test('all actions stay hidden while administrator and auditor redirect', async () => {
  for (const [role, target] of [['admin', '/admin/config'], ['auditor', '/admin/audit']]) {
    const view = await render({ role });
    for (const id of ['entryRetry', 'entryLogout', 'entryPassword']) {
      assert.equal(view.elements.get(id).hidden, true, `${role}: ${id}`);
    }
    assert.deepEqual(view.redirects, [target]);
  }
});

test('retry hides fallback actions until the next course check completes', async () => {
  let release;
  let pending = Promise.resolve();
  const view = await render({ waitForCourses: () => pending });
  assert.equal(view.elements.get('entryLogout').hidden, false);
  pending = new Promise(resolve => { release = resolve; });
  const retrying = view.click('entryRetry');
  await tick();
  assert.equal(view.elements.get('entryTitle').textContent, '正在进入工作区');
  for (const id of ['entryRetry', 'entryLogout', 'entryPassword']) {
    assert.equal(view.elements.get(id).hidden, true, id);
  }
  release();
  await retrying;
  assert.equal(view.elements.get('entryLogout').hidden, false);
});

test('a teacher without courses can retry or log out instead of being stranded', async () => {
  const view = await render();
  assert.match(view.elements.get('entryTitle').textContent, /没有.*课程/);
  assert.equal(view.elements.get('entryRetry').hidden, false);
  assert.equal(view.elements.get('entryLogout').hidden, false);
  assert.equal(view.elements.get('entryPassword').hidden, false);
  assert.equal(view.csrf.content, 'csrf');
  view.courses.push({ course_id: 'course-1', name: '课程' });
  await view.click('entryRetry');
  assert.deepEqual(view.redirects, ['/teacher/course-1']);
});

test('the admin workspace never exposes the password action while redirecting', async () => {
  const view = await render({ role: 'admin' });
  assert.equal(view.elements.get('entryPassword').hidden, true);
  assert.deepEqual(view.redirects, ['/admin/config']);
});

test('logout from an unassigned teacher workspace clears the session', async () => {
  const view = await render();
  await view.click('entryLogout');
  assert.deepEqual(view.requests.at(-1), ['POST', '/api/auth/logout']);
  assert.deepEqual(view.redirects, ['/login']);
});

test('workspace errors provide a retry instead of leaving a dead end', async () => {
  const view = await render({ failures: [{ status: 0 }] });
  assert.match(view.elements.get('entryNote').textContent, /重试/);
  assert.equal(view.elements.get('entryRetry').hidden, false);
  await view.click('entryRetry');
  assert.match(view.elements.get('entryTitle').textContent, /没有.*课程/);
});

test('a course loading error offers recovery only after the failure', async () => {
  const view = await render({ failures: [null, { status: 503 }] });
  assert.match(view.elements.get('entryTitle').textContent, /无法进入/);
  assert.equal(view.elements.get('entryRetry').hidden, false);
  assert.equal(view.elements.get('entryLogout').hidden, false);
  assert.equal(view.elements.get('entryPassword').hidden, false);
});

test('retry keeps previously verified recovery actions if session lookup temporarily fails', async () => {
  const view = await render();
  assert.equal(view.elements.get('entryLogout').hidden, false);
  view.failures.push({ status: 503 });
  await view.click('entryRetry');
  assert.match(view.elements.get('entryTitle').textContent, /无法进入/);
  assert.equal(view.elements.get('entryRetry').hidden, false);
  assert.equal(view.elements.get('entryLogout').hidden, false);
  assert.equal(view.elements.get('entryPassword').hidden, false);
});
