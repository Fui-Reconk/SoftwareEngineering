/* 入口：会话 Cookie 的作用域是 /api，页面路由在服务端读不到它，
   所以按角色分流只能在浏览器里做。 */
(function () {
  'use strict';

  const note = document.getElementById('entryNote');

  async function go() {
    const session = await window.API.get('/api/auth/me');
    const role = session.account.role;

    if (role === 'admin') {
      window.location.replace('/admin/config');
      return;
    }
    if (role === 'auditor') {
      window.location.replace('/admin/audit');
      return;
    }
    if (role === 'teacher') {
      const courses = (await window.API.get('/api/courses')).courses || [];
      if (courses.length === 0) {
        note.textContent = '这个账号名下还没有课程。';
        return;
      }
      window.location.replace(`/teacher/${encodeURIComponent(courses[0].code)}`);
      return;
    }
    window.location.replace('/login');
  }

  go().catch(function (failure) {
    if (failure.status === 401) {
      window.location.replace('/login?next=/');
      return;
    }
    note.textContent = '进不去，稍后再试。';
  });
})();
