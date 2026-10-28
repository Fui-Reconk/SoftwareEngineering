/* 直接读取已发布快照，不请求统计发布接口。 */
(function () {
  'use strict';
  const el = id => document.getElementById(id);
  const form = el('exportForm');
  const course = el('exportCourse');
  const publication = el('exportPublication');
  const error = el('exportPageError');
  const retry = el('exportRetry');
  const pdf = el('exportLatestPdf');
  const csv = el('exportLatestCsv');
  let exporting = false;

  function showError(message) {
    error.textContent = message;
    error.hidden = false;
  }
  function redirectIfExpired(failure) {
    if (failure.status !== 401) return false;
    window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    return true;
  }
  async function loadCourses() {
    form.hidden = true;
    retry.hidden = true;
    error.hidden = true;
    try {
      const result = await window.API.get('/api/courses');
      const courses = result.courses || [];
      if (!courses.length) {
        showError('目前没有分配课程，暂时无法导出。');
        retry.hidden = false;
        return;
      }
      course.textContent = '';
      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = '请选择课程';
      course.appendChild(placeholder);
      courses.forEach(item => {
        const option = document.createElement('option');
        option.value = item.course_id;
        option.textContent = `${item.name} · ${item.course_id}`;
        course.appendChild(option);
      });
      form.hidden = false;
    } catch (failure) {
      if (!redirectIfExpired(failure)) {
        showError(failure.message || '课程列表暂时取不到，请重试。');
        retry.hidden = false;
      }
    }
  }
  async function download(format) {
    if (exporting) return;
    error.hidden = true;
    const target = publication.value.trim().toLowerCase();
    if (!course.value) {
      showError('请先选择课程。');
      return;
    }
    if (target && !/^[a-f0-9]{32}$/.test(target)) {
      showError('请输入 32 位十六进制发布编号。');
      return;
    }
    exporting = true;
    pdf.disabled = csv.disabled = true;
    try {
      const params = new URLSearchParams({ format });
      if (target) params.set('publication', target);
      const file = await window.API.downloadWithMetadata(`/api/courses/${encodeURIComponent(course.value)}/export?${params}`);
      const url = window.URL.createObjectURL(file.blob);
      try {
        const link = document.createElement('a');
        link.href = url;
        link.download = file.filename && file.filename.toLowerCase().endsWith(`.${format}`)
          ? file.filename : `statistics-${target || 'latest'}.${format}`;
        document.body.appendChild(link);
        link.click();
        link.remove();
      } finally {
        window.setTimeout(() => window.URL.revokeObjectURL(url), 1000);
      }
    } catch (failure) {
      if (!redirectIfExpired(failure)) showError(failure.message || '导出失败，请稍后重试。');
    } finally {
      exporting = false;
      pdf.disabled = csv.disabled = false;
    }
  }
  pdf.addEventListener('click', () => download('pdf'));
  csv.addEventListener('click', () => download('csv'));
  retry.addEventListener('click', loadCourses);
  window.SHELL.ready.then(session => {
    if (!session) return;
    if (session.account.role !== 'teacher') {
      showError('只有任课教师可以导出课程快照。');
      return;
    }
    return loadCourses();
  }).catch(() => showError('账号信息暂时取不到，请刷新后重试。'));
})();
