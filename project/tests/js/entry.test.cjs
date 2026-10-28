const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const source = readFileSync(path.join(__dirname, '../../src/taces/presentation/static/js/pages/entry.js'), 'utf8');
const tick = () => new Promise(setImmediate);

async function render({ role = 'teacher', courses = [], failures = [] } = {}) {
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
  return { elements, requests, redirects, csrf, courses,
    async click(id) { await element(id).events.click(); await tick(); } };
}

test('a teacher without courses can retry or log out instead of being stranded', async () => {
  const view = await render();
  assert.match(view.elements.get('entryTitle').textContent, /没有.*课程/);
  assert.equal(view.elements.get('entryRetry').hidden, false);
  assert.equal(view.elements.get('entryLogout').hidden, false);
  assert.equal(view.csrf.content, 'csrf');
  view.courses.push({ course_id: 'course-1', name: '课程' });
  await view.click('entryRetry');
  assert.deepEqual(view.redirects, ['/teacher/course-1']);
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
