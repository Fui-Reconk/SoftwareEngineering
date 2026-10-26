/* 假数据。形状对齐 project/docs/API_CONTRACT.md，接后端后整个文件可删。
   演示口令写在这里只为让 mock 能走通，不是真账号。 */
(function () {
  'use strict';

  const TEACHER = {
    user_id: 'a-liyanqiu',
    username: 'liyanqiu',
    role: 'teacher',
    is_active: true,
    created_at: 1766500000,
  };

  const SESSION = {
    account: TEACHER,
    csrf_token: 'mock-csrf-token',
    expires_at: 1770000000,
  };

  const TERM = '2025–2026 学年第二学期';

  const PUBLISHED = {
    state: 'published',
    courseCode: 'SE201-03',
    courseTitle: '数据结构',
    term: TERM,
    responses: 235,
    enrolled: 287,
    publishedAt: '2026-06-30T10:13:00+08:00',
    pooledMean: 3.86,
    interval: 0.39,
    spread: 0.3,
    distinguishable: false,
    dimensions: [
      { name: '教学内容', value: 4.02 },
      { name: '教学方法', value: 3.84 },
      { name: '考核方式', value: 3.72 },
    ],
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
        { word: '板书', count: 10 },
        { word: '例题', count: 8 },
        { word: '练习', count: 7 },
        { word: '反馈', count: 6 },
      ],
    },
  };

  const REFUSED = {
    state: 'unpublished',
    reason: 'below_threshold',
    courseCode: 'GE105-02',
    courseTitle: '软件工程导论',
    sample: 3,
    threshold: 5,
    shortfall: 2,
    charged: false,
  };

  const CONFIG = {
    values: { epsilon: 0.1, k: 5, epsilonTotal: 4.0 },
    ranges: {
      epsilon: { min: 0.01, max: 1.0 },
      k: { min: 3, max: 50 },
      epsilonTotal: { min: 0.1, max: 20.0 },
    },
    units: { epsilon: 'ε', k: '份', epsilonTotal: 'ε' },
  };

  window.MOCK = {
    '/api/auth/login': function (body) {
      if (body && body.password === 'taces2026') return SESSION;
      return {
        __error: {
          status: 401,
          code: 'INVALID_CREDENTIALS',
          message: '用户名或密码不对。',
        },
      };
    },
    '/api/auth/me': SESSION,
    '/api/courses': {
      courses: [
        { code: 'SE201-03', title: '数据结构' },
        { code: 'GE105-02', title: '软件工程导论' },
      ],
    },
    '/api/courses/SE201-03/statistics': PUBLISHED,
    '/api/courses/GE105-02/statistics': REFUSED,
    /* 演示用：全 0 当作已用、全 1 当作不存在、全 2 当作窗口关闭，其余都通过。 */
    '/api/evaluation-codes/verify': function (body) {
      const code = (body && body.code) || '';
      if (/^0+$/.test(code)) return { valid: false, reason: 'used' };
      if (/^1+$/.test(code)) return { valid: false, reason: 'unknown' };
      if (/^2+$/.test(code)) return { valid: false, reason: 'expired' };
      return {
        valid: true,
        course: {
          code: 'SE201-03',
          title: '数据结构',
          teacher: '李砚秋',
          dimensions: [
            { name: '教学内容' },
            { name: '教学方法' },
            { name: '考核方式' },
          ],
        },
      };
    },
    '/api/submissions': function (body) {
      if (!body || !body.code || !Array.isArray(body.ratings) || body.ratings.length === 0) {
        return { __error: { status: 422, code: 'INVALID_SUBMISSION', message: '这份评分不完整。' } };
      }
      return { submissionId: 'sub-2026-0001' };
    },
    '/api/admin/config': function (body) {
      if (body && body.values) {
        const bad = Object.entries(body.values).find(([key, value]) => {
          const range = CONFIG.ranges[key];
          return range && (value < range.min || value > range.max);
        });
        if (bad) {
          return { __error: { status: 422, code: 'INVALID_VALUE', message: `${{ epsilon: 'ε', k: 'k', epsilonTotal: '预算总量' }[bad[0]] || bad[0]} 超出允许范围。` } };
        }
        return { values: body.values, ranges: CONFIG.ranges, units: CONFIG.units };
      }
      return CONFIG;
    },
    '/api/admin/audit': function () {
      const raw = [
        ['2026-06-30T10:13:00+08:00', '李砚秋', '查看统计', '数据结构', 0],
        ['2026-06-30T10:12:00+08:00', '李砚秋', '发布统计', '数据结构', 0.1],
        ['2026-06-28T16:40:00+08:00', '王敏', '修改参数', 'ε 0.20 改为 0.10', 0],
        ['2026-06-28T16:38:00+08:00', '王敏', '修改参数', 'k 3 改为 5', 0],
        ['2026-06-28T09:02:00+08:00', '王敏', '创建账号', 'liyanqiu', 0],
        ['2026-06-27T20:31:00+08:00', '陈立', '查看审计日志', '—', 0],
        ['2026-06-27T15:07:00+08:00', '李砚秋', '发布统计', '软件工程导论', 0.1],
        ['2026-06-26T18:22:00+08:00', '王敏', '修改参数', 'ε 总量 2.00 改为 4.00', 0],
        ['2026-06-26T11:45:00+08:00', '李砚秋', '登录', '—', 0],
        ['2026-06-25T14:03:00+08:00', '陈立', '查看审计日志', '—', 0],
        ['2026-06-25T09:58:00+08:00', '王敏', '停用账号', 'temp-auditor', 0],
        ['2026-06-24T17:12:00+08:00', '李砚秋', '查看统计', '数据结构', 0],
        ['2026-06-24T17:11:00+08:00', '李砚秋', '发布统计', '数据结构', 0.1],
        ['2026-06-23T10:26:00+08:00', '王敏', '创建账号', 'chenli', 0],
        ['2026-06-22T16:49:00+08:00', '陈立', '登录', '—', 0],
        ['2026-06-21T08:31:00+08:00', '李砚秋', '登录失败', 'liyanqiu', 0],
        ['2026-06-20T13:14:00+08:00', '王敏', '修改参数', 'ε 0.10 改为 0.20', 0],
        ['2026-06-19T19:05:00+08:00', '李砚秋', '登录', '—', 0],
      ];
      return {
        entries: raw.map(([at, actor, action, target, epsCost]) => ({ at, actor, action, target, epsCost })),
        next: null,
        courses: [
          { code: 'SE201-03', title: '数据结构' },
          { code: 'GE105-02', title: '软件工程导论' },
        ],
      };
    },
  };
})();
