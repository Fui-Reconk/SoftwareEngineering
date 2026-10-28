const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const source = readFileSync(path.join(__dirname, '../../src/taces/presentation/static/js/pages/board.js'), 'utf8');
const tick = () => new Promise(setImmediate);
const firstId = 'a'.repeat(32), nextId = 'b'.repeat(32);
const snapshot = (id = firstId, changes = {}) => ({
  state: 'published', publicationId: id, charged: false, budgetExhausted: false,
  courseCode: 'course-1', courseTitle: '数据结构', term: '2026秋', responses: 5, enrolled: 6,
  pooledMean: 3, interval: 1, spread: 0, distinguishable: false,
  dimensions: [{ name: '教学内容', value: 3 }],
  distribution: [1, 2, 3, 4, 5].map(score => ({ score, count: score === 3 ? 5 : 0 })),
  openText: { responses: 1, terms: [{ word: '反馈', count: 1 }] },
  publishedAt: '2026-10-28T12:00:00+08:00', ...changes,
});

async function render(initial, { session = { account: { role: 'teacher' } }, mock = false } = {}) {
  const elements = new Map(), calls = [], queue = [initial], resize = [], charts = [], redirects = [], chartErrors = [];
  function node() {
    let text = '';
    const classes = new Set();
    return { hidden: true, disabled: true, events: {}, children: [], style: {},
      classList: { add(value) { classes.add(value); }, remove(value) { classes.delete(value); }, contains(value) { return classes.has(value); } },
      get textContent() { return text; }, set textContent(value) { text = value; this.children = []; },
      addEventListener(name, handler) { this.events[name] = handler; },
      append(...children) { this.children.push(...children); }, appendChild(child) { this.children.push(child); },
      remove() {}, click() {},
    };
  }
  function element(id) { if (!elements.has(id)) elements.set(id, node()); return elements.get(id); }
  element('board').dataset = { course: 'course-1' };
  element('exportError');
  const context = vm.createContext({ URLSearchParams,
    document: { getElementById: element, createElement: node, body: { appendChild() {} } },
    window: { SHELL: { ready: Promise.resolve(session) },
      location: { pathname: '/teacher/course-1', replace(url) { redirects.push(url); } },
      API: { USE_MOCK: mock, async get(url) { calls.push(url); const result = await queue.shift(); if (result instanceof Error || result?.status) throw result; return result; } },
      Charts: { fmt: { int: String, dec: p => v => Number(v).toFixed(p), pct: p => v => (v * 100).toFixed(p) + '%' },
        intervals() {}, bars(target, options) { if (chartErrors.shift()) throw new Error('图表渲染失败'); charts.push(options); } },
      addEventListener(name, listener) { if (name === 'resize') resize.push(listener); },
    } });
  vm.runInContext(source, context);
  await tick();
  return { elements, calls, queue, resize, charts, redirects, chartErrors,
    async click() { await element('refreshResults').events.click(); await tick(); } };
}

test('a teacher can update an unpublished course when enough evaluations arrive', async () => {
  const view = await render({ state: 'unpublished', reason: 'below_threshold', sample: 4, threshold: 5, shortfall: 1 });
  assert.equal(view.elements.get('refused').hidden, false);
  assert.equal(view.elements.get('refreshResults').disabled, false);
  view.queue.push(snapshot(nextId, { charged: true }));
  await view.click();
  assert.deepEqual(view.calls, ['/api/courses/course-1/statistics', '/api/courses/course-1/statistics']);
  assert.equal(view.elements.get('refused').hidden, true);
  assert.equal(view.elements.get('published').hidden, false);
  assert.equal(view.elements.get('publishState').classList.contains('refused'), false);
  assert.equal(view.elements.get('exportCsv').disabled, false);
  assert.match(view.elements.get('refreshStatus').textContent, /已.*新.*结果/);
});

test('a failed shell authentication does not request or enable statistics', async () => {
  const view = await render(snapshot(), { session: null });
  assert.deepEqual(view.calls, []);
  assert.equal(view.elements.get('refreshResults').disabled, true);
});

test('mock mode can display results but does not offer unsupported exports', async () => {
  const view = await render(snapshot(), { mock: true });
  assert.equal(view.elements.get('published').hidden, false);
  assert.equal(view.elements.get('exportCsv').disabled, true);
  assert.equal(view.elements.get('exportPdf').disabled, true);
  assert.equal(view.elements.get('historyExport').hidden, true);
});

test('updated charts and export target replace the old snapshot without accumulating resize handlers', async () => {
  const view = await render(snapshot());
  view.elements.get('exportError').hidden = false;
  view.elements.get('exportError').textContent = '之前的导出失败';
  view.queue.push(snapshot(nextId, { charged: true, responses: 6, enrolled: 7,
    distribution: [1, 2, 3, 4, 5].map(score => ({ score, count: score === 5 ? 6 : 0 })),
    openText: { responses: 0, terms: [] } }));
  await view.click();
  assert.match(view.elements.get('currentPublication').textContent, new RegExp(nextId));
  assert.match(view.elements.get('courseSub').textContent, /有效评价 6 份/);
  assert.equal(view.elements.get('words').hidden, true);
  assert.equal(view.elements.get('exportError').hidden, true);
  assert.equal(view.resize.length, 1);
  view.resize[0]();
  assert.deepEqual(Array.from(view.charts.at(-1).values), [0, 0, 0, 0, 6]);
});

test('cached and budget-exhausted results explain why the existing snapshot remains', async () => {
  const view = await render(snapshot());
  view.queue.push(snapshot());
  await view.click();
  assert.match(view.elements.get('refreshStatus').textContent, /已有结果/);
  view.queue.push(snapshot(firstId, { budgetExhausted: true }));
  await view.click();
  assert.match(view.elements.get('refreshStatus').textContent, /预算不足/);
  assert.equal(view.elements.get('published').hidden, false);
  assert.match(view.elements.get('currentPublication').textContent, new RegExp(firstId));
});

test('another tab’s new snapshot is shown even when this request does not spend budget', async () => {
  const view = await render(snapshot());
  view.queue.push(snapshot(nextId, { charged: false }));
  await view.click();
  assert.match(view.elements.get('refreshStatus').textContent, /最新发布结果/);
  assert.match(view.elements.get('currentPublication').textContent, new RegExp(nextId));
});

test('the last affordable publication reports both the update and exhausted budget', async () => {
  const view = await render(snapshot());
  view.queue.push(snapshot(nextId, { charged: true, budgetExhausted: true }));
  await view.click();
  assert.match(view.elements.get('refreshStatus').textContent, /已发布新的统计结果/);
  assert.match(view.elements.get('refreshStatus').textContent, /预算不足/);
});

test('a failed update retains the displayed snapshot and prevents duplicate requests', async () => {
  const view = await render(snapshot());
  let reject;
  view.queue.push(new Promise((_, fail) => { reject = fail; }));
  const pending = view.click();
  await tick();
  assert.equal(view.elements.get('refreshResults').disabled, true);
  assert.equal(view.elements.get('exportCsv').disabled, true);
  await view.click();
  assert.equal(view.calls.length, 2);
  reject({ status: 503 });
  await pending;
  assert.equal(view.elements.get('published').hidden, false);
  assert.match(view.elements.get('currentPublication').textContent, new RegExp(firstId));
  assert.equal(view.elements.get('refreshError').hidden, false);
  assert.equal(view.elements.get('refreshResults').disabled, false);
  assert.equal(view.elements.get('exportCsv').disabled, false);
});

test('an expired session during an update returns to login', async () => {
  const view = await render(snapshot());
  view.queue.push({ status: 401 });
  await view.click();
  assert.deepEqual(view.redirects, ['/login?next=%2Fteacher%2Fcourse-1']);
  assert.equal(view.elements.get('refreshResults').disabled, true);
  assert.equal(view.elements.get('exportCsv').disabled, true);
});

test('lost access or a removed course clears results and disables export until access returns', async () => {
  for (const status of [403, 404]) {
    const view = await render(snapshot());
    view.queue.push({ status });
    await view.click();
    assert.equal(view.elements.get('published').hidden, true);
    assert.equal(view.elements.get('words').hidden, true);
    assert.equal(view.elements.get('historyExport').hidden, true);
    assert.equal(view.elements.get('exportCsv').disabled, true);
    assert.equal(view.elements.get('refreshError').hidden, false);
    view.queue.push(snapshot(nextId));
    await view.click();
    assert.equal(view.elements.get('published').hidden, false);
    assert.equal(view.elements.get('exportCsv').disabled, false);
  }
});

test('malformed results keep the previous complete snapshot and export target', async () => {
  const view = await render(snapshot());
  view.queue.push(snapshot(nextId, { charged: true, pooledMean: 4, distribution: null }));
  await view.click();
  assert.equal(view.elements.get('published').hidden, false);
  assert.equal(view.elements.get('pooledMean').textContent, '3.00');
  assert.match(view.elements.get('currentPublication').textContent, new RegExp(firstId));
  assert.equal(view.elements.get('exportCsv').disabled, false);
  assert.equal(view.elements.get('refreshError').hidden, false);
});

test('a chart rendering failure hides the partial snapshot and disables export', async () => {
  const view = await render(snapshot());
  view.chartErrors.push(true);
  view.queue.push(snapshot(nextId, { charged: true }));
  await view.click();
  assert.equal(view.elements.get('published').hidden, true);
  assert.equal(view.elements.get('historyExport').hidden, true);
  assert.equal(view.elements.get('exportCsv').disabled, true);
  assert.equal(view.elements.get('refreshError').hidden, false);
  assert.equal(view.elements.get('refreshResults').disabled, false);
});

test('a resize drawing failure does not leave mismatched charts exportable', async () => {
  const view = await render(snapshot());
  view.chartErrors.push(true);
  view.resize[0]();
  assert.equal(view.elements.get('published').hidden, true);
  assert.equal(view.elements.get('exportCsv').disabled, true);
  assert.equal(view.elements.get('refreshError').hidden, false);
});
