const assert = require('node:assert/strict');
const { existsSync, readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const file = path.join(__dirname, '../../src/taces/presentation/static/js/pages/exports.js');
const tick = () => new Promise(setImmediate);

async function page({ role = 'teacher', courses = [{course_id: 'course 1', name: '课程 A'}], failure = null, downloadFailure = null } = {}) {
  assert.ok(existsSync(file), 'standalone snapshot export script must exist');
  const elements = new Map(), calls = [], downloads = [], redirects = [];
  function node() { return { events: {}, children: [], value: '', textContent: '', hidden: false, disabled: false,
    addEventListener(name, handler) { this.events[name] = handler; },
    appendChild(child) { this.children.push(child); },
    click() { downloads.push(this.download); }, remove() {} }; }
  function el(id) { if (!elements.has(id)) elements.set(id, node()); return elements.get(id); }
  el('exportForm').hidden = true;
  const context = vm.createContext({ URLSearchParams, document: { getElementById: el, createElement: node, body: { appendChild() {} } },
    window: { SHELL: { ready: Promise.resolve({ account: { role } }) },
      location: { pathname: '/teacher/exports/history', replace(url) { redirects.push(url); } },
      API: { async get(route) { calls.push(route); if (failure) throw failure; return { courses }; },
        async downloadWithMetadata(route) { calls.push(route); if (downloadFailure) throw downloadFailure; return { blob: {}, filename: `statistics-${'b'.repeat(32)}.${route.includes('format=pdf') ? 'pdf' : 'csv'}` }; } },
      URL: { createObjectURL() { return 'blob:export'; }, revokeObjectURL() {} }, setTimeout(fn) { fn(); } } });
  vm.runInContext(readFileSync(file, 'utf8'), context);
  await tick(); await tick();
  return { elements, calls, downloads, redirects, async click(id) { await el(id).events.click(); await tick(); } };
}

test('teacher can export the latest snapshot without triggering statistics', async () => {
  const view = await page();
  view.elements.get('exportCourse').value = 'course 1';
  await view.click('exportLatestPdf');
  assert.deepEqual(view.calls, ['/api/courses', '/api/courses/course%201/export?format=pdf']);
  assert.deepEqual(view.downloads, [`statistics-${'b'.repeat(32)}.pdf`]);
});

test('teacher can export a known historical publication without triggering statistics', async () => {
  const view = await page();
  view.elements.get('exportCourse').value = 'course 1';
  view.elements.get('exportPublication').value = 'A'.repeat(32);
  await view.click('exportLatestCsv');
  assert.deepEqual(view.calls, ['/api/courses', `/api/courses/course%201/export?format=csv&publication=${'a'.repeat(32)}`]);
});

test('invalid identifiers do not send a download request', async () => {
  const view = await page();
  view.elements.get('exportCourse').value = 'course 1';
  view.elements.get('exportPublication').value = 'invalid';
  await view.click('exportLatestCsv');
  assert.deepEqual(view.calls, ['/api/courses']);
  assert.match(view.elements.get('exportPageError').textContent, /发布编号/);
});

test('other staff roles do not load teacher courses or export files', async () => {
  const view = await page({ role: 'admin' });
  assert.deepEqual(view.calls, []);
  assert.equal(view.elements.get('exportForm').hidden, true);
  assert.match(view.elements.get('exportPageError').textContent, /教师/);
});

test('a backend export error stays visible', async () => {
  const view = await page({ downloadFailure: { status: 409, message: '暂无已发布结果。' } });
  view.elements.get('exportCourse').value = 'course 1';
  await view.click('exportLatestCsv');
  assert.equal(view.elements.get('exportPageError').hidden, false);
  assert.match(view.elements.get('exportPageError').textContent, /暂无已发布/);
});
