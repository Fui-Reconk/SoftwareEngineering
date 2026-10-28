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
  const teacher = byId('courseTeacher');
  const teacherHint = byId('courseTeacherHint');
  const teacherLink = byId('courseTeacherLink');
  const defaultHint = byId('courseDefaultHint');
  const formError = byId('courseFormError');
  const saved = byId('courseSaved');
  const save = byId('courseSave');
  const cancel = byId('courseCancel');
  const PAGE_SIZE = 100;
  let session;
  let accounts = [];
  let selected = null;
  let rowButtons = [];
  let loading = false;
  let saving = false;
  let loaded = false;

  function updateControls() {
    const busy = loading || saving;
    create.disabled = busy || !loaded;
    fields.disabled = busy;
    close.disabled = busy;
    retry.disabled = busy;
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
    termCell.textContent = course.term;
    teacherCell.textContent = teacherLabel(course.teacher_id);
    edit.type = 'button';
    edit.className = 'btn';
    edit.textContent = '编辑';
    edit.setAttribute('aria-label', `编辑课程 ${course.name}`);
    edit.addEventListener('click', () => openForm(course));
    actions.appendChild(edit);
    row.append(courseCell, termCell, teacherCell, actions);
    rows.appendChild(row);
    rowButtons.push(edit);
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
        window.API.get('/api/courses'), fetchAccounts(),
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
    if (selected) {
      const changes = {};
      if (name.value.trim() !== selected.name) changes.name = name.value.trim();
      if (term.value.trim() !== selected.term) changes.term = term.value.trim();
      if (teacher.value !== selected.teacher_id) changes.teacher_id = teacher.value;
      if (Object.keys(changes).length === 0) {
        formError.textContent = '没有需要保存的更改。';
        formError.hidden = false;
        return;
      }
      request = () => window.API.patch(`/api/admin/courses/${encodeURIComponent(selected.course_id)}`, changes);
    } else {
      const payload = { course_id: courseId.value.trim(), name: name.value.trim(),
        term: term.value.trim(), teacher_id: teacher.value };
      request = () => window.API.post('/api/admin/courses', payload);
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
