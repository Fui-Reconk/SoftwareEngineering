const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const source = readFileSync(path.join(__dirname,
  '../../src/taces/presentation/static/js/pages/board.js'), 'utf8');

async function render(data) {
  const elements = new Map();
  const charts = [];
  function node() {
    return { textContent: '', hidden: true, children: [],
      className: '', classList: { add() {} }, style: {},
      append(...children) { this.children.push(...children); },
      appendChild(child) { this.children.push(child); } };
  }
  function element(id) {
    if (!elements.has(id)) elements.set(id, node());
    return elements.get(id);
  }
  element('board').dataset = { course: 'synthetic' };
  const context = vm.createContext({
    document: { getElementById: element, createElement: node },
    window: {
      SHELL: { ready: Promise.resolve() },
      API: { get: async () => data },
      Charts: {
        fmt: { int: String, dec: (places) => (value) => Number(value).toFixed(places),
          pct: (places) => (value) => (value * 100).toFixed(places) + '%' },
        intervals() {}, bars(target, options) { charts.push(options); },
      },
      addEventListener() {},
    },
  });
  vm.runInContext(source, context);
  await new Promise(setImmediate);
  return { elements, charts };
}

test('a budget refusal never tells an at-threshold course to collect more evaluations', async () => {
  const { elements } = await render({ state: 'unpublished', reason: 'budget_exhausted',
    sample: 5, threshold: 5, shortfall: 0, charged: false });
  assert.match(elements.get('refusedTitle').textContent, /预算/);
  assert.doesNotMatch(elements.get('refusedTitle').textContent, /还差/);
  assert.doesNotMatch(elements.get('refusedWhy').textContent, /没到/);
  assert.match(elements.get('refusedWhy').textContent, /管理员/);
});

test('the below-threshold refusal still explains the missing sample count', async () => {
  const { elements } = await render({ state: 'unpublished', reason: 'below_threshold',
    sample: 4, threshold: 5, shortfall: 1, charged: false });
  assert.match(elements.get('refusedTitle').textContent, /还差 1 份/);
  assert.match(elements.get('refusedWhy').textContent, /没到 k=5/);
});

test('the real histogram counts complete evaluations instead of individual dimension rows', async () => {
  const { elements, charts } = await render({ state: 'published', courseCode: 'synthetic',
    courseTitle: 'Synthetic', term: 'test', responses: 6, enrolled: 8,
    pooledMean: 3, interval: 4, spread: 0, distinguishable: false,
    dimensions: [{ name: 'A', value: 3 }, { name: 'B', value: 3 }, { name: 'C', value: 3 }],
    distribution: [1, 2, 3, 4, 5].map((score) => ({ score, count: score === 3 ? 2 : 1 })),
    openText: { responses: 0, terms: [] }, publishedAt: '2026-10-27T12:00:00+08:00',
    budgetExhausted: false });
  assert.equal(elements.get('ratingCount').textContent, '6 份有效评价');
  assert.equal(charts[0].unit, ' 份');
});
