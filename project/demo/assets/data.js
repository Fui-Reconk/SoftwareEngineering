/* 看板数据。一门课一条记录，页面要用的东西都在里面，不再分「列表用的」和「正文用的」两份。
   数值只在这里定义一次；末尾四条断言守着不能自相矛盾的地方：分布合计与加权均值都要落在联合均分上，
   区间由 ε 与 n 现算，而不是另填一个数字。 */
window.TACES = (() => {
  'use strict';

  const MIN_SCORE = 1;
  const MAX_SCORE = 5;

  /* 参数取自《设计流程》5.1，将来与 business/config 的默认值一致 */
  const params = { k: 5, epsilonTotal: 4, epsilonPerQuery: 0.1 };

  const institution = '暨南大学';
  const term = '2025–2026 学年第二学期';
  const teacher = { name: '李砚秋', role: '教师', dept: '计算机科学系' };
  const record = { id: 'TACES-2026S-0231', sealed: '2026-06-30 10:13' };
  const window = { from: '06-08', to: '06-26' };

  const courses = [
    {
      code: 'SE201-03',
      title: '数据结构',
      state: 'published',
      enrolled: 287,
      responses: 235,
      window,
      /* 三个维度与联合均分均已加噪。三者差值小于区间，
         所以「哪个维度更弱」这一学期是判不出来的。 */
      dimensions: [
        { name: '教学内容', value: 4.02 },
        { name: '教学方法', value: 3.84 },
        { name: '考核方式', value: 3.72 },
      ],
      /* 一份评价三个维度各一条单项评分，235 份合计 705 条 */
      distribution: [
        { score: 1, count: 15 },
        { score: 2, count: 52 },
        { score: 3, count: 139 },
        { score: 4, count: 310 },
        { score: 5, count: 189 },
      ],
      openText: {
        responses: 118,
        terms: [
          { word: '作业', count: 42 },
          { word: '讲解', count: 38 },
          { word: '实验', count: 31 },
          { word: '节奏', count: 27 },
          { word: '考试', count: 24 },
          { word: '课件', count: 21 },
          { word: '答疑', count: 17 },
          { word: '给分', count: 12 },
        ],
      },
    },
    {
      code: 'GE105-02',
      title: '软件工程导论',
      state: 'gated',
      enrolled: 96,
      responses: 3,
      window,
    },
  ];

  const board = courses[0];
  const gated = courses[1];

  const round = (v, d) => Math.round(v * 10 ** d) / 10 ** d;
  const units = board.dimensions.length;
  const ratings = board.responses * units;
  const pooledMean = round(board.dimensions.reduce((s, d) => s + d.value, 0) / units, 2);

  const histogramTotal = board.distribution.reduce((s, b) => s + b.count, 0);
  const histogramMean = round(
    board.distribution.reduce((s, b) => s + b.score * b.count, 0) / histogramTotal, 4);

  /* 均值查询的全局敏感度：一个人的评分变动最多改动 4/n。
     噪声尺度 b = Δf/ε，90% 双侧区间半宽 = b·ln10。 */
  const sensitivity = (MAX_SCORE - MIN_SCORE) / board.responses;
  const scale = sensitivity / params.epsilonPerQuery;
  const interval = round(scale * Math.LN10, 2);

  const values = board.dimensions.map((d) => d.value);
  const spread = round(Math.max(...values) - Math.min(...values), 2);

  const stats = {
    units,
    ratings,
    pooledMean,
    histogramTotal,
    histogramMean,
    sensitivity,
    scale,
    interval,
    spread,
    /* 区间一重叠，两个维度的先后顺序就不能当结论用 */
    distinguishable: spread > interval * 2,
    submitRate: board.responses / board.enrolled,
    shortfall: Math.max(0, params.k - gated.responses),
  };

  console.assert(ratings === 705, '单项评分条数应为 705');
  console.assert(histogramTotal === ratings, '分布合计应等于单项评分条数');
  console.assert(Math.abs(histogramMean - pooledMean) < 0.005, '分布加权均值应与联合均分一致');
  console.assert(!stats.distinguishable, '差值超过两倍区间时，那句结论要改写');

  return { params, institution, term, teacher, record, courses, board, gated, stats };
})();
