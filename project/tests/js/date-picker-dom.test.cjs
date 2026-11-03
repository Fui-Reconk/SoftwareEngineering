const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const source = readFileSync(path.join(__dirname, '../../src/taces/presentation/static/js/date-picker.js'), 'utf8');

function element(id = '') {
  let text = '';
  return { id, children: [], events: {}, attrs: {}, dataset: {}, style: {}, value: '', hidden: false, open: false,
    classList: { toggle() {} },
    get textContent() { return text; },
    set textContent(value) { text = value; this.children = []; },
    appendChild(child) { this.children.push(child); },
    addEventListener(name, handler) { (this.events[name] ||= []).push(handler); },
    fire(name, event = {}) { for (const handler of this.events[name] || []) handler(event); },
    dispatchEvent(event) { this.fire(event.type, event); },
    setAttribute(name, value) { this.attrs[name] = value; },
    focus() { this.focused = true; },
    showModal() { this.open = true; }, close() { this.open = false; },
    getBoundingClientRect() { return { left: 20, right: 320, top: 20, bottom: 60, width: 300, height: 40 }; },
    querySelector(selector) {
      const match = /^\[data-day="(\d+)"\]$/.exec(selector);
      function find(node) {
        if (match && node.dataset.day === match[1]) return node;
        for (const child of node.children) { const found = find(child); if (found) return found; }
        return null;
      }
      return find(this);
    },
  };
}

function mount({ value = '2026-05-15', withTime = false, supportsDialog = true, visualViewport = null } = {}) {
  const ids = ['datePickerDialog', 'dateYear', 'dateMonth', 'dateGrid', 'datePrevious', 'dateNext',
    'dateTimeControls', 'dateHour', 'dateMinute', 'dateError', 'dateToday', 'dateClear', 'dateCancel', 'dateConfirm'];
  const nodes = Object.fromEntries(ids.map(id => [id, element(id)]));
  if (!supportsDialog) nodes.datePickerDialog.showModal = undefined;
  const input = element('dateValue');
  input.value = value;
  const trigger = element('trigger');
  trigger.hidden = true;
  trigger.dataset = { dateFor: input.id, withTime: String(withTime) };
  const label = element('label');
  trigger.querySelector = () => label;
  nodes[input.id] = input;
  const document = { getElementById: id => nodes[id], querySelectorAll: () => [trigger],
    createElement: () => element() };
  const window = { innerWidth: 1024, innerHeight: 768, visualViewport, addEventListener() {} };
  const context = vm.createContext({ document, window, Event: class { constructor(type) { this.type = type; } } });
  vm.runInContext(source, context);
  return { ...nodes, input, trigger, label, window };
}

test('native date control remains available if dialog enhancement is unsupported', () => {
  const view = mount({ supportsDialog: false });
  assert.equal(view.input.hidden, false);
  assert.equal(view.trigger.hidden, true);
});

test('calendar keeps the same six-week layout when navigating between short and long months', () => {
  const view = mount({ value: '2021-02-15' });
  view.trigger.fire('click');
  for (const [month, numberOfDays] of [[2, 28], [3, 31], [5, 31]]) {
    view.dateMonth.value = String(month);
    view.dateMonth.fire('change');
    assert.equal(view.dateGrid.children.length, 6, `2021-${month} must leave room for six weeks`);
    assert.ok(view.dateGrid.children.every(row => row.children.length === 7));
    const dayButtons = view.dateGrid.children.flatMap(row => row.children.flatMap(cell => cell.children));
    assert.equal(dayButtons.length, numberOfDays);
    assert.equal(dayButtons[0].textContent, '1');
    assert.equal(dayButtons.at(-1).textContent, String(numberOfDays));
  }
});

test('confirm, cancel and clear preserve values and emit changes only when needed', () => {
  const view = mount();
  let changes = 0;
  view.input.addEventListener('change', () => { changes += 1; });
  assert.equal(view.input.hidden, true);
  assert.equal(view.trigger.hidden, false);
  assert.equal(view.label.textContent, '2026年5月15日');
  view.trigger.fire('click');
  view.dateGrid.querySelector('[data-day="17"]').fire('click');
  view.dateConfirm.fire('click');
  assert.equal(view.input.value, '2026-05-17');
  assert.equal(view.label.textContent, '2026年5月17日');
  assert.equal(changes, 1);
  view.trigger.fire('click');
  view.dateGrid.querySelector('[data-day="18"]').fire('click');
  view.dateCancel.fire('click');
  assert.equal(view.input.value, '2026-05-17');
  assert.equal(changes, 1);
  view.trigger.fire('click');
  view.dateClear.fire('click');
  assert.equal(view.input.value, '');
  assert.equal(view.label.textContent, '请选择日期');
  assert.equal(changes, 2);
});

test('an invalid year stays visible and blocks navigation and confirmation', () => {
  const view = mount();
  view.trigger.fire('click');
  view.dateYear.value = '10000';
  view.dateYear.fire('change');
  assert.equal(view.dateError.hidden, false);
  assert.equal(view.dateYear.focused, undefined, 'an invalid year must not trap keyboard focus');
  view.dateMonth.value = '6';
  view.dateMonth.fire('change');
  assert.equal(view.dateYear.value, '10000');
  assert.equal(view.dateMonth.value, '5');
  assert.equal(view.dateError.hidden, false);
  view.dateConfirm.fire('click');
  assert.equal(view.datePickerDialog.open, true);
  assert.equal(view.input.value, '2026-05-15');
  view.dateYear.value = '2028';
  view.dateYear.fire('change');
  assert.equal(view.dateError.hidden, true);
  view.dateConfirm.fire('click');
  assert.equal(view.input.value, '2028-05-15');
});

test('datetime picker keeps a 24-hour local time and ISO value', () => {
  const view = mount({ value: '2028-02-28T09:05', withTime: true });
  view.trigger.fire('click');
  view.dateGrid.querySelector('[data-day="29"]').fire('click');
  view.dateHour.value = '15';
  view.dateMinute.value = '30';
  view.dateConfirm.fire('click');
  assert.equal(view.input.value, '2028-02-29T15:30');
  assert.equal(view.label.textContent, '2028年2月29日 15:30');
});

test('arrow keys cross month and year boundaries and programmatic values stay in sync', () => {
  const view = mount({ value: '2026-12-31' });
  view.trigger.fire('click');
  let prevented = false;
  view.dateGrid.querySelector('[data-day="31"]').fire('keydown', {
    key: 'ArrowRight', preventDefault() { prevented = true; },
  });
  assert.equal(prevented, true);
  view.dateConfirm.fire('click');
  assert.equal(view.input.value, '2027-01-01');
  view.input.value = '2028-02-29';
  view.window.TacesDatePicker.sync(view.input);
  assert.equal(view.label.textContent, '2028年2月29日');
});

test('zoomed visual viewport constrains and repositions the picker on pan', () => {
  const viewport = element('viewport');
  Object.assign(viewport, { width: 195, height: 400, offsetLeft: 90, offsetTop: 20 });
  const view = mount({ visualViewport: viewport });
  view.trigger.fire('click');
  assert.match(view.datePickerDialog.style.left, /clamp\(98px/);
  assert.match(view.datePickerDialog.style.maxWidth, /285px/);
  viewport.offsetLeft = 120;
  viewport.fire('scroll');
  assert.match(view.datePickerDialog.style.left, /clamp\(128px/);
  assert.match(view.datePickerDialog.style.maxWidth, /315px/);
});

test('picker uses the available space after a short viewport grows', () => {
  const view = mount({ value: '2021-02-15T09:05', withTime: true });
  view.window.innerWidth = 390;
  view.window.innerHeight = 844;
  view.trigger.getBoundingClientRect = () => ({ left: 36, right: 356, top: 462, bottom: 502 });
  view.trigger.fire('click');
  // Simulate the inline size left over after the dialog was constrained by a short viewport.
  view.datePickerDialog.style.maxHeight = '304px';
  view.datePickerDialog.getBoundingClientRect = function () {
    const limit = Number.parseFloat(this.style.maxHeight);
    return { left: 36, right: 356, top: 0, bottom: 0, width: 320,
      height: Number.isFinite(limit) ? Math.min(414, limit) : 414 };
  };
  view.dateMonth.value = '3';
  view.dateMonth.fire('change');
  assert.match(view.datePickerDialog.style.top, /clamp\(8px, 40px,/,
    'the full-height picker should fit above the trigger instead of being clipped below it');
});
