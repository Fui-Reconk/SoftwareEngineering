/* 假数据。形状对齐 docs/AUTH.md 里各接口的 data 部分，接后端后整个文件可删。
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
        { code: 'SE201-03', title: '数据结构', term: '2025–2026 学年第二学期' },
        { code: 'GE105-02', title: '软件工程导论', term: '2025–2026 学年第二学期' },
      ],
    },
  };
})();
