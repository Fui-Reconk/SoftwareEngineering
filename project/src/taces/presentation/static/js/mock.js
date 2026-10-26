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
  };
})();
