/* 会话 Cookie 只发送到 /api，教职工入口在浏览器按角色分流。 */
(function () {
  'use strict';

  const title = document.getElementById('entryTitle');
  const note = document.getElementById('entryNote');
  const retry = document.getElementById('entryRetry');
  const logout = document.getElementById('entryLogout');
  const passwordLink = document.getElementById('entryPassword');
  const csrf = document.querySelector('meta[name="csrf-token"]');
  let busy = false;

  async function go() {
    if (busy) return;
    busy = true;
    retry.hidden = true;
    retry.disabled = true;
    logout.disabled = true;
    title.textContent = '正在进入工作区';
    note.textContent = '正在确认账号信息，请稍候。';
    try {
      const session = await window.API.get('/api/auth/me');
      csrf.content = session.csrf_token || '';
      logout.hidden = false;
      passwordLink.hidden = false;
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
        const result = await window.API.get('/api/courses');
        if (!result || !Array.isArray(result.courses)) throw new Error('课程信息格式有误');
        if (result.courses.length === 0) {
          title.textContent = '还没有分配课程';
          note.textContent = '请联系管理员分配课程，完成后可重新检查。';
          retry.hidden = false;
          return;
        }
        window.location.replace(`/teacher/${encodeURIComponent(result.courses[0].course_id)}`);
        return;
      }
      window.location.replace('/login');
    } catch (failure) {
      if (failure.status === 401) {
        window.location.replace('/login?next=/workspace');
        return;
      }
      title.textContent = '暂时无法进入工作区';
      note.textContent = '账号或课程信息暂时取不到，请重试。';
      retry.hidden = false;
    } finally {
      busy = false;
      retry.disabled = false;
      logout.disabled = false;
    }
  }

  retry.addEventListener('click', go);
  logout.addEventListener('click', async () => {
    if (busy) return;
    busy = true;
    retry.disabled = true;
    logout.disabled = true;
    try {
      await window.API.post('/api/auth/logout');
      window.location.replace('/login');
    } catch (failure) {
      if (failure.status === 401) {
        window.location.replace('/login');
      } else {
        note.textContent = '退出失败，请检查网络后重试。';
      }
    } finally {
      busy = false;
      retry.disabled = false;
      logout.disabled = false;
    }
  });
  go();
})();
