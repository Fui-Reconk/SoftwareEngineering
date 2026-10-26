/* 两张图和一条区间轴，按 app-screens §6 手绘 SVG：一条序列一个色，横向网格线 3–5 条、
   刻度取整并高过最大值，柱形方角、无渐变、无图例（单序列不需要），坐标文字 11–12px。
   宽度取容器的实际像素，容器尺寸变化时重画，不用 viewBox 拉伸去糊。 */
window.Charts = (() => {
  'use strict';

  const NS = 'http://www.w3.org/2000/svg';
  const MINUS = '\u2212';

  const node = (tag, attrs, parent) => {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v != null) n.setAttribute(k, v);
    if (parent) parent.appendChild(n);
    return n;
  };
  const text = (parent, str, attrs) => {
    const t = node('text', attrs, parent);
    t.textContent = str;
  };
  const span = (parent, cls, str) => {
    const s = document.createElement('span');
    s.className = cls;
    if (str != null) s.textContent = str;
    parent.appendChild(s);
    return s;
  };
  const css = (el, name, fallback) => getComputedStyle(el).getPropertyValue(name).trim() || fallback;

  const nf = (opts) => new Intl.NumberFormat(document.documentElement.lang || 'zh-CN', opts);
  const fmt = {
    int: (v) => nf({ maximumFractionDigits: 0 }).format(v),
    dec: (d) => (v) => nf({ minimumFractionDigits: d, maximumFractionDigits: d }).format(v),
    pct: (d = 1) => (v) => nf({ style: 'percent', minimumFractionDigits: d, maximumFractionDigits: d }).format(v),
    signed: (f) => (v) => (v > 0 ? '+' : v < 0 ? MINUS : '') + f(Math.abs(v)),
  };

  /* 取整刻度，顶格高过最大值，0 永远在底 */
  function ticks(max, count = 4) {
    const raw = max / count;
    const mag = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || 10 * mag;
    const top = Math.ceil(max / step) * step;
    const out = [];
    for (let v = 0; v <= top + step / 2; v += step) out.push(Math.round(v * 1000) / 1000);
    return out;
  }

  const PALETTE = (host) => ({
    grid: css(host, '--grid', '#e5e5e5'),
    base: css(host, '--border', '#e8e8e8'),
    ink: css(host, '--axis-ink', '#5f6368'),
    hue: css(host, '--chart-1', '#1b6c80'),
    band: css(host, '--chart-band', 'rgba(27, 108, 128, 0.2)'),
    bandEdge: css(host, '--chart-band-edge', 'rgba(27, 108, 128, 0.42)'),
    rule: css(host, '--rule', '#f0f1f2'),
  });

  /* 竖柱图，一档一根 */
  function bars(host, { labels, values, format = fmt.int, height = 200, unit = '' } = {}) {
    const w = host.clientWidth;
    host.textContent = '';
    if (!w || !values.length) return;
    const c = PALETTE(host);
    const pad = { t: 12, r: 6, b: 26, l: 34 };
    const plotW = w - pad.l - pad.r;
    const plotH = height - pad.t - pad.b;
    // 全零时也要有个刻度，否则 ticks(0) 会算出 NaN
    const maxValue = Math.max(...values);
    const list = ticks(maxValue > 0 ? maxValue : 1);
    const high = list[list.length - 1];
    const svg = node('svg', {
      width: w, height, viewBox: `0 0 ${w} ${height}`, role: 'img',
      'aria-label': labels.map((l, i) => `${l} ${format(values[i])}${unit}`).join('；'),
    }, host);
    /* 透明的接指针面，保证空白处也能读到悬停位置 */
    node('rect', { x: 0, y: 0, width: w, height, fill: 'none', 'pointer-events': 'all' }, svg);

    list.forEach((t) => {
      const y = Math.round(pad.t + plotH * (1 - t / high)) + 0.5;
      if (t > 0) node('line', { x1: pad.l, x2: w - pad.r, y1: y, y2: y, stroke: c.grid, 'stroke-width': 1 }, svg);
      text(svg, format(t), {
        x: pad.l - 8, y: y + 4, 'text-anchor': 'end', fill: c.ink, 'font-size': 11,
      });
    });
    node('line', {
      x1: pad.l, x2: w - pad.r, y1: Math.round(pad.t + plotH) + 0.5,
      y2: Math.round(pad.t + plotH) + 0.5, stroke: c.base, 'stroke-width': 1,
    }, svg);

    const slot = plotW / values.length;
    const barW = Math.min(64, slot * 0.52);
    const total = values.reduce((a, b) => a + b, 0);
    const columns = [];

    values.forEach((v, i) => {
      const h = (v / high) * plotH;
      const x = Math.round(pad.l + slot * i + (slot - barW) / 2);
      columns.push(node('rect', {
        x, y: Math.round(pad.t + plotH - h), width: Math.round(barW), height: Math.round(h), fill: c.hue,
      }, svg));
      text(svg, labels[i], {
        x: Math.round(pad.l + slot * i + slot / 2), y: height - 8,
        'text-anchor': 'middle', fill: c.ink, 'font-size': 12,
      });
    });

    /* 悬停读数：指到哪一档，就把那一档的条数和占比写在条的上方，其余几档压暗 */
    const tip = document.createElement('div');
    tip.className = 'chart-tip';
    tip.hidden = true;

    const show = (i) => {
      const v = values[i];
      tip.textContent = `${labels[i]} · ${format(v)}${unit}`
        + (total ? ` · ${fmt.pct(1)(v / total)}` : '');
      tip.hidden = false;
      const half = tip.offsetWidth / 2;
      const centre = pad.l + slot * i + slot / 2;
      tip.style.left = `${Math.min(Math.max(centre, half + 2), w - half - 2)}px`;
      tip.style.top = `${Math.round(pad.t + plotH - (v / high) * plotH) - 6}px`;
      columns.forEach((col, j) => col.setAttribute('fill-opacity', j === i ? '1' : '0.5'));
    };
    const hide = () => {
      tip.hidden = true;
      columns.forEach((col) => col.setAttribute('fill-opacity', '1'));
    };

    svg.addEventListener('pointermove', (event) => {
      const x = event.clientX - svg.getBoundingClientRect().left;
      const i = Math.floor((x - pad.l) / slot);
      if (x < pad.l || x > w - pad.r || i < 0 || i >= values.length) hide();
      else show(i);
    });
    svg.addEventListener('pointerleave', hide);
    host.appendChild(tip);
  }

  /* 三行区间共用一个 1–5 轴：带色段是噪声区间，竖线是现值。
     两段的色带一重叠，两个维度就分不出高下。 */
  function intervals(host, { rows, interval, min, max, format = fmt.dec(2) } = {}) {
    host.textContent = '';
    const c = PALETTE(host);
    const wrap = document.createElement('div');
    wrap.className = 'ivl';
    host.appendChild(wrap);

    const line = (name, value) => {
      const r = document.createElement('div');
      r.className = 'ivl-row';
      span(r, 'ivl-name', name);
      const cell = span(r, 'ivl-track');
      span(r, 'ivl-value num', value == null ? '' : format(value));
      wrap.appendChild(r);
      return cell;
    };

    const cells = rows.map((row) => line(row.name, row.value));
    const axisCell = line('', null);
    axisCell.parentElement.classList.add('ivl-axis');

    const drawTrack = (cell, row) => {
      const width = cell.clientWidth;
      if (!width) return;
      const sx = (v) => ((v - min) / (max - min)) * width;
      const svg = node('svg', { width, height: 16, viewBox: `0 0 ${width} 16`, 'aria-hidden': 'true' }, cell);
      node('rect', { x: 0, y: 7, width, height: 1, fill: c.rule }, svg);
      const lo = Math.max(min, row.value - interval);
      const hi = Math.min(max, row.value + interval);
      node('rect', {
        x: Math.round(sx(lo)), y: 2, width: Math.max(2, Math.round(sx(hi) - sx(lo))),
        height: 12, fill: c.band, stroke: c.bandEdge, 'stroke-width': 1, rx: 2,
      }, svg);
      node('rect', { x: Math.round(sx(row.value)) - 1, y: 0, width: 2, height: 16, fill: c.hue }, svg);
    };

    const drawAxis = (cell) => {
      const width = cell.clientWidth;
      if (!width) return;
      const svg = node('svg', { width, height: 16, viewBox: `0 0 ${width} 16`, 'aria-hidden': 'true' }, cell);
      node('rect', { x: 0, y: 0, width, height: 1, fill: c.rule }, svg);
      for (let v = min; v <= max; v += 1) {
        const x = Math.round(((v - min) / (max - min)) * width);
        node('rect', { x, y: 0, width: 1, height: 4, fill: c.rule }, svg);
        text(svg, String(v), {
          x, y: 15,
          'text-anchor': v === min ? 'start' : v === max ? 'end' : 'middle',
          fill: c.ink, 'font-size': 11,
        });
      }
    };

    rows.forEach((row, i) => drawTrack(cells[i], row));
    drawAxis(axisCell);
  }

  return { bars, intervals, ticks, fmt };
})();
