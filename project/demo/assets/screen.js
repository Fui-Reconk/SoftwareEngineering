/* 把 data.js 的数值摆到页面上。切换课程只换一份视图，
   被 k 闸门拦住的课程走另一套版式：整页只说一句为什么不出数。 */
(() => {
  'use strict';

  const d = window.TACES;
  const f = window.Charts.fmt;
  const sheet = document.getElementById('sheet');
  const courseList = document.getElementById('courseList');
  const topbarContext = document.getElementById('topbarContext');
  const topbarStamp = document.getElementById('topbarStamp');

  let redraw = [];

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };
  const add = (parent, tag, cls, text) => {
    const n = el(tag, cls, text);
    parent.appendChild(n);
    return n;
  };

  /* ---------- 左侧课程列表 ---------- */
  function renderCourses(activeCode) {
    courseList.textContent = '';
    d.courses.forEach((course) => {
      const btn = el('button', 'course');
      btn.type = 'button';
      btn.dataset.code = course.code;
      if (course.code === activeCode) btn.setAttribute('aria-current', 'true');
      add(btn, 'span', 'course-title', course.title);
      const meta = add(btn, 'span', 'course-meta');
      add(meta, 'span', 'num', String(course.responses));
      add(meta, 'span', null, course.state === 'gated'
        ? ` 份，不足 ${d.params.k}`
        : ' 份评价');
      if (course.state === 'gated') meta.classList.add('short');
      btn.addEventListener('click', () => render(course.code));
      courseList.appendChild(btn);
    });
  }

  /* ---------- 主版式 ---------- */
  function render(code) {
    const course = d.courses.find((c) => c.code === code) || d.courses[0];
    renderCourses(course.code);
    topbarContext.textContent = `${d.institution} · ${d.term}`;
    topbarStamp.textContent = `数据截至 ${d.record.sealed}`;
    document.title = `${course.title} · 结果看板 · TACES`;
    sheet.textContent = '';
    redraw = [];
    (course.state === 'gated' ? renderGated : renderBoard)(course);
    drawCharts();
    sheet.focus({ preventScroll: true });
  }

  function titleRow(course, sub, action) {
    const row = add(sheet, 'div', 'title-row');
    const left = add(row, 'div');
    add(left, 'h1', null, course.title);
    add(left, 'p', 'sub', sub);
    const right = add(row, 'div', 'title-actions');
    if (action) right.appendChild(action);
    return right;
  }

  function stampBox(text, refused) {
    return el('span', 'stamp-box' + (refused ? ' refused' : ''), text);
  }

  function renderBoard(course) {
    const s = d.stats;
    const rate = f.pct(1)(s.submitRate);

    titleRow(
      course,
      `${course.code} · 选课 ${course.enrolled} 人，收到有效评价 ${course.responses} 份（${rate}）· 评教窗口 ${course.window.from} 至 ${course.window.to}`,
      null,
    ).append(
      stampBox('可发布'),
      (() => {
        const b = el('button', 'btn', '导出 PDF');
        b.type = 'button';
        return b;
      })(),
    );

    /* 主卡：左边一个问题，右边它的证据 */
    const report = add(sheet, 'section', 'panel report');
    const left = add(report, 'div', 'report-left');
    add(left, 'p', 'kpi-label', '联合均分 · 1–5 分');
    const answer = add(left, 'p', 'answer');
    add(answer, 'span', 'answer-value num', f.dec(2)(s.pooledMean));
    add(answer, 'span', 'answer-ci', `±${f.dec(2)(s.interval)}`);
    add(left, 'p', 'answer-note', `90% 噪声区间，n=${course.responses}`);
    add(left, 'p', 'finding',
      `三个维度相差 ${f.dec(2)(s.spread)} 分，落在 ±${f.dec(2)(s.interval)} 的噪声之内，`
      + '这一学期分不出哪个更弱。');

    const dims = add(left, 'div', 'dims');
    add(left, 'p', 'caption', '色带是 90% 噪声区间；两段一重叠，就读不出先后。');

    const right = add(report, 'div', 'report-right');
    const head = add(right, 'div', 'chart-head');
    add(head, 'h2', null, '评分分布');
    add(head, 'span', 'meta', `${s.ratings} 条单项评分`);
    const hist = add(right, 'div', 'chart');
    add(right, 'p', 'caption', '一份评价在三个维度上各记一条单项评分。');

    redraw.push(
      () => window.Charts.intervals(dims, {
        rows: course.dimensions,
        interval: s.interval,
        min: 1,
        max: 5,
      }),
      () => window.Charts.bars(hist, {
        labels: course.distribution.map((b) => `${b.score} 分`),
        values: course.distribution.map((b) => b.count),
        format: f.int,
        height: 208,
        unit: ' 条',
      }),
    );

    /* 第二块：学生写了什么。整行给到它，词条和条的长度都撑得开 */
    const words = add(sheet, 'section', 'panel words');
    const wHead = add(words, 'header');
    add(wHead, 'h2', null, '开放题高频词');
    add(wHead, 'span', 'meta', `${course.openText.responses} 条评语`);
    const list = add(words, 'ul', 'wordlist');
    const max = Math.max(...course.openText.terms.map((t) => t.count));
    course.openText.terms.forEach((term, i) => {
      const li = add(list, 'li', i === 0 ? 'top' : null);
      add(li, 'span', 'w', term.word);
      const bar = add(li, 'span', 'bar');
      const fill = add(bar, 'i');
      fill.style.width = `${Math.round((term.count / max) * 100)}%`;
      add(li, 'span', 'c num', f.int(term.count));
    });
    add(words, 'p', 'caption foot', '只出高频词，原文不进接口。');

    add(sheet, 'p', 'record', `记录 ${d.record.id} · 归档 ${d.record.sealed}`);
  }

  function renderGated(course) {
    const s = d.stats;
    titleRow(
      course,
      `${course.code} · 选课 ${course.enrolled} 人，收到有效评价 ${course.responses} 份 · 评教窗口 ${course.window.from} 至 ${course.window.to}`,
      stampBox('不予出数', true),
    );

    const panel = add(sheet, 'section', 'panel gated');
    const body = add(panel, 'div', 'gated-main');
    add(body, 'p', 'gated-title', `还差 ${s.shortfall} 份评价才能出数`);
    add(body, 'p', 'gated-text',
      `有效评价 ${course.responses} 份，没到 k=${d.params.k}。`
      + '闸门在这一步挡住整页，均值、分布、维度对比和词频都不返回，'
      + '因为样本太少时，任何一项都足以让人反推出某一个人的打分。');
    add(body, 'p', 'gated-text',
      `窗口已于 ${course.window.to} 关闭，选课 ${course.enrolled} 人里只有 ${course.responses} 人提交，`
      + `提交率 ${f.pct(1)(course.responses / course.enrolled)}。`
      + '下次开课时报名人数和提交率都会重新计算，这一页不会因为下一次的评价而改变。');
    add(body, 'p', 'caption', '被拒绝的查询不扣预算，账本上不留这一笔。');

    const facts = add(panel, 'dl', 'gated-facts');
    [
      ['门槛 k', String(d.params.k)],
      ['当前 n', String(course.responses)],
      ['缺口', String(s.shortfall)],
      ['本次扣费', '0.00'],
    ].forEach(([label, value]) => {
      add(facts, 'dt', null, label);
      add(facts, 'dd', 'num', value);
    });

    add(sheet, 'p', 'record', `记录 ${d.record.id} · 归档 ${d.record.sealed}`);
  }

  /* ---------- 重画 ---------- */
  let frame = 0;
  function drawCharts() {
    redraw.forEach((fn) => fn());
  }
  window.addEventListener('resize', () => {
    window.cancelAnimationFrame(frame);
    frame = window.requestAnimationFrame(drawCharts);
  }, { passive: true });
  if (document.fonts) document.fonts.ready.then(drawCharts);

  /* ---------- 手机上的课程抽屉 ---------- */
  const sidebar = document.getElementById('sidebar');
  const backdrop = document.getElementById('backdrop');
  const toggle = document.getElementById('menuToggle');
  const setMenu = (open) => {
    sidebar.classList.toggle('open', open);
    backdrop.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
  };
  toggle.addEventListener('click', () => setMenu(!sidebar.classList.contains('open')));
  backdrop.addEventListener('click', () => setMenu(false));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && sidebar.classList.contains('open')) setMenu(false);
  });
  courseList.addEventListener('click', () => setMenu(false));
  document.getElementById('signOut').addEventListener('click', () => setMenu(false));

  render(d.courses[0].code);
})();
