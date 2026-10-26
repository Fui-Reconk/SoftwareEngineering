/* 隐私参数：范围与单位都由接口给，页面不写死数字；保存后原地给一句「已生效」。 */
(function () {
  'use strict';

  const FIELDS = ['epsilon', 'k', 'epsilonTotal'];
  const inputs = {
    epsilon: document.getElementById('epsilonInput'),
    k: document.getElementById('kInput'),
    epsilonTotal: document.getElementById('epsilonTotalInput'),
  };
  const error = document.getElementById('configError');
  const saved = document.getElementById('configSaved');
  const button = document.getElementById('saveConfig');
  let ranges = {};

  function describe(key, range, unit) {
    return `允许 ${range.min} 到 ${range.max}${unit || ''}`;
  }

  function validate() {
    error.hidden = true;
    for (const key of FIELDS) {
      const range = ranges[key];
      if (!range) continue;
      const value = Number(inputs[key].value);
      if (!Number.isFinite(value) || value < range.min || value > range.max) {
        error.textContent = `${key} 超出允许范围（${range.min} 到 ${range.max}）。`;
        error.hidden = false;
        return null;
      }
    }
    return FIELDS.reduce((acc, key) => {
      acc[key] = Number(inputs[key].value);
      return acc;
    }, {});
  }

  async function load() {
    try {
      const config = await window.API.get('/api/admin/config');
      ranges = config.ranges || {};
      FIELDS.forEach((key) => {
        inputs[key].value = config.values[key];
        const hint = document.getElementById(`${key}Range`);
        if (hint && ranges[key]) hint.textContent = describe(key, ranges[key], config.units?.[key]);
      });
    } catch (failure) {
      error.textContent = '参数取不到，刷新再试。';
      error.hidden = false;
      button.disabled = true;
    }
  }

  button.addEventListener('click', async () => {
    const values = validate();
    if (!values) return;
    button.disabled = true;
    saved.hidden = true;
    try {
      const config = await window.API.patch('/api/admin/config', { values });
      FIELDS.forEach((key) => {
        if (config && config.values) inputs[key].value = config.values[key];
      });
      saved.hidden = false;
    } catch (failure) {
      error.textContent = failure.message || '保存失败，再试一次。';
      error.hidden = false;
    } finally {
      button.disabled = false;
    }
  });

  load();
})();
