/* 教师看板：把统计接口的数值填进模板留好的槽位，画两张图。
   区间与「能不能比较」都由接口给，这里不重算差分隐私。 */
(function () {
  'use strict';

  const f = window.Charts.fmt;
  const board = document.getElementById('board');
  const code = board.dataset.course;
  let publicationId = null;
  let exporting = false;

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
        `选课 ${f.int(data.enrolled)} 人`,
        `有效评价 ${f.int(data.responses)} 份（${f.pct(1)(data.responses / data.enrolled)}）`]
        .filter(Boolean).join(' · '));

    const state = el('publishState');
    state.textContent = '已发布';
    state.hidden = false;

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
    el('historyExport').hidden = !publicationId;
    if (publicationId) setText('currentPublication', `当前发布编号：${publicationId}`);
    updateExportControls();

    // 先显示再画：容器还 hidden 时量不到宽度，SVG 会画成空的。
    el('published').hidden = false;
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
    const draw = () => window.Charts.bars(histogram, {
      labels: data.distribution.map((bin) => `${bin.score} 分`),
      values: data.distribution.map((bin) => bin.count),
      format: f.int,
      height: 208,
      unit: ' 份',
    });
    draw();
    const redrawAll = () => {
      draw();
      window.Charts.intervals(dims, {
        rows: data.dimensions,
        interval: data.interval,
        min: 1,
        max: 5,
      });
    };
    window.addEventListener('resize', redrawAll, { passive: true });

    drawWords(data.openText);
    setText('record', data.budgetExhausted
      ? `发布于 ${stamp(data.publishedAt)} · 预算已用完，这份不会再更新`
      : `发布于 ${stamp(data.publishedAt)}`);
  }

  function updateExportControls() {
    el('exportPdf').disabled = !publicationId || exporting;
    el('exportCsv').disabled = !publicationId || exporting;
    el('historyPdf').disabled = !publicationId || exporting;
    el('historyCsv').disabled = !publicationId || exporting;
  }

  async function download(format, target = publicationId) {
    if (!publicationId || exporting) return;
    exporting = true;
    updateExportControls();
    const error = el('exportError');
    error.hidden = true;
    try {
      const params = new URLSearchParams({ format, publication: target });
      const blob = await window.API.download(`/api/courses/${encodeURIComponent(code)}/export?${params}`);
      const url = window.URL.createObjectURL(blob);
      try {
        const link = document.createElement('a');
        link.href = url;
        link.download = `statistics-${target}.${format}`;
        document.body.appendChild(link);
        link.click();
        link.remove();
      } finally {
        window.setTimeout(() => window.URL.revokeObjectURL(url), 1000);
      }
    } catch (failure) {
      if (failure.status === 401) {
        window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
      } else {
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

  function drawRefused(data) {
    setText('courseTitle', data.courseTitle || '结果看板');
    setText('courseSub', data.courseCode || '');
    const state = el('publishState');
    state.textContent = '不予出数';
    state.classList.add('refused');
    state.hidden = false;

    const exhausted = data.reason === 'budget_exhausted';
    setText('refusedTitle', exhausted
      ? '预算已用完，暂时没有可查看的发布结果'
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

  function showError(message) {
    setText('courseSub', message);
  }

  window.SHELL.ready
    .then(() => window.API.get(`/api/courses/${encodeURIComponent(code)}/statistics`))
    .then((data) => (data.state === 'published' ? drawPublished(data) : drawRefused(data)))
    .catch((failure) => {
      if (failure.status === 401) return;
      showError(failure.status === 404
        ? '这门课没有找到。'
        : '这份结果暂时取不到，刷新再试。');
    });
})();
