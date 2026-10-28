/* 教师看板：把统计接口的数值填进模板留好的槽位，画两张图。
   区间与「能不能比较」都由接口给，这里不重算差分隐私。 */
(function () {
  'use strict';

  const f = window.Charts.fmt;
  const board = document.getElementById('board');
  const code = board.dataset.course;
  let publicationId = null;
  let exporting = false;
  let refreshing = false;
  let ready = false;
  let chartData = null;

  const el = (id) => document.getElementById(id);

  function setText(id, text) {
    const node = el(id);
    if (node) node.textContent = text;
  }

  function stamp(iso) {
    return iso ? iso.slice(0, 16).replace('T', ' ') : '';
  }

  function drawPublished(data) {
    setText('courseTitle', data.courseTitle);
    setText('courseSub',
      [data.term, data.courseCode,
        `已发评价码 ${f.int(data.enrolled)} 个`,
        `有效评价 ${f.int(data.responses)} 份（${f.pct(1)(data.responses / data.enrolled)}）`]
        .filter(Boolean).join(' · '));

    const state = el('publishState');
    state.textContent = '已发布';
    state.classList.remove('refused');
    state.hidden = false;
    el('refused').hidden = true;

    setText('pooledMean', f.dec(2)(data.pooledMean));
    setText('interval', `±${f.dec(2)(data.interval)}`);
    setText('sampleNote', `90% 噪声区间，n=${f.int(data.responses)}`);

    const spread = f.dec(2)(data.spread);
    const interval = f.dec(2)(data.interval);
    setText('finding', data.dimensions.length === 1
      ? '只有一个评价维度，无法进行维度间比较。'
      : data.distinguishable
        ? `${data.dimensions.length} 个维度最高与最低相差 ${spread} 分，噪声区间不重叠。`
        : `${data.dimensions.length} 个维度最高与最低相差 ${spread} 分，±${interval} 的噪声区间重叠。`);
    publicationId = /^[a-f0-9]{32}$/i.test(data.publicationId || '') ? data.publicationId : null;
    el('historyExport').hidden = !publicationId || window.API.USE_MOCK === true;
    if (publicationId) setText('currentPublication', `当前发布编号：${publicationId}`);
    updateExportControls();

    // 先显示再画：容器还 hidden 时量不到宽度，SVG 会画成空的。
    el('published').hidden = false;
    chartData = data;
    redrawCharts();
    drawWords(data.openText);
    setText('record', data.budgetExhausted
      ? `发布于 ${stamp(data.publishedAt)} · 当前预算不足以再次发布`
      : `发布于 ${stamp(data.publishedAt)}`);
  }

  function redrawCharts() {
    if (!chartData || el('published').hidden) return;
    const data = chartData;
    const dims = el('dims');
    window.Charts.intervals(dims, {
      rows: data.dimensions,
      interval: data.interval,
      min: 1,
      max: 5,
    });

    const ratings = data.distribution.reduce((sum, bin) => sum + bin.count, 0);
    setText('ratingCount', `${f.int(ratings)} 份有效评价`);
    const histogram = el('histogram');
    window.Charts.bars(histogram, {
      labels: data.distribution.map((bin) => `${bin.score} 分`),
      values: data.distribution.map((bin) => bin.count),
      format: f.int,
      height: 208,
      unit: ' 份',
    });
  }
  window.addEventListener('resize', () => {
    try { redrawCharts(); }
    catch (failure) {
      clearResults();
      el('refreshStatus').hidden = true;
      el('refreshError').textContent = '结果显示失败，请重新更新。';
      el('refreshError').hidden = false;
    }
  }, { passive: true });

  function updateExportControls() {
    const busy = exporting || refreshing;
    const canExport = Boolean(publicationId) && !busy && window.API.USE_MOCK !== true;
    el('refreshResults').disabled = !ready || busy;
    el('exportPdf').disabled = !canExport;
    el('exportCsv').disabled = !canExport;
    el('historyPdf').disabled = !canExport;
    el('historyCsv').disabled = !canExport;
  }

  async function download(format, target = publicationId) {
    if (!publicationId || exporting || refreshing || window.API.USE_MOCK === true) return;
    exporting = true;
    updateExportControls();
    const error = el('exportError');
    error.hidden = true;
    try {
      const params = new URLSearchParams({ format, publication: target });
      const file = await window.API.downloadWithMetadata(`/api/courses/${encodeURIComponent(code)}/export?${params}`);
      const url = window.URL.createObjectURL(file.blob);
      try {
        const link = document.createElement('a');
        link.href = url;
        link.download = file.filename && file.filename.toLowerCase().endsWith(`.${format}`)
          ? file.filename : `课程评价.${format}`;
        document.body.appendChild(link);
        link.click();
        link.remove();
      } finally {
        window.setTimeout(() => window.URL.revokeObjectURL(url), 1000);
      }
    } catch (failure) {
      if (failure.status === 401) {
        ready = false;
        clearResults();
        window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
      } else {
        if (failure.status === 403) clearResults();
        error.textContent = failure.message || '导出失败，请稍后重试。';
        error.hidden = false;
      }
    } finally {
      exporting = false;
      updateExportControls();
    }
  }

  function downloadHistory(format) {
    const target = el('historyId').value.trim().toLowerCase();
    if (!/^[a-f0-9]{32}$/.test(target)) {
      el('exportError').textContent = '请输入 32 位十六进制发布编号。';
      el('exportError').hidden = false;
      return;
    }
    return download(format, target);
  }

  el('historyPdf').addEventListener('click', () => downloadHistory('pdf'));
  el('historyCsv').addEventListener('click', () => downloadHistory('csv'));
  el('exportPdf').addEventListener('click', () => download('pdf'));
  el('exportCsv').addEventListener('click', () => download('csv'));

  function drawWords(openText) {
    el('words').hidden = true;
    el('wordlist').textContent = '';
    if (!openText || !openText.terms || openText.terms.length === 0) return;
    setText('openTextCount', `${f.int(openText.responses)} 条评语`);
    const list = el('wordlist');
    const max = Math.max(...openText.terms.map((term) => term.count));
    list.textContent = '';
    openText.terms.forEach((term) => {
      const row = document.createElement('li');
      const word = document.createElement('span');
      word.className = 'w';
      word.textContent = term.word;
      const bar = document.createElement('span');
      bar.className = 'bar';
      const fill = document.createElement('i');
      fill.style.width = `${Math.round((term.count / max) * 100)}%`;
      bar.appendChild(fill);
      const count = document.createElement('span');
      count.className = 'c num';
      count.textContent = f.int(term.count);
      row.append(word, bar, count);
      list.appendChild(row);
    });
    el('words').hidden = false;
  }

  function clearResults() {
    publicationId = null;
    chartData = null;
    el('published').hidden = true;
    el('refused').hidden = true;
    el('words').hidden = true;
    el('historyExport').hidden = true;
    el('publishState').hidden = true;
    el('exportError').hidden = true;
    setText('courseTitle', '结果看板');
    setText('courseSub', '');
    setText('record', '');
    setText('currentPublication', '');
    ['pooledMean', 'interval', 'sampleNote', 'finding', 'ratingCount', 'dims', 'histogram', 'wordlist', 'openTextCount']
      .forEach((id) => setText(id, ''));
    updateExportControls();
  }

  function drawRefused(data) {
    clearResults();
    setText('courseTitle', data.courseTitle || '结果看板');
    setText('courseSub', data.courseCode || '');
    const state = el('publishState');
    state.textContent = '不予出数';
    state.classList.add('refused');
    state.hidden = false;

    const exhausted = data.reason === 'budget_exhausted';
    setText('refusedTitle', exhausted
      ? '预算不足，暂时没有可查看的发布结果'
      : `还差 ${f.int(data.shortfall)} 份评价才能出数`);
    setText('refusedWhy', exhausted
      ? '这门课尚无已保存的发布结果，剩余预算不足以发布新结果。请联系管理员调整预算。'
      : `有效评价 ${f.int(data.sample)} 份，没到 k=${f.int(data.threshold)}。`
        + '闸门在这一步挡住整页，均值、分布、维度对比和词频都不返回。');

    const facts = el('refusedFacts');
    facts.textContent = '';
    [['门槛 k', data.threshold], ['当前 n', data.sample],
     exhausted ? ['可用快照', '暂无'] : ['缺口', data.shortfall],
     ['本次扣费', '0.00']].forEach(([label, value]) => {
      const dt = document.createElement('dt');
      dt.textContent = label;
      const dd = document.createElement('dd');
      dd.className = 'num';
      dd.textContent = String(value);
      facts.append(dt, dd);
    });

    el('refused').hidden = false;
  }

  function refreshMessage(data, previous) {
    if (data.state !== 'published') return data.reason === 'budget_exhausted'
      ? '当前预算不足，暂时无法发布结果。' : '当前还没有满足发布条件的结果。';
    if (data.charged || (publicationId && publicationId !== previous)) {
      return (data.charged ? '已发布新的统计结果。' : '已更新至最新发布结果。')
        + (data.budgetExhausted ? '当前预算不足以再次发布。' : '');
    }
    return data.budgetExhausted ? '当前预算不足以发布新结果，继续显示已有结果。'
      : '暂无可发布的新结果，继续显示已有结果。';
  }

  function validResult(data) {
    const number = (value) => typeof value === 'number' && Number.isFinite(value);
    if (!data || typeof data !== 'object') return false;
    if (data.state === 'unpublished') {
      return ['below_threshold', 'budget_exhausted'].includes(data.reason)
        && [data.sample, data.threshold, data.shortfall].every(number);
    }
    if (data.state !== 'published' || !/^[a-f0-9]{32}$/i.test(data.publicationId || '')) return false;
    return ['courseCode', 'courseTitle', 'term', 'publishedAt'].every((key) => typeof data[key] === 'string')
      && ['responses', 'enrolled', 'pooledMean', 'interval', 'spread'].every((key) => number(data[key]))
      && typeof data.distinguishable === 'boolean'
      && Array.isArray(data.dimensions) && data.dimensions.length > 0
      && data.dimensions.every((item) => item && typeof item.name === 'string' && number(item.value))
      && Array.isArray(data.distribution) && data.distribution.length > 0
      && data.distribution.every((item) => item && number(item.score) && number(item.count))
      && data.openText && number(data.openText.responses) && Array.isArray(data.openText.terms)
      && data.openText.terms.every((item) => item && typeof item.word === 'string' && number(item.count));
  }

  async function loadResults(manual = false) {
    if (!ready || refreshing || exporting) return;
    refreshing = true;
    updateExportControls();
    const previous = publicationId;
    const status = el('refreshStatus');
    const error = el('refreshError');
    error.hidden = true;
    status.hidden = false;
    status.textContent = manual ? '正在更新结果…' : '正在加载统计结果…';
    let rendering = false;
    try {
      const data = await window.API.get(`/api/courses/${encodeURIComponent(code)}/statistics`);
      if (!validResult(data)) throw new Error('无效的统计结果');
      rendering = true;
      if (data.state === 'published') drawPublished(data);
      else drawRefused(data);
      rendering = false;
      el('exportError').hidden = true;
      status.hidden = !manual;
      if (manual) status.textContent = refreshMessage(data, previous);
    } catch (failure) {
      status.hidden = true;
      if (failure.status === 401) {
        ready = false;
        clearResults();
        window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
      } else {
        if (rendering || failure.status === 403 || failure.status === 404) clearResults();
        error.textContent = failure.status === 404 ? '这门课没有找到。'
          : failure.status === 403 ? '当前账号无权查看这门课程的结果。'
            : rendering ? '结果显示失败，请重新更新。' : '结果暂时取不到，请重试。';
        error.hidden = false;
      }
    } finally {
      refreshing = false;
      updateExportControls();
    }
  }

  el('refreshResults').addEventListener('click', () => loadResults(true));
  window.SHELL.ready
    .then((session) => { if (session?.account) { ready = true; return loadResults(); } })
    .catch((failure) => {
      if (failure.status === 401) return;
      el('refreshError').textContent = '账号信息暂时取不到，请刷新页面重试。';
      el('refreshError').hidden = false;
    });
})();
