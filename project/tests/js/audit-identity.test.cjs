const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

test('audit rows identify accounts and show staff number changes', async () => {
  const elements = new Map();
  function node() {
    return { children: [], options: [], value: '', hidden: false, textContent: '',
      appendChild(child) { this.children.push(child); }, addEventListener() {} };
  }
  function element(id) { if (!elements.has(id)) elements.set(id, node()); return elements.get(id); }
  const actorId = 'a'.repeat(32), targetId = 'b'.repeat(32);
  const context = vm.createContext({ URLSearchParams,
    document: { getElementById: element, createElement: node },
    window: { SHELL: { ready: Promise.resolve() }, API: { async get() {
      return { courses: [], entries: [{ at: '2026-10-28T10:13:00+08:00', actor: 'admin', actorId,
        action: '修改账号', target: '001235', targetId,
        accountChange: { from: '001234', to: '001235' }, epsCost: 0 }] };
    } } } });
  vm.runInContext(readFileSync(path.join(__dirname, '../../src/taces/presentation/static/js/pages/audit.js'), 'utf8'), context);
  await new Promise(setImmediate);
  const cells = elements.get('auditRows').children[0].children;
  assert.equal(cells[1].textContent, `admin · ${actorId}`);
  assert.equal(cells[3].textContent, `001234 → 001235 · ${targetId}`);
});
