/* 学生评分：维度名与课程名来自校验结果，五个选项用原生 radio，键盘可达。
   评价码随评分一起 POST，不出现在 URL 里。 */
(function () {
  'use strict';

  const stored = sessionStorage.getItem('taces.verify');
  if (!stored) {
    window.location.replace('/student');
    return;
  }

  let verify;
  try {
    verify = JSON.parse(stored);
  } catch (broken) {
    window.location.replace('/student');
    return;
  }

  const course = verify.course || {};
  const dimensions = (course.dimensions || []).map((item) => item.name);
  const form = document.getElementById('rateForm');
  const rows = document.getElementById('dimensionRows');
  const submit = document.getElementById('submitRating');
  const error = document.getElementById('rateError');
  const openText = document.getElementById('openText');
  const charCount = document.getElementById('charCount');

  document.getElementById('courseTitle').textContent = course.title || '请给这门课打分';
  document.getElementById('courseMeta').textContent =
    [course.code, course.teacher].filter(Boolean).join(' · ');

  const ratings = new Map();
  let submitting = false;

  function refresh() {
    const missing = dimensions.filter((name) => !ratings.has(name));
    submit.disabled = submitting || missing.length > 0;
    submit.textContent = missing.length === 0 ? '提交' : `还差：${missing.join('、')}`;
  }

  dimensions.forEach((name) => {
    const row = document.createElement('div');
    row.className = 'scale-row';
    const legend = document.createElement('span');
    legend.className = 'scale-label';
    legend.textContent = name;

    const group = document.createElement('div');
    group.className = 'scale';
    group.setAttribute('role', 'radiogroup');
    group.setAttribute('aria-label', name);

    for (let score = 1; score <= 5; score += 1) {
      const option = document.createElement('label');
      option.className = 'scale-option';
      const input = document.createElement('input');
      input.type = 'radio';
      input.name = name;
      input.value = String(score);
      input.addEventListener('change', () => {
        ratings.set(name, score);
        refresh();
      });
      const box = document.createElement('span');
      box.textContent = String(score);
      option.append(input, box);
      group.appendChild(option);
    }

    row.append(legend, group);
    rows.appendChild(row);
  });

  openText.addEventListener('input', () => {
    charCount.textContent = String(openText.value.length);
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    error.hidden = true;
    submitting = true;
    submit.disabled = true;
    try {
      await window.API.post('/api/submissions', {
        code: verify.code,
        ratings: dimensions.map((name) => ({ dimension: name, score: ratings.get(name) })),
        openText: openText.value.trim(),
      });
      sessionStorage.removeItem('taces.verify');
      document.querySelector('.card-wide').hidden = true;
      const receipt = document.getElementById('receipt');
      receipt.hidden = false;
      receipt.focus();
      window.setTimeout(() => window.location.assign('/'), 5000);
    } catch (failure) {
      if (failure.status === 409) {
        // 码在提交前被用掉或窗口关了：回上一步，让学生看见原因
        sessionStorage.removeItem('taces.verify');
        sessionStorage.setItem('taces.failure', failure.message || '这个码不能用了。');
        window.location.assign('/student');
        return;
      }
      error.textContent = failure.message || '提交失败，再试一次。';
      error.hidden = false;
      submitting = false;
      submit.disabled = false;
    }
  });

  refresh();
})();
