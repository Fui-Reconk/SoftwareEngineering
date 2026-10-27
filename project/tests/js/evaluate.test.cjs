const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const script = readFileSync(path.join(__dirname, '../../src/taces/presentation/static/js/pages/evaluate.js'), 'utf8');

function element() {
  return {
    children: [], handlers: {}, hidden: false, disabled: false, value: '', textContent: '',
    addEventListener(name, handler) { this.handlers[name] = handler; },
    setAttribute(name, value) { this[name] = value; },
    append(...children) { this.children.push(...children); },
    appendChild(child) { this.children.push(child); },
    focus() { this.focused = true; },
  };
}

function evaluationPage(failure = null) {
  const ids = Object.fromEntries([
    'rateForm', 'dimensionRows', 'submitRating', 'rateError', 'openText',
    'charCount', 'courseTitle', 'courseMeta', 'receipt',
  ].map((id) => [id, element()]));
  ids.receipt.hidden = true;
  const formCard = element();
  const storage = new Map([['taces.verify', JSON.stringify({
    code: 'demo-code',
    course: { title: '演示课程', dimensions: [{ name: '教学内容' }, { name: '教学方法' }] },
  })]]);
  const navigation = [];
  const requests = [];
  const timers = [];
  let now = 0;
  const context = vm.createContext({
    document: {
      getElementById(id) { return ids[id]; },
      querySelector(selector) { return selector === '.card-wide' ? formCard : null; },
      createElement: element,
    },
    sessionStorage: {
      getItem(key) { return storage.get(key) ?? null; },
      setItem(key, value) { storage.set(key, value); },
      removeItem(key) { storage.delete(key); },
    },
    window: {
      API: { async post(route, payload) {
        requests.push({ route, payload });
        if (failure) throw failure;
        return {};
      } },
      location: {
        assign(route) { navigation.push(route); },
        replace(route) { navigation.push(route); },
      },
      setTimeout(callback, delay) { timers.push({ callback, at: now + delay }); },
    },
  });
  vm.runInContext(script, context);
  for (const row of ids.dimensionRows.children) {
    row.children[1].children[3].children[0].handlers.change();
  }
  return {
    ids, formCard, storage, navigation, requests, timers,
    submit: () => ids.rateForm.handlers.submit({ preventDefault() {} }),
    advance(milliseconds) {
      now += milliseconds;
      for (const timer of timers.splice(0)) {
        if (timer.at <= now) timer.callback();
        else timers.push(timer);
      }
    },
  };
}

test('a successful submission shows the receipt and returns home after five seconds', async () => {
  const page = evaluationPage();
  await page.submit();
  assert.equal(page.requests.length, 1);
  assert.equal(page.requests[0].route, '/api/submissions');
  assert.equal(page.formCard.hidden, true);
  assert.equal(page.ids.receipt.hidden, false);
  assert.equal(page.storage.has('taces.verify'), false);
  assert.equal(page.timers.length, 1);
  assert.equal(page.ids.receipt.focused, true);
  page.advance(4999);
  assert.deepEqual(page.navigation, []);
  page.advance(1);
  assert.deepEqual(page.navigation, ['/']);
});

test('a failed submission keeps the form available and does not schedule a return', async () => {
  const page = evaluationPage({ status: 500, message: '暂时无法提交。' });
  await page.submit();
  assert.equal(page.formCard.hidden, false);
  assert.equal(page.ids.receipt.hidden, true);
  assert.equal(page.ids.rateError.hidden, false);
  assert.equal(page.ids.rateError.textContent, '暂时无法提交。');
  assert.equal(page.ids.submitRating.disabled, false);
  assert.equal(page.storage.has('taces.verify'), true);
  assert.equal(page.timers.length, 0);
  assert.deepEqual(page.navigation, []);
});

test('a rejected code returns to the student entry without scheduling the receipt timer', async () => {
  const page = evaluationPage({ status: 409, message: '评价码已失效。' });
  await page.submit();
  assert.equal(page.ids.receipt.hidden, true);
  assert.equal(page.storage.has('taces.verify'), false);
  assert.equal(page.storage.get('taces.failure'), '评价码已失效。');
  assert.equal(page.timers.length, 0);
  assert.deepEqual(page.navigation, ['/student']);
});
