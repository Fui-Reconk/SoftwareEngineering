const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const root = path.join(__dirname, '../../src/taces/presentation/static/js');
const boardSource = readFileSync(path.join(root, 'pages/board.js'), 'utf8');
const apiSource = readFileSync(path.join(root, 'api.js'), 'utf8');
const tick = () => new Promise(setImmediate);
const publication = '0123456789abcdef0123456789abcdef';
const published = { state: 'published', publicationId: publication, courseCode: 'CS-1',
  courseTitle: '课程', term: '秋', responses: 5, enrolled: 6, pooledMean: 3, interval: 1,
  spread: 0, distinguishable: false, dimensions: [{ name: 'A', value: 3 }],
  distribution: [1, 2, 3, 4, 5].map(score => ({ score, count: 1 })),
  openText: { responses: 0, terms: [] }, publishedAt: '2026-10-28T10:00:00+08:00' };

async function page(data = published, failure = null) {
  const elements = new Map(), requests = [], downloads = [], revoked = [], redirects = [];
  function node() { return { textContent: '', hidden: true, disabled: true, events: {},
    children: [], style: {}, classList: { add() {}, remove() {} },
    addEventListener(name, fn) { this.events[name] = fn; },
    append(...children) { this.children.push(...children); },
    appendChild(child) { this.children.push(child); },
    click() { downloads.push({ href: this.href, filename: this.download }); }, remove() {},
  }; }
  function element(id) { if (!elements.has(id)) elements.set(id, node()); return elements.get(id); }
  element('board').dataset = { course: 'CS-1' };
  ['exportPdf', 'exportCsv', 'exportError', 'historyExport', 'historyId', 'historyPdf', 'historyCsv'].forEach(element);
  const context = vm.createContext({
    document: { getElementById: element, createElement: node, body: { appendChild() {} } },
    URLSearchParams,
    window: { SHELL: { ready: Promise.resolve({ account: { role: 'teacher' } }) },
      location: { pathname: '/teacher/CS-1', replace(url) { redirects.push(url); } },
      API: { get: async () => data, downloadWithMetadata: async route => {
        requests.push(route); if (failure) throw failure;
        return { blob: { file: true }, filename: `课程_秋_teacher.${route.includes('format=pdf') ? 'pdf' : 'csv'}` };
      } },
      URL: { createObjectURL: () => 'blob:download', revokeObjectURL: value => revoked.push(value) },
      Charts: { fmt: { int: String, dec: p => v => Number(v).toFixed(p), pct: p => v => (v * 100).toFixed(p) + '%' }, intervals() {}, bars() {} },
      addEventListener() {}, setTimeout(fn) { fn(); },
    },
  });
  vm.runInContext(boardSource, context);
  await tick();
  return { elements, requests, downloads, revoked, redirects,
    async click(id) { assert.equal(typeof element(id).events.click, 'function', `${id} must have a click handler`); await element(id).events.click(); await tick(); } };
}

test('published snapshots download the exact displayed publication in both formats', async () => {
  const view = await page();
  assert.equal(view.elements.get('exportPdf').disabled, false);
  assert.equal(view.elements.get('exportCsv').disabled, false);
  await view.click('exportPdf');
  await view.click('exportCsv');
  assert.deepEqual(view.requests, [
    `/api/courses/CS-1/export?format=pdf&publication=${publication}`,
    `/api/courses/CS-1/export?format=csv&publication=${publication}`,
  ]);
  assert.deepEqual(view.downloads.map(item => item.filename), ['课程_秋_teacher.pdf', '课程_秋_teacher.csv']);
  assert.equal(view.revoked.length, 2);
});

test('export after an update requests the newly displayed publication', async () => {
  const data = { ...published };
  const view = await page(data);
  const next = 'b'.repeat(32);
  data.publicationId = next;
  data.charged = true;
  await view.click('refreshResults');
  await view.click('exportPdf');
  assert.equal(view.requests[0], `/api/courses/CS-1/export?format=pdf&publication=${next}`);
});

test('unpublished results do not permit exports', async () => {
  const view = await page({ state: 'unpublished', reason: 'below_threshold', sample: 2, threshold: 5, shortfall: 3 });
  assert.equal(view.elements.get('exportPdf').disabled, true);
  assert.equal(view.elements.get('exportCsv').disabled, true);
  assert.deepEqual(view.requests, []);
});

test('download errors remain visible on the board', async () => {
  const view = await page(published, { status: 503, message: '导出服务暂不可用' });
  await view.click('exportCsv');
  assert.match(view.elements.get('exportError').textContent, /导出服务暂不可用/);
  assert.equal(view.elements.get('exportError').hidden, false);
  assert.equal(view.downloads.length, 0);
});

test('an expired session during export hides results and disables further actions', async () => {
  const view = await page(published, { status: 401 });
  await view.click('exportCsv');
  assert.deepEqual(view.redirects, ['/login?next=%2Fteacher%2FCS-1']);
  assert.equal(view.elements.get('published').hidden, true);
  assert.equal(view.elements.get('exportCsv').disabled, true);
  assert.equal(view.elements.get('refreshResults').disabled, true);
});

test('lost course access during export hides results but allows a later retry', async () => {
  const view = await page(published, { status: 403, message: '无权导出' });
  await view.click('exportCsv');
  assert.equal(view.elements.get('published').hidden, true);
  assert.equal(view.elements.get('exportCsv').disabled, true);
  assert.equal(view.elements.get('refreshResults').disabled, false);
  assert.match(view.elements.get('exportError').textContent, /无权/);
  assert.equal(view.elements.get('exportError').hidden, false);
});

test('a missing historical publication leaves the current snapshot available', async () => {
  const view = await page(published, { status: 404, message: '发布快照不存在' });
  view.elements.get('historyId').value = 'a'.repeat(32);
  await view.click('historyCsv');
  assert.equal(view.elements.get('published').hidden, false);
  assert.equal(view.elements.get('exportCsv').disabled, false);
  assert.match(view.elements.get('exportError').textContent, /不存在/);
});

test('the shared binary download includes the session and preserves backend errors', async () => {
  const calls = [];
  const blob = { file: true };
  let fail = false;
  const context = vm.createContext({ document: { querySelector: () => ({ content: 'csrf' }) },
    window: {}, URLSearchParams,
    fetch: async (url, options) => {
      calls.push({ url, options });
      return fail ? { ok: false, status: 403, json: async () => ({ error: { code: 'DENIED', message: '无权导出' } }) }
        : { ok: true, blob: async () => blob };
    },
  });
  vm.runInContext(apiSource, context);
  assert.equal(typeof context.window.API.download, 'function');
  assert.equal(await context.window.API.download('/api/courses/CS-1/export?format=csv'), blob);
  assert.equal(calls[0].options.credentials, 'include');
  fail = true;
  await assert.rejects(context.window.API.download('/api/courses/CS-1/export?format=csv'),
    error => error.status === 403 && error.message === '无权导出');
});


test('the result summary reflects a course with one custom dimension', async () => {
  const view = await page();
  assert.doesNotMatch(view.elements.get('finding').textContent, /三个维度/);
});


test('a teacher can export an older saved snapshot by its publication number', async () => {
  const view = await page();
  const old = 'a'.repeat(32);
  assert.equal(view.elements.get('historyExport').hidden, false);
  view.elements.get('historyId').value = old;
  await view.click('historyCsv');
  assert.equal(view.requests[0], `/api/courses/CS-1/export?format=csv&publication=${old}`);
  assert.equal(view.downloads[0].filename, '课程_秋_teacher.csv');
});

test('an invalid history number does not send a download request', async () => {
  const view = await page();
  view.elements.get('historyId').value = 'invalid';
  await view.click('historyPdf');
  assert.equal(view.requests.length, 0);
  assert.match(view.elements.get('exportError').textContent, /发布编号/);
});


test('binary download metadata decodes the backend UTF-8 attachment filename', async () => {
  const context = vm.createContext({ document: { querySelector: () => null }, window: {}, URLSearchParams,
    fetch: async () => ({ ok: true, blob: async () => ({ file: true }),
      headers: { get: name => name === 'Content-Disposition'
        ? "attachment; filename=_2026_teacher.csv; filename*=UTF-8''%E6%95%B0%E6%8D%AE%E7%BB%93%E6%9E%84_2026%E7%A7%8B_teacher.csv" : null } }) });
  vm.runInContext(apiSource, context);
  const result = await context.window.API.downloadWithMetadata('/api/courses/CS-1/export?format=csv');
  assert.equal(result.filename, '数据结构_2026秋_teacher.csv');
  assert.equal(result.blob.file, true);
});

test('binary metadata rejects encoded paths and malformed UTF-8 filenames', async () => {
  for (const disposition of ["attachment; filename*=UTF-8''..%2Fevil.csv", "attachment; filename*=UTF-8''%E6%ZZ.csv"]) {
    const context = vm.createContext({ document: { querySelector: () => null }, window: {}, URLSearchParams,
      fetch: async () => ({ ok: true, blob: async () => ({}), headers: { get: () => disposition } }) });
    vm.runInContext(apiSource, context);
    const result = await context.window.API.downloadWithMetadata('/api/courses/CS-1/export?format=csv');
    assert.equal(result.filename, null);
  }
});


test('binary metadata ignores unsafe attachment filenames', async () => {
  const context = vm.createContext({ document: { querySelector: () => null }, window: {}, URLSearchParams,
    fetch: async () => ({ ok: true, blob: async () => ({}),
      headers: { get: () => 'attachment; filename="../../unexpected.csv"' } }) });
  vm.runInContext(apiSource, context);
  const result = await context.window.API.downloadWithMetadata('/api/courses/CS-1/export?format=csv');
  assert.equal(result.filename, null);
});
