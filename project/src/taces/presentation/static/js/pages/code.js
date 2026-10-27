/* 评价码校验：三种失败各用模板里的一句原话，不在这里另写。
   校验通过后把码与课程信息暂存到 sessionStorage，评分页提交时一起 POST，
   不进 URL（会进浏览器历史和访问日志）。 */
(function () {
  'use strict';

  const form = document.getElementById('codeForm');
  if (!form) return;
  const input = document.getElementById('codeInput');
  const error = document.getElementById('codeError');
  const submit = form.querySelector('button[type="submit"]');

  function showError(kind, fallback) {
    error.textContent = error.dataset[kind] || fallback || '校验失败，再试一次。';
    error.hidden = false;
    submit.disabled = false;
  }

  // 评分页把我们送回来时会留一句原因（码被用掉、窗口关了）
  const carried = sessionStorage.getItem('taces.failure');
  if (carried) {
    sessionStorage.removeItem('taces.failure');
    error.textContent = carried;
    error.hidden = false;
  }

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    error.hidden = true;
    const code = input.value.trim();
    if (!code) {
      showError('empty');
      return;
    }
    submit.disabled = true;
    try {
      const result = await window.API.post('/api/evaluation-codes/verify', { code: code });
      if (!result.valid) {
        showError(result.reason);
        return;
      }
      sessionStorage.setItem('taces.verify', JSON.stringify({
        code: code,
        course: result.course,
      }));
      window.location.assign('/student/evaluate');
    } catch (failure) {
      showError(null, failure.message);
    }
  });
})();
