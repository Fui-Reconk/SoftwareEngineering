const assert = require('node:assert/strict');
const { test } = require('node:test');
const path = require('node:path');
const { parseValue, displayValue, monthGrid, shiftMonth } = require(path.join(__dirname,
  '../../src/taces/presentation/static/js/date-picker.js'));

test('date and 24-hour datetime values preserve the existing ISO API format', () => {
  assert.deepEqual(parseValue('2028-02-29', false), { year: 2028, month: 2, day: 29, hour: 0, minute: 0 });
  assert.deepEqual(parseValue('2028-02-29T09:05', true), { year: 2028, month: 2, day: 29, hour: 9, minute: 5 });
  assert.equal(displayValue('2028-02-29', false), '2028年2月29日');
  assert.equal(displayValue('2028-02-29T09:05', true), '2028年2月29日 09:05');
  assert.equal(displayValue('', false), '请选择日期');
  assert.equal(displayValue('', true), '请选择日期和时间');
});

test('calendar validates leap years and month boundaries without locale dependence', () => {
  for (const value of ['2027-02-29', '2028-04-31', '0000-01-01', '2028-13-01']) {
    assert.equal(parseValue(value, false), null, value);
  }
  for (const value of ['2028-02-29T24:00', '2028-02-29T09:60', '2028-02-29T09:05PM']) {
    assert.equal(parseValue(value, true), null, value);
  }
  const days = monthGrid(2026, 2);
  assert.equal(days.length, 42);
  assert.equal(days.indexOf(1), 6); // Monday-first: 2026-02-01 is Sunday.
  assert.equal(days.filter(Boolean).length, 28);
  assert.equal(monthGrid(2028, 2).filter(Boolean).length, 29);
  assert.deepEqual(shiftMonth(2026, 12, 1), { year: 2027, month: 1 });
  assert.deepEqual(shiftMonth(2026, 1, -1), { year: 2025, month: 12 });
});
