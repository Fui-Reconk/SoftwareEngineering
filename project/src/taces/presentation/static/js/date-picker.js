/* Chinese date controls retain ISO values for the existing APIs. */
(function () {
  'use strict';

  const pad = (number) => String(number).padStart(2, '0');
  const daysInMonth = (year, month) => {
    if (month === 2) return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0) ? 29 : 28;
    return [4, 6, 9, 11].includes(month) ? 30 : 31;
  };

  function parseValue(value, withTime) {
    if (typeof value !== 'string') return null;
    const match = (withTime ? /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/ : /^(\d{4})-(\d{2})-(\d{2})$/).exec(value);
    if (!match) return null;
    const year = Number(match[1]), month = Number(match[2]), day = Number(match[3]);
    const hour = withTime ? Number(match[4]) : 0, minute = withTime ? Number(match[5]) : 0;
    if (year < 1 || month < 1 || month > 12 || day < 1 || day > daysInMonth(year, month)
        || hour > 23 || minute > 59) return null;
    return { year, month, day, hour, minute };
  }

  function displayValue(value, withTime) {
    const date = parseValue(value, withTime);
    if (!date) return withTime ? '请选择日期和时间' : '请选择日期';
    return `${date.year}年${date.month}月${date.day}日${withTime ? ` ${pad(date.hour)}:${pad(date.minute)}` : ''}`;
  }

  function monthGrid(year, month) {
    const first = new Date(0);
    first.setUTCHours(0, 0, 0, 0);
    first.setUTCFullYear(year, month - 1, 1);
    const offset = (first.getUTCDay() + 6) % 7;
    const length = daysInMonth(year, month);
    return Array.from({ length: 42 }, (_, index) => {
      const day = index - offset + 1;
      return day >= 1 && day <= length ? day : null;
    });
  }

  function shiftMonth(year, month, amount) {
    const index = Math.max(0, Math.min(9999 * 12 - 1, (year - 1) * 12 + month - 1 + amount));
    return { year: Math.floor(index / 12) + 1, month: index % 12 + 1 };
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { parseValue, displayValue, monthGrid, shiftMonth };
  }
  if (typeof document === 'undefined') return;
  const dialog = document.getElementById('datePickerDialog');
  if (!dialog || typeof dialog.showModal !== 'function') return;

  const byId = (id) => document.getElementById(id);
  const yearInput = byId('dateYear'), monthSelect = byId('dateMonth'), grid = byId('dateGrid');
  const previous = byId('datePrevious'), next = byId('dateNext');
  const timeControls = byId('dateTimeControls'), hourSelect = byId('dateHour'), minuteSelect = byId('dateMinute');
  const error = byId('dateError');
  const triggers = Array.from(document.querySelectorAll('[data-date-for]'));
  let active = null, draft = null;

  function addOptions(select, count) {
    for (let number = 0; number < count; number += 1) {
      const option = document.createElement('option');
      option.value = pad(number);
      option.textContent = pad(number);
      select.appendChild(option);
    }
  }
  addOptions(hourSelect, 24);
  addOptions(minuteSelect, 60);

  function sync(input) {
    const trigger = triggers.find((item) => item.dataset.dateFor === input.id);
    if (!trigger) return;
    const withTime = trigger.dataset.withTime === 'true';
    trigger.querySelector('[data-date-value]').textContent = displayValue(input.value, withTime);
    trigger.classList.toggle('is-empty', !parseValue(input.value, withTime));
  }
  window.TacesDatePicker = { sync };

  function applyYear(focusInvalid = false) {
    const year = Number(yearInput.value);
    if (!yearInput.value.trim() || !Number.isInteger(year) || year < 1 || year > 9999) {
      error.textContent = '请输入 1 至 9999 之间的有效年份。';
      error.hidden = false;
      placeDialog();
      if (focusInvalid) yearInput.focus();
      return false;
    }
    draft.year = year;
    draft.day = Math.min(draft.day, daysInMonth(draft.year, draft.month));
    return true;
  }

  function placeDialog() {
    if (!active || !dialog.open) return;
    const target = active.trigger.getBoundingClientRect();
    const margin = 8;
    const viewport = window.visualViewport;
    const visibleTop = viewport?.offsetTop || 0;
    const visibleHeight = viewport?.height || window.innerHeight;
    const bottom = visibleTop + visibleHeight;
    const visibleLeft = viewport?.offsetLeft || 0;
    const visibleWidth = viewport?.width || window.innerWidth;
    const right = visibleLeft + visibleWidth;
    dialog.style.maxWidth = '';
    const width = dialog.getBoundingClientRect().width;
    const left = Math.max(visibleLeft + margin, Math.min(target.left, right - width - margin));
    const rightLimit = viewport && visibleWidth < window.innerWidth ? `${right}px` : '100vw';
    const leftLimit = `clamp(${visibleLeft + margin}px, ${left}px, calc(${rightLimit} - ${Math.ceil(width) + margin}px))`;
    dialog.style.left = leftLimit;
    dialog.style.maxWidth = `max(0px, calc(${rightLimit} - ${leftLimit} - ${margin}px))`;
    const bounds = dialog.getBoundingClientRect();
    const below = target.bottom + margin;
    const above = target.top - bounds.height - margin;
    const top = below + bounds.height <= bottom - margin ? below
      : above >= visibleTop + margin ? above : Math.max(visibleTop + margin, bottom - bounds.height - margin);
    // Constrain position and height even when content or the viewport changes.
    const bottomLimit = viewport && visibleHeight < window.innerHeight ? `${bottom}px` : '100dvh';
    const topLimit = `clamp(${visibleTop + margin}px, ${top}px, calc(${bottomLimit} - ${Math.ceil(bounds.height) + margin}px))`;
    dialog.style.top = topLimit;
    dialog.style.maxHeight = `max(0px, calc(${bottomLimit} - ${topLimit} - ${margin}px))`;
  }

  function moveDay(amount) {
    if (!applyYear(true)) return;
    const date = new Date(0);
    date.setUTCHours(0, 0, 0, 0);
    date.setUTCFullYear(draft.year, draft.month - 1, draft.day + amount);
    const year = date.getUTCFullYear();
    if (year < 1 || year > 9999) return;
    draft.year = year;
    draft.month = date.getUTCMonth() + 1;
    draft.day = date.getUTCDate();
    render(true);
  }

  function moveMonth(amount) {
    if (!applyYear(true)) return;
    const moved = shiftMonth(draft.year, draft.month, amount);
    draft.year = moved.year;
    draft.month = moved.month;
    draft.day = Math.min(draft.day, daysInMonth(draft.year, draft.month));
    render(true);
  }

  function keyDay(event) {
    const delta = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[event.key];
    if (delta) {
      event.preventDefault();
      moveDay(delta);
    } else if (event.key === 'PageUp' || event.key === 'PageDown') {
      event.preventDefault();
      moveMonth(event.key === 'PageUp' ? -1 : 1);
    } else if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault();
      const index = monthGrid(draft.year, draft.month).indexOf(draft.day) % 7;
      moveDay(event.key === 'Home' ? -index : 6 - index);
    }
  }

  function render(focusDay = false) {
    yearInput.value = String(draft.year);
    monthSelect.value = String(draft.month);
    previous.disabled = draft.year === 1 && draft.month === 1;
    next.disabled = draft.year === 9999 && draft.month === 12;
    error.hidden = true;
    grid.textContent = '';
    const today = new Date();
    const days = monthGrid(draft.year, draft.month);
    const rowCount = Math.ceil((days.lastIndexOf(daysInMonth(draft.year, draft.month)) + 1) / 7);
    for (let rowIndex = 0; rowIndex < rowCount; rowIndex += 1) {
      const row = document.createElement('tr');
      for (let column = 0; column < 7; column += 1) {
        const cell = document.createElement('td');
        const day = days[rowIndex * 7 + column];
        if (day !== null) {
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'date-picker-day';
          button.dataset.day = String(day);
          button.textContent = String(day);
          button.setAttribute('aria-label', `${draft.year}年${draft.month}月${day}日`);
          button.setAttribute('aria-pressed', String(day === draft.day));
          button.tabIndex = day === draft.day ? 0 : -1;
          if (today.getFullYear() === draft.year && today.getMonth() + 1 === draft.month && today.getDate() === day) {
            button.setAttribute('aria-current', 'date');
          }
          button.addEventListener('click', () => { if (applyYear(true)) { draft.day = day; render(true); } });
          button.addEventListener('keydown', keyDay);
          cell.appendChild(button);
        }
        row.appendChild(cell);
      }
      grid.appendChild(row);
    }
    placeDialog();
    if (focusDay) grid.querySelector(`[data-day="${draft.day}"]`)?.focus();
  }

  function close() {
    if (!active) return;
    const trigger = active.trigger;
    active = null;
    dialog.close();
    trigger.setAttribute('aria-expanded', 'false');
    trigger.focus();
  }

  function open(trigger) {
    const input = byId(trigger.dataset.dateFor);
    if (!input || trigger.disabled) return;
    const withTime = trigger.dataset.withTime === 'true';
    const now = new Date();
    draft = parseValue(input.value, withTime) || {
      year: now.getFullYear(), month: now.getMonth() + 1, day: now.getDate(),
      hour: now.getHours(), minute: now.getMinutes(),
    };
    active = { input, trigger, withTime };
    timeControls.hidden = !withTime;
    hourSelect.value = pad(draft.hour);
    minuteSelect.value = pad(draft.minute);
    dialog.setAttribute('aria-label', withTime ? '选择日期和时间' : '选择日期');
    trigger.setAttribute('aria-expanded', 'true');
    render();
    dialog.showModal();
    placeDialog();
    grid.querySelector(`[data-day="${draft.day}"]`)?.focus();
  }

  previous.addEventListener('click', () => moveMonth(-1));
  next.addEventListener('click', () => moveMonth(1));
  monthSelect.addEventListener('change', () => {
    if (!applyYear(true)) { monthSelect.value = String(draft.month); return; }
    draft.month = Number(monthSelect.value);
    draft.day = Math.min(draft.day, daysInMonth(draft.year, draft.month));
    render();
  });
  yearInput.addEventListener('change', () => {
    if (applyYear()) render();
  });
  byId('dateToday').addEventListener('click', () => {
    const today = new Date();
    draft.year = today.getFullYear(); draft.month = today.getMonth() + 1; draft.day = today.getDate();
    render(true);
  });
  byId('dateClear').addEventListener('click', () => {
    const input = active.input, changed = input.value !== '';
    input.value = '';
    sync(input);
    close();
    if (changed) input.dispatchEvent(new Event('change', { bubbles: true }));
  });
  byId('dateCancel').addEventListener('click', close);
  byId('dateConfirm').addEventListener('click', () => {
    if (!applyYear(true)) return;
    const date = `${String(draft.year).padStart(4, '0')}-${pad(draft.month)}-${pad(draft.day)}`;
    const value = active.withTime ? `${date}T${hourSelect.value}:${minuteSelect.value}` : date;
    if (active.withTime) {
      const local = new Date(value);
      if (!Number.isFinite(local.getTime()) || local.getFullYear() !== draft.year || local.getMonth() + 1 !== draft.month
          || local.getDate() !== draft.day || local.getHours() !== Number(hourSelect.value) || local.getMinutes() !== Number(minuteSelect.value)) {
        error.textContent = '此本地时间无效，请选择其他时间。';
        error.hidden = false;
        placeDialog();
        return;
      }
    }
    const input = active.input, changed = input.value !== value;
    input.value = value;
    sync(input);
    close();
    if (changed) input.dispatchEvent(new Event('change', { bubbles: true }));
  });
  dialog.addEventListener('cancel', (event) => { event.preventDefault(); close(); });
  dialog.addEventListener('click', (event) => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) close();
  });
  window.addEventListener('resize', placeDialog);
  window.visualViewport?.addEventListener('resize', placeDialog);
  window.visualViewport?.addEventListener('scroll', placeDialog);
  triggers.forEach((trigger) => {
    const input = byId(trigger.dataset.dateFor);
    if (!input) return;
    trigger.addEventListener('click', () => open(trigger));
    sync(input);
    input.hidden = true;
    trigger.hidden = false;
  });
})();
