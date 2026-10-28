const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const source = readFileSync(path.join(__dirname,
  '../../src/taces/presentation/static/js/shell.js'), 'utf8');

async function render(role, { pathname = '/admin/config', courses = [], failure = false, unauthorized = false } = {}) {
  const elements = new Map();
  const requests = [];
  const windowEvents = {};
  let redirect;
  function node() {
    let value = '';
    const classes = new Set();
    return { children: [], attributes: {}, events: {}, hidden: false,
      get textContent() { return value; },
      set textContent(text) { value = text; this.children = []; },
      append(...children) { this.children.push(...children); },
      appendChild(child) { this.children.push(child); },
      setAttribute(name, value) { this.attributes[name] = value; },
      addEventListener(name, handler) { this.events[name] = handler; },
      classList: {
        toggle(name, active) { if (active) classes.add(name); else classes.delete(name); },
        contains(name) { return classes.has(name); },
      },
    };
  }
  function element(id) {
    if (!elements.has(id)) elements.set(id, node());
    return elements.get(id);
  }
  element('staffNav').hidden = true;
  element('courseSection').hidden = true;
  const csrf = { content: '' };
  const context = vm.createContext({
    document: {
      getElementById: element, createElement: node, addEventListener() {},
      querySelector(selector) {
        return selector.includes('csrf-token') ? csrf : { dataset: { course: 'mine' } };
      },
    },
    window: {
      innerWidth: 390,
      addEventListener(name, handler) { windowEvents[name] = handler; },
      location: { pathname, search: '', replace(value) { redirect = value; } },
      API: {
        async get(route) {
          requests.push(route);
          if (route === '/api/auth/me') {
            if (unauthorized) throw { status: 401 };
            return { account: { username: 'test_' + role, role }, csrf_token: 'test-csrf' };
          }
          if (route === '/api/courses') {
            if (failure) throw { status: 503 };
            return { courses };
          }
          throw new Error('Unexpected request: ' + route);
        },
        async post(route) { requests.push(route); },
      },
    },
  });
  vm.runInContext(source, context);
  await context.window.SHELL.ready;
  return { elements, requests, csrf, redirect: () => redirect,
    resize(width) { context.window.innerWidth = width; windowEvents.resize?.(); } };
}

test('admin has account management, configuration and audit destinations without fetching teacher courses', async () => {
  const view = await render('admin', { pathname: '/admin/audit' });
  assert.deepEqual(view.requests, ['/api/auth/me']);
  const nav = view.elements.get('staffNav');
  assert.equal(nav.hidden, false);
  assert.deepEqual(nav.children.map((link) => [link.textContent, link.href]), [
    ['账号管理', '/admin/accounts'], ['课程管理', '/admin/courses'],
    ['隐私参数', '/admin/config'], ['查询留痕', '/admin/audit'],
  ]);
  assert.equal(nav.children[3].attributes['aria-current'], 'page');
  assert.equal(view.elements.get('courseSection').hidden, true);
  assert.equal(view.csrf.content, 'test-csrf');
});

test('account management is marked as the current destination for an admin', async () => {
  const view = await render('admin', { pathname: '/admin/accounts' });
  assert.equal(view.elements.get('staffNav').children[0].attributes['aria-current'], 'page');
});

test('course management is marked as the current destination for an admin', async () => {
  const view = await render('admin', { pathname: '/admin/courses' });
  assert.equal(view.elements.get('staffNav').children[1].attributes['aria-current'], 'page');
});

test('auditor has only the audit destination and never calls the courses endpoint', async () => {
  const view = await render('auditor', { pathname: '/admin/audit' });
  assert.deepEqual(view.requests, ['/api/auth/me']);
  assert.deepEqual(view.elements.get('staffNav').children.map((link) => link.href), ['/admin/audit']);
  assert.equal(view.elements.get('staffNav').children[0].attributes['aria-current'], 'page');
  assert.equal(view.elements.get('courseSection').hidden, true);
});

test('teacher retains owned course navigation and its current course', async () => {
  const view = await render('teacher', { pathname: '/teacher/mine', courses: [
    { course_id: 'mine', name: '我的课程' }, { course_id: 'another', name: '另一门课程' },
  ] });
  assert.deepEqual(view.requests, ['/api/auth/me', '/api/courses']);
  assert.deepEqual(view.elements.get('staffNav').children.map(link => link.href), ['/teacher/exports/history']);
  assert.equal(view.elements.get('courseSection').hidden, false);
  const links = view.elements.get('courseList').children;
  assert.deepEqual(links.map((link) => link.href), ['/teacher/mine', '/teacher/another']);
  assert.equal(links[0].attributes['aria-current'], 'page');
});

test('teacher without courses sees an explicit empty state', async () => {
  const view = await render('teacher');
  assert.match(view.elements.get('courseList').textContent, /还没有/);
});

test('course loading failure leaves account and logout available', async () => {
  const view = await render('teacher', { failure: true });
  assert.match(view.elements.get('courseList').textContent, /取不到/);
  assert.equal(view.elements.get('accountBox').children[0].textContent, 'test_teacher');
  await view.elements.get('signOut').events.click();
  assert.equal(view.redirect(), '/login');
});

test('an expired session redirects to login before creating any navigation', async () => {
  const view = await render('admin', { unauthorized: true });
  assert.equal(view.redirect(), '/login?next=%2Fadmin%2Fconfig');
  assert.equal(view.elements.get('staffNav').hidden, true);
  assert.equal(view.elements.get('courseSection').hidden, true);
  assert.deepEqual(view.requests, ['/api/auth/me']);
});

test('the mobile menu exposes its open and closed state', async () => {
  const view = await render('admin');
  const toggle = view.elements.get('menuToggle');
  const backdrop = view.elements.get('backdrop');
  toggle.events.click();
  assert.equal(toggle.attributes['aria-expanded'], 'true');
  assert.equal(toggle.attributes['aria-label'], '收起工作区导航');
  assert.equal(backdrop.hidden, false);
  backdrop.events.click();
  assert.equal(toggle.attributes['aria-expanded'], 'false');
  assert.equal(toggle.attributes['aria-label'], '展开工作区导航');
  assert.equal(backdrop.hidden, true);
});

test('resizing an open mobile drawer to desktop clears the backdrop', async () => {
  const view = await render('teacher');
  view.elements.get('menuToggle').events.click();
  assert.equal(view.elements.get('backdrop').hidden, false);
  view.resize(1440);
  assert.equal(view.elements.get('backdrop').hidden, true);
  assert.equal(view.elements.get('menuToggle').attributes['aria-expanded'], 'false');
});


test('snapshot export is available in teacher navigation without opening a course board', async () => {
  const view = await render('teacher', { pathname: '/teacher/exports/history' });
  assert.deepEqual(view.requests, ['/api/auth/me', '/api/courses']);
  assert.equal(view.elements.get('staffNav').children[0].textContent, '导出快照');
  assert.equal(view.elements.get('staffNav').children[0].attributes['aria-current'], 'page');
});
