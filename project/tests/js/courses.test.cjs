const assert = require('node:assert/strict');
const { existsSync, readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const script = path.join(__dirname, '../../src/taces/presentation/static/js/pages/courses.js');
const tick = () => new Promise(setImmediate);
const activeTeacher = { user_id: 'teacher-1', username: 'li', role: 'teacher', is_active: true };
const secondTeacher = { user_id: 'teacher-2', username: 'wang', role: 'teacher', is_active: true };
const disabledTeacher = { user_id: 'teacher-3', username: 'disabled', role: 'teacher', is_active: false };

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

async function render({ role = 'admin', accounts = [activeTeacher, secondTeacher, disabledTeacher],
  courses = [{ course_id: 'c1', name: '数据结构', teacher_id: 'teacher-1', term: '2026秋' }],
  failure = null, saveFailure = null, postWait = null, reloadFailure = null } = {}) {
  assert.ok(existsSync(script), 'course management page script is missing');
  let data = courses.map(course => ({ ...course }));
  const elements = new Map();
  const requests = [];
  const redirects = [];
  function element(id) {
    if (!elements.has(id)) elements.set(id, node());
    return elements.get(id);
  }
  const api = {
    async get(route) {
      requests.push({ method: 'GET', route });
      if (failure) { const error = failure; failure = null; throw error; }
      if (route === '/api/courses') return { courses: data.map(course => ({ ...course })) };
      if (route.startsWith('/api/admin/accounts?')) {
        const params = new URLSearchParams(route.split('?')[1]);
        const offset = Number(params.get('offset'));
        const limit = Number(params.get('limit'));
        return { accounts: accounts.slice(offset, offset + limit).map(account => ({ ...account })) };
      }
      throw new Error('Unexpected request: ' + route);
    },
    async post(route, body) {
      requests.push({ method: 'POST', route, body: JSON.parse(JSON.stringify(body)) });
      if (saveFailure) throw saveFailure;
      if (postWait) await postWait;
      data.push({ ...body });
      if (reloadFailure) { failure = reloadFailure; reloadFailure = null; }
      return { course: { ...body } };
    },
    async patch(route, body) {
      requests.push({ method: 'PATCH', route, body: JSON.parse(JSON.stringify(body)) });
      if (saveFailure) throw saveFailure;
      const id = decodeURIComponent(route.split('/').pop());
      const course = data.find(item => item.course_id === id);
      Object.assign(course, body);
      return { course: { ...course } };
    },
  };
  const context = vm.createContext({
    document: { getElementById: element, createElement: node },
    window: { SHELL: { ready: Promise.resolve({ account: { role } }) }, API: api,
      location: { replace(url) { redirects.push(url); } } },
    URLSearchParams,
  });
  vm.runInContext(readFileSync(script, 'utf8'), context);
  await tick();
  await tick();
  return { elements, requests, redirects,
    async submit() { await element('courseForm').events.submit({ preventDefault() {} }); await tick(); },
    async click(id) { await element(id).events.click(); await tick(); } };
}

function editButton(view, index = 0) {
  return view.elements.get('courseRows').children[index].children[3].children[0];
}

test('admin can create a course assigned to an active teacher', async () => {
  const view = await render();
  assert.equal(view.elements.get('courseRows').children[0].children[2].textContent, 'li');
  await view.click('courseCreate');
  assert.equal(view.elements.get('courseDialog').open, true);
  assert.deepEqual(view.elements.get('courseTeacher').children.map(option => option.value), ['', 'teacher-1', 'teacher-2']);
  view.elements.get('courseId').value = 'CS202';
  view.elements.get('courseName').value = '软件工程';
  view.elements.get('courseTerm').value = '2026秋';
  view.elements.get('courseTeacher').value = 'teacher-2';
  await view.submit();
  assert.deepEqual(view.requests.find(request => request.method === 'POST'), {
    method: 'POST', route: '/api/admin/courses',
    body: { course_id: 'CS202', name: '软件工程', term: '2026秋', teacher_id: 'teacher-2' },
  });
  assert.equal(view.elements.get('courseDialog').open, false);
  assert.equal(view.elements.get('courseRows').children.length, 2);
  assert.equal(view.elements.get('courseSaved').hidden, false);
});

test('editing a course transfers only the changed teacher and refreshes the list', async () => {
  const view = await render();
  editButton(view).events.click();
  assert.equal(view.elements.get('courseDialog').open, true);
  assert.equal(view.elements.get('courseId').readOnly, true);
  assert.equal(view.elements.get('courseTeacher').value, 'teacher-1');
  view.elements.get('courseTeacher').value = 'teacher-2';
  await view.submit();
  assert.deepEqual(view.requests.find(request => request.method === 'PATCH'), {
    method: 'PATCH', route: '/api/admin/courses/c1', body: { teacher_id: 'teacher-2' },
  });
  assert.equal(view.elements.get('courseRows').children[0].children[2].textContent, 'wang');
  assert.equal(view.elements.get('courseDialog').open, false);
});

test('only enabled teachers can be chosen even when a current teacher is disabled', async () => {
  const view = await render({ accounts: [disabledTeacher], courses: [
    { course_id: 'c1', name: '课程', teacher_id: 'teacher-3', term: '2026秋' },
  ] });
  assert.match(view.elements.get('courseRows').children[0].children[2].textContent, /disabled.*停用/);
  editButton(view).events.click();
  assert.equal(view.elements.get('courseTeacher').value, '');
  assert.equal(view.elements.get('courseTeacherHint').hidden, false);
  await view.submit();
  assert.equal(view.requests.some(request => request.method === 'PATCH'), false);
  assert.equal(view.elements.get('courseFormError').hidden, false);
});

test('teacher choices include accounts on later API pages', async () => {
  const others = Array.from({ length: 100 }, (_, index) => ({
    user_id: `admin-${index}`, username: `admin-${index}`, role: 'admin', is_active: true,
  }));
  const view = await render({ accounts: [...others, secondTeacher] });
  await view.click('courseCreate');
  assert.deepEqual(view.elements.get('courseTeacher').children.map(option => option.value), ['', 'teacher-2']);
  assert.ok(view.requests.some(request => request.route.endsWith('offset=100')));
});

test('a failed save leaves the edit dialog and error available', async () => {
  const view = await render({ saveFailure: { status: 409, message: '课程标识已存在。' } });
  await view.click('courseCreate');
  view.elements.get('courseId').value = 'c1';
  view.elements.get('courseName').value = '课程';
  view.elements.get('courseTerm').value = '2026秋';
  view.elements.get('courseTeacher').value = 'teacher-1';
  await view.submit();
  assert.equal(view.elements.get('courseDialog').open, true);
  assert.match(view.elements.get('courseFormError').textContent, /已存在/);
});

test('failed loading can be retried without exposing incomplete assignment choices', async () => {
  const view = await render({ failure: { status: 503, message: '暂不可用' } });
  assert.equal(view.elements.get('courseCreate').disabled, true);
  assert.equal(view.elements.get('coursesRetry').hidden, false);
  await view.click('coursesRetry');
  assert.equal(view.elements.get('courseCreate').disabled, false);
  assert.equal(view.elements.get('courseRows').children.length, 1);
});

test('non-admin accounts do not request courses or teacher accounts', async () => {
  const view = await render({ role: 'teacher' });
  assert.deepEqual(view.requests, []);
  assert.equal(view.elements.get('courseWorkspace').hidden, true);
  assert.equal(view.elements.get('courseDenied').hidden, false);
});


test('an unchanged course is not submitted', async () => {
  const view = await render();
  editButton(view).events.click();
  await view.submit();
  assert.equal(view.requests.some(request => request.method === 'PATCH'), false);
  assert.match(view.elements.get('courseFormError').textContent, /没有需要保存/);
  assert.equal(view.elements.get('courseDialog').open, true);
});

test('saving blocks duplicate requests and prevents closing until it settles', async () => {
  let release;
  const postWait = new Promise(resolve => { release = resolve; });
  const view = await render({ postWait });
  await view.click('courseCreate');
  view.elements.get('courseId').value = 'CS202';
  view.elements.get('courseName').value = '软件工程';
  view.elements.get('courseTerm').value = '2026秋';
  view.elements.get('courseTeacher').value = 'teacher-1';
  const pending = view.submit();
  await tick();
  await view.submit();
  await view.click('courseCancel');
  let prevented = false;
  view.elements.get('courseDialog').events.cancel({ preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
  assert.equal(view.elements.get('courseDialog').open, true);
  assert.equal(view.requests.filter(request => request.method === 'POST').length, 1);
  release();
  await pending;
  assert.equal(view.elements.get('courseDialog').open, false);
});

test('a successful save with a failed refresh offers retry and disables stale actions', async () => {
  const view = await render({ reloadFailure: { status: 503, message: '重新加载失败' } });
  await view.click('courseCreate');
  view.elements.get('courseId').value = 'CS202';
  view.elements.get('courseName').value = '软件工程';
  view.elements.get('courseTerm').value = '2026秋';
  view.elements.get('courseTeacher').value = 'teacher-1';
  await view.submit();
  assert.equal(view.elements.get('courseSaved').hidden, false);
  assert.equal(view.elements.get('courseCreate').disabled, true);
  assert.equal(editButton(view).disabled, true);
  assert.equal(view.elements.get('coursesRetry').hidden, false);
  await view.click('coursesRetry');
  assert.equal(view.elements.get('courseRows').children.length, 2);
  assert.equal(view.elements.get('courseCreate').disabled, false);
});

test('an expired session returns to login from course management', async () => {
  const view = await render({ failure: { status: 401 } });
  assert.deepEqual(view.redirects, ['/login?next=%2Fadmin%2Fcourses']);
});
