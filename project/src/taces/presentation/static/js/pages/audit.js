/* 查询留痕：只读表格。时间、操作者、动作名都由接口翻译好，这里只填格。
   课程下拉的选项也来自这个接口，因为审计员拿不到 /api/courses。 */
(function () {
  'use strict';

  const rows = document.getElementById('auditRows');
  const empty = document.getElementById('auditEmpty');
  const loadMore = document.getElementById('loadMore');
  const courseFilter = document.getElementById('courseFilter');
  const LIMIT = 50;
  let offset = 0;
  let loading = false;

  function render(entries) {
    entries.forEach((entry) => {
      const tr = document.createElement('tr');
      const cells = [
        { text: entry.at.replace('T', ' ').slice(0, 16) },
        { text: entry.actor },
        { text: entry.action },
        { text: entry.target || '—' },
        { text: entry.epsCost ? String(entry.epsCost) : '0', className: 'n num' },
      ];
      cells.forEach((cell) => {
        const td = document.createElement('td');
        if (cell.className) td.className = cell.className;
        td.textContent = cell.text;
        tr.appendChild(td);
      });
      rows.appendChild(tr);
    });
  }

  function fillCourses(courses) {
    if (!courses || courseFilter.options.length > 0) return;
    const all = document.createElement('option');
    all.value = '';
    all.textContent = '全部';
    courseFilter.appendChild(all);
    courses.forEach((course) => {
      const option = document.createElement('option');
      option.value = course.code;
      option.textContent = course.title;
      courseFilter.appendChild(option);
    });
  }

  async function load(reset) {
    if (loading) return;
    loading = true;
    if (reset) {
      offset = 0;
      rows.textContent = '';
    }
    const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
    if (courseFilter.value) params.set('course', courseFilter.value);
    try {
      const page = await window.API.get(`/api/admin/audit?${params.toString()}`);
      fillCourses(page.courses);
      render(page.entries || []);
      offset += (page.entries || []).length;
      loadMore.hidden = !page.next;
      empty.hidden = offset > 0;
    } catch (failure) {
      empty.textContent = failure.status === 403
        ? '这个账号没有看审计日志的权限。'
        : '留痕取不到，刷新再试。';
      empty.hidden = false;
    } finally {
      loading = false;
    }
  }

  loadMore.addEventListener('click', () => load(false));
  courseFilter.addEventListener('change', () => load(true));
  load(true);
})();
