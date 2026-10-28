const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

function eventTarget() {
  return { events: {}, addEventListener(name, handler) { (this.events[name] ||= []).push(handler); },
    fire(name, event) { for (const handler of this.events[name] || []) handler(event); } };
}

test('password visibility is independent, preserves the value and resets on submit or dialog close', () => {
  const form = eventTarget(), dialog = eventTarget(), window = eventTarget();
  const inputs = { one: { type: 'password', value: 'first secret' }, two: { type: 'password', value: 'second secret' } };
  const buttons = Object.keys(inputs).map(id => ({ ...eventTarget(),
    dataset: { showLabel: `显示${id}`, hideLabel: `隐藏${id}` },
    attrs: { 'aria-controls': id, 'aria-label': `显示${id}`, 'aria-pressed': 'false' },
    getAttribute(name) { return this.attrs[name]; }, setAttribute(name, value) { this.attrs[name] = value; },
    closest(selector) { return selector === 'form' ? form : selector === 'dialog' ? dialog : null; },
  }));
  const context = vm.createContext({ window, document: { querySelectorAll: () => buttons, getElementById: id => inputs[id] } });
  vm.runInContext(readFileSync(path.join(__dirname, '../../src/taces/presentation/static/js/password-toggle.js'), 'utf8'), context);
  buttons[0].fire('click');
  assert.equal(inputs.one.type, 'text');
  assert.equal(inputs.two.type, 'password');
  assert.equal(inputs.one.value, 'first secret');
  assert.equal(buttons[0].attrs['aria-label'], '显示one');
  assert.equal(buttons[0].attrs['aria-pressed'], 'true');
  assert.equal(buttons[0].title, '隐藏one');
  buttons[0].fire('click');
  assert.equal(inputs.one.type, 'password');
  assert.equal(buttons[0].attrs['aria-label'], '显示one');
  assert.equal(buttons[0].title, '显示one');
  buttons[0].fire('click');
  buttons[1].fire('click');
  form.fire('submit');
  assert.equal(inputs.one.type, 'password');
  assert.equal(inputs.two.type, 'password');
  buttons[1].fire('click');
  dialog.fire('close');
  assert.equal(inputs.two.type, 'password');
  assert.equal(buttons[1].attrs['aria-pressed'], 'false');
  buttons[0].fire('click');
  window.fire('pageshow', { persisted: true });
  assert.equal(inputs.one.type, 'password');
  assert.equal(buttons[0].attrs['aria-pressed'], 'false');
});
