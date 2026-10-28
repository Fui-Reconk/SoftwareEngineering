/* 侧栏壳的公共行为：登录守卫、课程列表、账号与退出、手机抽屉。
   六页里带壳的几页都靠它，页面自己的 JS 只管正文数据。 */
(function () {
  'use strict';

  const sidebar = document.getElementById('sidebar');
  const backdrop = document.getElementById('backdrop');
  const toggle = document.getElementById('menuToggle');
  const courseList = document.getElementById('courseList');
  const courseSection = document.getElementById('courseSection');
  const staffNav = document.getElementById('staffNav');
  const accountBox = document.getElementById('accountBox');
  const currentCode = document.querySelector('[data-course]')?.dataset.course || '';

  function setMenu(open) {
    if (!sidebar || !toggle) return;
    sidebar.classList.toggle('open', open);
    backdrop.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? '收起工作区导航' : '展开工作区导航');
  }

  if (toggle) {
    toggle.addEventListener('click', () => setMenu(!sidebar.classList.contains('open')));
    backdrop.addEventListener('click', () => setMenu(false));
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && sidebar.classList.contains('open')) setMenu(false);
    });
    window.addEventListener('resize', () => {
      if (window.innerWidth > 860) setMenu(false);
    });
  }

  function toLogin() {
    const here = window.location.pathname + window.location.search;
    window.location.replace(`/login?next=${encodeURIComponent(here)}`);
  }

  function renderCourses(courses) {
    courseList.textContent = '';
    if (courses.length === 0) {
      courseList.textContent = '还没有分配课程。';
      return;
    }
    courses.forEach((course) => {
      const item = document.createElement('a');
      item.className = 'course';
      item.href = `/teacher/${encodeURIComponent(course.course_id)}`;
      if (course.course_id === currentCode) item.setAttribute('aria-current', 'page');
      const title = document.createElement('span');
      title.className = 'course-title';
      title.textContent = course.name;
      const meta = document.createElement('span');
      meta.className = 'course-meta';
      meta.textContent = course.course_id;
      item.append(title, meta);
      courseList.appendChild(item);
    });
    courseList.addEventListener('click', () => setMenu(false), { once: true });
  }

  function renderNavigation(role) {
    const destinations = role === 'admin'
      ? [['账号管理', '/admin/accounts'], ['课程管理', '/admin/courses'], ['隐私参数', '/admin/config'], ['查询留痕', '/admin/audit']]
      : role === 'auditor' ? [['查询留痕', '/admin/audit']]
        : role === 'teacher' ? [['导出快照', '/teacher/exports/history']] : [];
    staffNav.textContent = '';
    destinations.forEach(([label, href]) => {
      const item = document.createElement('a');
      item.className = 'course';
      item.textContent = label;
      item.href = href;
      if (window.location.pathname === href) item.setAttribute('aria-current', 'page');
      staffNav.appendChild(item);
    });
    staffNav.hidden = destinations.length === 0;
    courseSection.hidden = role !== 'teacher';
    staffNav.addEventListener('click', () => setMenu(false));
  }

  function renderAccount(account) {
    accountBox.textContent = '';
    const name = document.createElement('span');
    name.className = 'who-name';
    name.textContent = account.username;
    const meta = document.createElement('span');
    meta.className = 'who-meta';
    meta.textContent = { teacher: '教师', admin: '管理员', auditor: '审计员' }[account.role] || account.role;
    accountBox.append(name, meta);
  }

  const signOut = document.getElementById('signOut');
  if (signOut) {
    signOut.addEventListener('click', async () => {
      try {
        await window.API.post('/api/auth/logout');
      } catch (ignored) {
        // 退出失败也要把人送回登录页，否则他会卡在一个已失效的壳里。
      }
      window.location.replace('/login');
    });
  }

  async function start() {
    let session;
    try {
      session = await window.API.get('/api/auth/me');
    } catch (failure) {
      if (failure.status === 401) {
        toLogin();
        return;
      }
      throw failure;
    }
    document.querySelector('meta[name="csrf-token"]').content = session.csrf_token || '';
    renderAccount(session.account);
    if (!sidebar) return;
    renderNavigation(session.account.role);
    // 课程结果只属于任课教师；管理员使用管理与配置导航。
    if (session.account.role !== 'teacher') return session;
    try {
      const courses = (await window.API.get('/api/courses')).courses || [];
      renderCourses(courses);
    } catch (failure) {
      courseList.textContent = '课程列表取不到。';
    }
    return session;
  }

  window.SHELL = { ready: start() };
})();
