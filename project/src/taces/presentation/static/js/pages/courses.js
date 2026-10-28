/* 管理员课程列表：沿用账号管理弹窗，写入和权限由现有 API 校验。 */
(function () {
  'use strict';

  const byId = (id) => document.getElementById(id);
  const workspace = byId('courseWorkspace');
  const denied = byId('courseDenied');
  const rows = byId('courseRows');
  const empty = byId('coursesEmpty');
  const loadingNote = byId('coursesLoading');
  const listError = byId('coursesError');
  const retry = byId('coursesRetry');
  const create = byId('courseCreate');
  const dialog = byId('courseDialog');
  const title = byId('courseDialogTitle');
  const close = byId('courseClose');
  const form = byId('courseForm');
  const fields = byId('courseFields');
  const courseId = byId('courseId');
  const name = byId('courseName');
  const term = byId('courseTerm');
  const closesAt = byId('courseClosesAt');
  const useCustom = byId('courseUseCustom');
  const dimensionCreate = byId('courseDimensionCreate');
  const dimensionSummary = byId('courseDimensionSummary');
  const customSection = byId('courseCustomSection');
  const dimensionContainer = byId('courseDimensionRows');
  const addDimensionButton = byId('courseAddDimension');
  const teacher = byId('courseTeacher');
  const teacherHint = byId('courseTeacherHint');
  const teacherLink = byId('courseTeacherLink');
  const defaultHint = byId('courseDefaultHint');
  const formError = byId('courseFormError');
  const saved = byId('courseSaved');
  const save = byId('courseSave');
  const cancel = byId('courseCancel');
  const codeDialog = byId('codeDialog');
  const codeTitle = byId('codeDialogTitle');
  const codeClose = byId('codeClose');
  const codeWindow = byId('codeWindow');
  const codeForm = byId('codeForm');
  const codeFields = byId('codeFields');
  const codeCount = byId('codeCount');
  const codeExpiresAt = byId('codeExpiresAt');
  const codeError = byId('codeError');
  const codeIssue = byId('codeIssue');
  const codeResult = byId('codeResult');
  const codeValues = byId('codeValues');
  const codeCopy = byId('codeCopy');
  const codeDownload = byId('codeDownload');
  const codeSaved = byId('codeSaved');
  const PAGE_SIZE = 100;
  let session;
  let accounts = [];
  let selected = null;
  let rowButtons = [];
  let loading = false;
  let saving = false;
  let issuing = false;
  let loaded = false;
  let initialDeadline = '';
  let dimensionRows = [];
  let codeCourse = null;
  let issuedCodes = [];
  let codesSaved = true;
  let codeWindowClosed = true;

  function updateControls() {
    const busy = loading || saving || issuing;
    create.disabled = busy || !loaded;
    fields.disabled = busy;
    close.disabled = busy;
    retry.disabled = busy;
    codeFields.disabled = busy;
    codeClose.disabled = busy;
    codeIssue.disabled = busy || codeWindowClosed;
    rowButtons.forEach((button) => { button.disabled = busy || !loaded; });
  }

  function loginAgain() {
    window.location.replace('/login?next=%2Fadmin%2Fcourses');
  }

  async function fetchAccounts() {
    const result = [];
    let offset = 0;
    while (true) {
      const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
      const page = await window.API.get(`/api/admin/accounts?${params.toString()}`);
      if (!page || !Array.isArray(page.accounts)) throw new Error('教师账号列表格式有误，请重试。');
      result.push(...page.accounts);
      if (page.accounts.length < PAGE_SIZE) return result;
      offset += page.accounts.length;
    }
  }

  function inputTime(seconds) {
    if (typeof seconds !== 'number' || !Number.isFinite(seconds)) return '';
    const value = new Date(seconds * 1000);
    if (!Number.isFinite(value.getTime())) return '';
    const pad = (number) => String(number).padStart(2, '0');
    return `${String(value.getFullYear()).padStart(4, '0')}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}T${pad(value.getHours())}:${pad(value.getMinutes())}`;
  }

  function localTimestamp(value) {
    if (!value) return null;
    const milliseconds = new Date(value).getTime();
    if (!Number.isFinite(milliseconds) || milliseconds < 0 || milliseconds > 253402300799000) {
      throw new Error('请填写有效的日期和时间。');
    }
    return Math.floor(milliseconds / 1000);
  }

  function deadlineLabel(seconds) {
    const value = inputTime(seconds);
    if (!value) return '未设置评价截止时间';
    return `${seconds <= Date.now() / 1000 ? '已截止' : '截止'} ${value.replace('T', ' ')}`;
  }

  function addDimension(name = '', weight = '1') {
    if (dimensionRows.length >= 10) return;
    const row = document.createElement('div');
    const nameLabel = document.createElement('label');
    const nameText = document.createElement('span');
    const nameInput = document.createElement('input');
    const weightLabel = document.createElement('label');
    const weightText = document.createElement('span');
    const weightInput = document.createElement('input');
    const remove = document.createElement('button');
    row.className = 'course-dimension-row';
    nameLabel.className = weightLabel.className = 'field';
    nameText.className = weightText.className = 'field-label';
    nameText.textContent = '维度名称';
    weightText.textContent = '权重';
    nameInput.className = weightInput.className = 'input';
    nameInput.type = 'text';
    nameInput.required = true;
    nameInput.value = name;
    weightInput.type = 'number';
    weightInput.step = 'any';
    weightInput.min = '0';
    weightInput.max = '1';
    weightInput.required = true;
    weightInput.value = weight;
    nameLabel.append(nameText, nameInput);
    weightLabel.append(weightText, weightInput);
    remove.className = 'btn';
    remove.type = 'button';
    remove.textContent = '移除';
    remove.addEventListener('click', () => {
      dimensionRows = dimensionRows.filter((item) => item.row !== row);
      row.remove();
      addDimensionButton.disabled = false;
    });
    row.append(nameLabel, weightLabel, remove);
    dimensionContainer.appendChild(row);
    dimensionRows.push({ row, name: nameInput, weight: weightInput });
    addDimensionButton.disabled = dimensionRows.length >= 10;
  }

  function customDimensions() {
    const dimensions = dimensionRows.map((item) => ({ name: item.name.value.trim(), weight: Number(item.weight.value) }));
    const valid = dimensions.length >= 1 && dimensions.length <= 10
      && dimensions.every((item) => item.name && [...item.name].length <= 64
        && Number.isFinite(item.weight) && item.weight > 0 && item.weight <= 1)
      && new Set(dimensions.map((item) => item.name)).size === dimensions.length;
    if (!valid || Math.abs(dimensions.reduce((sum, item) => sum + item.weight, 0) - 1) > 1e-9) {
      throw new Error('请填写不重复的维度名称，权重须大于 0 且合计为 1。');
    }
    return dimensions;
  }

  function teacherLabel(teacherId) {
    const account = accounts.find((item) => item.user_id === teacherId);
    if (!account) return `${teacherId}（账号不可用）`;
    if (account.role !== 'teacher') return `${account.username}（非教师账号）`;
    return account.is_active ? account.username : `${account.username}（已停用）`;
  }

  function addRow(course) {
    const row = document.createElement('tr');
    const courseCell = document.createElement('td');
    const courseName = document.createElement('span');
    const identifier = document.createElement('span');
    const termCell = document.createElement('td');
    const teacherCell = document.createElement('td');
    const actions = document.createElement('td');
    const edit = document.createElement('button');
    courseName.className = 'course-name';
    courseName.textContent = course.name;
    identifier.className = 'course-identifier';
    identifier.textContent = course.course_id;
    courseCell.append(courseName, identifier);
    termCell.setAttribute('data-label', '学期');
    teacherCell.setAttribute('data-label', '任课教师');
    termCell.textContent = course.term;
    const deadline = document.createElement('span');
    deadline.className = 'course-identifier';
    deadline.textContent = deadlineLabel(course.closes_at);
    termCell.appendChild(deadline);
    teacherCell.textContent = teacherLabel(course.teacher_id);
    edit.type = 'button';
    edit.className = 'btn';
    edit.textContent = '编辑';
    edit.setAttribute('aria-label', `编辑课程 ${course.name}`);
    edit.addEventListener('click', () => openForm(course));
    const issue = document.createElement('button');
    issue.type = 'button';
    issue.className = 'btn';
    issue.textContent = '发放评价码';
    issue.setAttribute('aria-label', `为课程 ${course.name} 发放评价码`);
    issue.addEventListener('click', () => openCodeForm(course));
    actions.className = 'course-actions';
    actions.append(edit, issue);
    row.append(courseCell, termCell, teacherCell, actions);
    rows.appendChild(row);
    rowButtons.push(edit, issue);
  }

  async function loadData() {
    if (loading) return false;
    loading = true;
    loaded = false;
    listError.hidden = true;
    retry.hidden = true;
    loadingNote.hidden = false;
    updateControls();
    try {
      const [coursePage, accountPage] = await Promise.all([
        window.API.get('/api/admin/courses'), fetchAccounts(),
      ]);
      if (!coursePage || !Array.isArray(coursePage.courses)) throw new Error('课程列表格式有误，请重试。');
      accounts = accountPage;
      rows.textContent = '';
      rowButtons = [];
      coursePage.courses.forEach(addRow);
      empty.hidden = coursePage.courses.length !== 0;
      loaded = true;
      return true;
    } catch (failure) {
      if (failure.status === 401) {
        loginAgain();
        return false;
      }
      listError.textContent = failure.message || '课程或教师列表取不到，请重试。';
      listError.hidden = false;
      retry.hidden = false;
      return false;
    } finally {
      loading = false;
      loadingNote.hidden = true;
      updateControls();
    }
  }

  function activeTeachers() {
    return accounts.filter((account) => account.role === 'teacher' && account.is_active);
  }

  function openForm(course) {
    if (!loaded || loading || saving || !session || session.account.role !== 'admin') return;
    selected = course || null;
    title.textContent = selected ? '编辑课程' : '新建课程';
    courseId.value = selected ? selected.course_id : '';
    courseId.readOnly = Boolean(selected);
    name.value = selected ? selected.name : '';
    term.value = selected ? selected.term : '';
    initialDeadline = selected ? inputTime(selected.closes_at) : '';
    closesAt.value = initialDeadline;
    useCustom.checked = false;
    customSection.hidden = true;
    customSection.disabled = true;
    dimensionRows = [];
    dimensionContainer.textContent = '';
    addDimensionButton.disabled = false;
    dimensionCreate.hidden = Boolean(selected);
    dimensionSummary.hidden = !selected;
    if (selected) {
      const dimensions = Array.isArray(selected.dimensions) ? selected.dimensions : [];
      dimensionSummary.textContent = dimensions.length
        ? `评价维度（创建后不可修改）：${dimensions.map((item) => `${item.name}（约 ${Number((item.weight * 100).toPrecision(4))}%）`).join('、')}`
        : '这门课没有可用的评价维度，请联系管理员检查。';
    }
    const teachers = activeTeachers();
    teacher.textContent = '';
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = '请选择任课教师';
    placeholder.disabled = true;
    teacher.appendChild(placeholder);
    teachers.forEach((account) => {
      const option = document.createElement('option');
      option.value = account.user_id;
      option.textContent = account.username;
      teacher.appendChild(option);
    });
    const assignedIsActive = selected && teachers.some((account) => account.user_id === selected.teacher_id);
    teacher.value = assignedIsActive ? selected.teacher_id : '';
    teacherHint.hidden = true;
    teacherLink.hidden = true;
    if (teachers.length === 0) {
      teacherHint.textContent = '没有可分配的启用教师，请先创建或启用教师账号。';
      teacherHint.hidden = false;
      teacherLink.hidden = false;
    } else if (selected && !assignedIsActive) {
      teacherHint.textContent = '原任教师不可用，请重新选择一位启用的教师。';
      teacherHint.hidden = false;
    }
    defaultHint.hidden = Boolean(selected);
    save.textContent = selected ? '保存修改' : '创建课程';
    formError.hidden = true;
    saved.hidden = true;
    dialog.showModal();
    title.focus();
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!dialog.open || saving || loading || !loaded || !session || session.account.role !== 'admin') return;
    formError.hidden = true;
    if (!activeTeachers().some((account) => account.user_id === teacher.value)) {
      formError.textContent = '请选择一位启用的教师。';
      formError.hidden = false;
      return;
    }
    let request;
    try {
      const deadline = localTimestamp(closesAt.value);
      if (selected) {
        const changes = {};
        if (name.value.trim() !== selected.name) changes.name = name.value.trim();
        if (term.value.trim() !== selected.term) changes.term = term.value.trim();
        if (teacher.value !== selected.teacher_id) changes.teacher_id = teacher.value;
        if (closesAt.value !== initialDeadline) {
          if (deadline === null) throw new Error('请填写截止时间；如需关闭评价，可设置过去的时间。');
          changes.closes_at = deadline;
        }
        if (Object.keys(changes).length === 0) throw new Error('没有需要保存的更改。');
        request = () => window.API.patch(`/api/admin/courses/${encodeURIComponent(selected.course_id)}`, changes);
      } else {
        const payload = { course_id: courseId.value.trim(), name: name.value.trim(),
          term: term.value.trim(), teacher_id: teacher.value };
        if (deadline !== null) payload.closes_at = deadline;
        if (useCustom.checked) payload.dimensions = customDimensions();
        request = () => window.API.post('/api/admin/courses', payload);
      }
    } catch (failure) {
      formError.textContent = failure.message;
      formError.hidden = false;
      return;
    }
    saving = true;
    updateControls();
    let focusAfterSave = false;
    try {
      await request();
      const message = selected ? '课程已更新。' : '课程已创建。';
      dialog.close();
      saved.textContent = message;
      saved.hidden = false;
      await loadData();
      focusAfterSave = true;
    } catch (failure) {
      if (failure.status === 401) {
        loginAgain();
        return;
      }
      formError.textContent = failure.message || '保存失败，请重试。';
      formError.hidden = false;
    } finally {
      saving = false;
      updateControls();
      if (focusAfterSave) (loaded ? create : retry).focus();
    }
  });

  useCustom.addEventListener('change', () => {
    customSection.hidden = !useCustom.checked;
    customSection.disabled = !useCustom.checked;
    if (useCustom.checked && dimensionRows.length === 0) addDimension();
  });
  addDimensionButton.addEventListener('click', () => addDimension('', ''));

  function openCodeForm(course) {
    if (!loaded || loading || saving || issuing || !session || session.account.role !== 'admin') return;
    codeCourse = course;
    issuedCodes = [];
    codesSaved = true;
    codeWindowClosed = typeof course.closes_at !== 'number' || course.closes_at <= Date.now() / 1000;
    codeTitle.textContent = `发放评价码 · ${course.name}`;
    codeWindow.textContent = codeWindowClosed
      ? `${deadlineLabel(course.closes_at)}，请先在课程编辑中调整截止时间。`
      : `${deadlineLabel(course.closes_at)}（本机时间）`;
    codeCount.value = '1';
    codeExpiresAt.value = '';
    codeError.hidden = true;
    codeSaved.hidden = true;
    codeForm.hidden = false;
    codeResult.hidden = true;
    codeValues.value = '';
    updateControls();
    codeDialog.showModal();
    codeTitle.focus();
  }

  codeForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!codeDialog.open || !codeCourse || issuing || codeWindowClosed) return;
    codeError.hidden = true;
    let payload;
    try {
      const count = Number(codeCount.value);
      if (!codeCount.value || !Number.isInteger(count) || count < 1 || count > 1000) {
        throw new Error('发放数量须为 1–1000 的整数。');
      }
      payload = { count };
      const expiry = localTimestamp(codeExpiresAt.value);
      if (expiry !== null) {
        if (expiry <= Date.now() / 1000 || expiry > codeCourse.closes_at) {
          throw new Error('评价码有效期须晚于现在，且不能超过课程截止时间。');
        }
        payload.expires_at = expiry;
      }
    } catch (failure) {
      codeError.textContent = failure.message;
      codeError.hidden = false;
      return;
    }
    issuing = true;
    updateControls();
    try {
      const response = await window.API.post(`/api/admin/courses/${encodeURIComponent(codeCourse.course_id)}/evaluation-codes`, payload);
      if (!response || !Array.isArray(response.codes) || response.codes.length !== payload.count
          || !response.codes.every((value) => typeof value === 'string' && /^[a-f0-9]{32}$/i.test(value))) {
        throw { status: 0 };
      }
      issuedCodes = response.codes;
      codesSaved = false;
      codeValues.value = issuedCodes.join('\n');
      codeForm.hidden = true;
      codeResult.hidden = false;
      codeValues.focus();
    } catch (failure) {
      if (failure.status === 401) {
        loginAgain();
      } else {
        codeError.textContent = failure.status === 0
          ? '发放结果无法确认；若服务器已处理，这批评价码无法再次显示。再次发放将生成新码。'
          : failure.message || '发放失败，请稍后重试。';
        codeError.hidden = false;
      }
    } finally {
      issuing = false;
      updateControls();
    }
  });

  function mayCloseCodes() {
    return !issuing && (issuedCodes.length === 0 || codesSaved
      || window.confirm('评价码只显示这一次，尚未复制或下载。确定关闭吗？'));
  }
  codeClose.addEventListener('click', () => { if (mayCloseCodes()) codeDialog.close(); });
  codeDialog.addEventListener('cancel', (event) => { if (!mayCloseCodes()) event.preventDefault(); });
  codeDialog.addEventListener('close', () => {
    issuedCodes = [];
    codesSaved = true;
    codeValues.value = '';
    codeCourse = null;
  });
  window.addEventListener('beforeunload', (event) => {
    if (issuing || (issuedCodes.length && !codesSaved)) {
      event.preventDefault();
      event.returnValue = '';
    }
  });
  codeCopy.addEventListener('click', async () => {
    if (!issuedCodes.length) return;
    try {
      await window.navigator.clipboard.writeText(codeValues.value);
      codesSaved = true;
      codeSaved.textContent = '已复制，请粘贴到安全位置保存。';
    } catch (failure) {
      codeSaved.textContent = '无法自动复制，请手动选中上方评价码复制。';
    }
    codeSaved.hidden = false;
  });
  codeDownload.addEventListener('click', () => {
    if (!issuedCodes.length) return;
    const blob = new Blob([`${codeValues.value}\n`], { type: 'text/plain;charset=utf-8' });
    const url = window.URL.createObjectURL(blob);
    try {
      const link = document.createElement('a');
      link.href = url;
      link.download = `evaluation-codes-${codeCourse.course_id}.txt`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      codesSaved = true;
      codeSaved.textContent = '已开始下载，请确认文件已保存。';
      codeSaved.hidden = false;
    } finally {
      window.setTimeout(() => window.URL.revokeObjectURL(url), 1000);
    }
  });

  create.addEventListener('click', () => openForm(null));
  const dismissDialog = () => { if (!saving) dialog.close(); };
  cancel.addEventListener('click', dismissDialog);
  close.addEventListener('click', dismissDialog);
  dialog.addEventListener('cancel', (event) => { if (saving) event.preventDefault(); });
  retry.addEventListener('click', loadData);

  window.SHELL.ready.then((result) => {
    if (!result) return;
    session = result;
    if (session.account.role !== 'admin') {
      workspace.hidden = true;
      denied.hidden = false;
      return;
    }
    workspace.hidden = false;
    denied.hidden = true;
    return loadData();
  }).catch(() => {
    denied.textContent = '账号信息取不到，请刷新后重试。';
    denied.hidden = false;
  });
})();
