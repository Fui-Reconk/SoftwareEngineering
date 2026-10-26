# 前端六页实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: 用 superpowers:executing-plans 逐任务执行。步骤用 `- [ ]` 跟踪。

**Goal:** 把 `presentation/` 从空的模板目录做成六页可交的前端，数字经一层适配代码取，接口到位后只改那一层。

**Architecture:** Flask 渲染页面骨架（标题、区块标题、固定文案），JS 只把数据填进 `data-slot` 槽位。取数统一走 `static/js/api.js`，一个 `USE_MOCK` 常量在假数据与 `fetch` 之间切换。文案在模板里，所以 pytest 能断言页面内容，关掉 JS 也还有骨架。

**Tech Stack:** Python 3.12 + Flask 3.1（`project/.venv` 已有）、Jinja2、原生 HTML/CSS/JS，前端零依赖。

**Spec:** `project/docs/FRONTEND.md`（13 条判断在 §4，六页定义在 §5）

## Global Constraints

- 不引入前端框架、构建工具、CSS 框架、图标库、外部字体。
- 所有路径相对，源码与文档不出现本机绝对路径。
- 视觉 token 只有一份：`static/css/app.css` 的 `:root`（松绿：纸 `#edf1ee`、数据 `#1f6b4e`）。
- 页面文案中文，句式与 `project/demo/` 一致。
- 每页 `lint.mjs --app` 0 FAIL / 0 WARN。
- 关键页（教师看板、学生评分）另过 `inspect.mjs` 1440/768/390 三宽度 0 FAIL / 0 WARN。
- 不改 `business/`、`data/`，不改 SRS 与正稿。
- 测试命令一律在 `project/` 下执行：`.venv/Scripts/python.exe -m pytest tests/pages/test_pages.py -q`

## Review Focus

1. **浏览器访问不存在的路径** → 应是 HTML 错误页；`/api` 前缀仍是 JSON。Owner: Task 1（改掉一条已通过的集成测试）。
2. **未登录直接打开 `/teacher/…`** → 应回登录并记住原地址。Owner: Task 4（`board.js` 里的 guard），Task 10 手工核对。
3. **统计接口失败或超时** → 出问题的那个块内一句话加重试，不做整屏横幅。Owner: Task 4、Task 7，Task 10 手工核对。
4. **手机上六页不出横向滚动** → Owner: Task 4、Task 7 的 inspector，Task 10 统一补其余四页。
5. **关掉 JS 每页仍有标题与区块标题** → 因为文案在模板里，每个页面任务的 pytest 片段断言就是这一项。

## 文件总览

| 文件 | 谁建 | 职责 |
| --- | --- | --- |
| `presentation/app.py` | T1 改 | 挂 static/template，注册 pages 蓝图 |
| `presentation/errors.py` | T1 改 | `/api` 走 JSON，其余走 HTML |
| `presentation/templates/error.html` | T1 | 错误页 |
| `presentation/templates/base.html` | T2 | 两种壳共用骨架 |
| `presentation/templates/{auth,teacher,student,admin}/*.html` | T2、T4、T6–T9 | 六页 |
| `presentation/static/css/app.css` | T2 | 唯一一份 token 与组件 |
| `presentation/static/js/api.js` | T2 | 唯一取数出口 |
| `presentation/static/js/mock.js` | T2 起各任务加条目 | 按契约写死的假数据 |
| `presentation/static/js/pages/*.js` | T4、T6–T9 | 每页填数 |
| `tests/pages/test_pages.py` | T1 起各任务加行 | 页面断言 |

---

### Task 1: 静态与模板挂载、浏览器错误页

**Files:**
- Modify: `project/src/taces/presentation/app.py:17,26-27`
- Modify: `project/src/taces/presentation/errors.py`
- Create: `project/src/taces/presentation/templates/error.html`
- Modify: `project/tests/integration/test_http.py:32-35`（把「未知路径返回 JSON」改成「未知页面返回 HTML」）
- Create: `project/tests/pages/test_pages.py`、`project/tests/pages/__init__.py`

**Interfaces:**
- Produces: `error.html`，变量 `code` 与 `message`；`/api` 前缀继续返回 `{error: {code, message}}`。

- [ ] **Step 1: 写失败的测试**

```python
# project/tests/pages/test_pages.py
def test_unknown_page_returns_html_for_browser(app):
    response = app.test_client().get("/not-a-route")
    assert response.status_code == 404
    assert response.mimetype == "text/html"
    assert "没有这个页面" in response.get_data(as_text=True)


def test_unknown_api_route_still_returns_json(app):
    response = app.test_client().get("/api/not-a-route")
    assert response.status_code == 404
    assert response.mimetype == "application/json"
    assert response.json["error"]["code"] == "NOT_FOUND"
```

同时把 `tests/integration/test_http.py` 里的 `test_missing_route_returns_json` 整条删掉（它被上面第二条取代）。

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/pages/test_pages.py -q`
Expected: `test_unknown_page_returns_html_for_browser` 失败（拿到 `application/json`）

- [ ] **Step 3: 实现**

`app.py` 的 `Flask(...)` 改成 `static_folder="static", template_folder="templates"`。
`errors.py` 在返回前判 `request.path.startswith("/api")`：是则走原 JSON 分支，否则 `render_template("error.html", code=…, message=…)`。
`error.html` 用最小结构，不依赖 `base.html`（T2 才建）。404 文案「没有这个页面」，其余用原 `message`。

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/pages/test_pages.py tests/integration/test_http.py -q`
Expected: 全 passed

- [ ] **Step 5: 提交**

```bash
git add project/src/taces/presentation project/tests
git commit -m "feat(presentation): 浏览器错误页与静态模板挂载"
```

---

### Task 2: 共享骨架与登录页

**Files:**
- Create: `presentation/routes/pages.py`、`presentation/templates/base.html`、`presentation/templates/auth/login.html`
- Create: `presentation/static/css/app.css`、`presentation/static/js/api.js`、`presentation/static/js/mock.js`
- Modify: `app.py`（注册 `pages` 蓝图）
- Modify: `tests/pages/test_pages.py`

**Interfaces:**
- Produces: 蓝图 `taces.presentation.routes.pages.pages`（无 url_prefix）；路由 `/login`；
  `base.html` 的块 `title`、`content`、`scripts`，以及变量 `shell`（`"plain"` 或 `"staff"`）；
  `window.API.USE_MOCK`、`window.API.get(path)`、`window.API.post(path, body)`；
  `window.MOCK` 以接口路径为键。

- [ ] **Step 1: 写失败的测试**

```python
def test_login_page_is_html_with_its_copy(app):
    body = app.test_client().get("/login").get_data(as_text=True)
    assert "<h1" in body
    assert "TACES" in body
    assert "学生不用登录" in body
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/pages/test_pages.py::test_login_page_is_html_with_its_copy -q`
Expected: 404

- [ ] **Step 3: 实现**

`app.css` 从 `project/demo/assets/app.css` 迁过来，去掉 demo 专用节，留 token、壳、控件、表单。
`base.html` 按 `shell` 变量分两套：`plain` 只出产品名顶栏，`staff` 出侧栏加顶栏。
`login.html` 用 `plain` 壳，区块照 `FRONTEND.md` §5.1。
`api.js` 与 `mock.js` 先只有形状：`USE_MOCK = true`，`mock.js` 里放 `/api/auth/login` 与 `/api/auth/me`。
登录成功后跳 `/`（T3 建）。

- [ ] **Step 4: 跑测试并过视觉闸门**

Run: `.venv/Scripts/python.exe -m pytest tests/pages/test_pages.py -q`
Expected: passed
Run: `node .agents/skills/design-taste-frontend/scripts/lint.mjs --app project/src/taces/presentation`
Expected: 0 FAIL / 0 WARN

- [ ] **Step 5: 提交**

```bash
git add project/src/taces/presentation project/tests
git commit -m "feat(presentation): 共享骨架与登录页"
```

---

### Task 3: 按角色中转的入口页

**Files:** Create `templates/entry.html`、`static/js/pages/entry.js`；Modify `routes/pages.py`、`mock.js`、`tests/pages/test_pages.py`

**Interfaces:**
- Consumes: Task 2 的 `API.get`。
- Produces: 路由 `/`。

- [ ] **Step 1: 写失败的测试**

```python
def test_entry_page_renders(app):
    body = app.test_client().get("/").get_data(as_text=True)
    assert "正在进入" in body
```

- [ ] **Step 2: 跑测试确认失败**（404）
- [ ] **Step 3: 实现**

页面本身不做服务端判权（会话 Cookie 作用域是 `/api`，页面路由读不到）。`entry.js` 调
`API.get("/api/auth/me")`，按 `account.role` 跳：`teacher` → 其第一门课的 `/teacher/<code>`，
`admin` → `/admin/config`，`auditor` → `/admin/audit`；401 则跳 `/login?next=/`。

- [ ] **Step 4: 跑测试确认通过**
- [ ] **Step 5: 提交** `feat(presentation): 按角色中转的入口页`

---

### Task 4: 教师结果看板

**Files:**
- Create: `templates/teacher/board.html`、`static/js/pages/board.js`
- Modify: `static/css/app.css`（看板各块）、`mock.js`（统计接口）、`routes/pages.py`、`tests/pages/test_pages.py`

**Interfaces:**
- Consumes: `API.get`、`base.html` 的 `staff` 壳。
- Produces: 路由 `/teacher/<course_id>`；`MOCK["/api/courses/<id>/statistics"]` 形状
  `{ state, courseCode, courseTitle, term, responses, enrolled, publishedAt,
     pooledMean, interval, spread, distinguishable,
     dimensions: [{name, value}], distribution: [{score, count}],
     openText: { responses, terms: [{word, count}] } }`

- [ ] **Step 1: 写失败的测试**

```python
def test_board_renders_its_blocks(app):
    body = app.test_client().get("/teacher/SE201-03").get_data(as_text=True)
    assert "评分分布" in body
    assert "开放题高频词" in body
    assert "评教窗口" in body
```

- [ ] **Step 2: 跑测试确认失败**（404）
- [ ] **Step 3: 实现**

模板出标题行、主卡两栏的空槽、词频块、页脚；`board.js` 取数后按 `data-slot` 填。
数值沿用 demo：235 份、705 条、3.86、±0.39、三维度 4.02/3.84/3.72、分布 15/52/139/310/189。
区间与 `distinguishable` 从响应读，不在前端重算。`state === "unpublished"` 时换成拒绝态。
页面加载先调 `/api/auth/me`，401 跳 `/login?next=` 当前路径。

- [ ] **Step 4: 跑测试、过闸门**

Run: `.venv/Scripts/python.exe -m pytest tests/pages/test_pages.py -q` → passed
Run: `node .agents/skills/design-taste-frontend/scripts/lint.mjs --app project/src/taces/presentation` → 0/0
Run: 起服务后 `inspect.mjs --app <url>/teacher/SE201-03` → 三宽度 0 FAIL / 0 WARN，截图逐张看

- [ ] **Step 5: 提交** `feat(presentation): 教师结果看板页`

---

### Task 5: 看板空位处理

**Files:** Modify `mock.js`（高频词 12 条）、`templates/teacher/board.html`（承诺句）、`static/css/app.css`（三列）、`tests/pages/test_pages.py`

- [ ] **Step 1: 写失败的测试**

```python
def test_board_states_the_anonymity_promise(app):
    body = app.test_client().get("/teacher/SE201-03").get_data(as_text=True)
    assert "不关联" in body
    assert "原文不出接口" in body
```

- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现**（词频 8→12，三列各四条；承诺句放在词频块说明位，模板里写死）
- [ ] **Step 4: 跑测试、确认仍是一屏、lint 0/0**
- [ ] **Step 5: 提交** `feat(presentation): 看板词频扩到十二项并补匿名承诺`

---

### Task 6: 学生评价码校验页

**Files:** Create `templates/student/code.html`、`static/js/pages/code.js`；Modify `routes/pages.py`、`mock.js`、`tests/pages/test_pages.py`

**Interfaces:**
- Produces: 路由 `/student`；`MOCK["/api/evaluation-codes/verify"]` 形状
  `{ valid, reason?, course: { code, title, teacher, dimensions: [{name}] } }`

- [ ] **Step 1: 写失败的测试**

```python
def test_code_page_renders_and_states_the_three_failures(app):
    body = app.test_client().get("/student").get_data(as_text=True)
    assert "进入评教" in body
    assert "已经用过了" in body and "没有这个码" in body and "窗口已关闭" in body
```

- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现**（三种失败文案写在模板里，JS 只切显示；校验成功后把码与课程信息交给评分页）
- [ ] **Step 4: 跑测试、lint 0/0**
- [ ] **Step 5: 提交** `feat(presentation): 学生评价码校验页`

---

### Task 7: 学生评分页（关键页）

**Files:** Create `templates/student/evaluate.html`、`static/js/pages/evaluate.js`；Modify `routes/pages.py`、`mock.js`、`static/css/app.css`（选项组与文本框）、`tests/pages/test_pages.py`

**Interfaces:**
- Consumes: Task 6 的 verify 响应。
- Produces: 路由 `/student/evaluate`；`MOCK["/api/submissions"]` 写 `{ submissionId }`。

- [ ] **Step 1: 写失败的测试**

```python
def test_evaluate_page_renders_three_dimensions_and_the_receipt(app):
    body = app.test_client().get("/student/evaluate").get_data(as_text=True)
    assert "教学内容" in body and "教学方法" in body and "考核方式" in body
    assert "不能再改" in body
    assert "500" in body
```

- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现**

三个维度各一行五个 radio（`fieldset` + `legend`，键盘可达）；开放题 `textarea` 带 500 字计数；
未选满时提交禁用并写明差哪个；提交成功整页换成回执。无码打开（`sessionStorage` 里没有 verify 结果）回 `/student`。
码随评分一起 POST，不放 URL。

- [ ] **Step 4: 跑测试、过闸门**（本页是关键页，必须跑三宽度 inspector）
- [ ] **Step 5: 提交** `feat(presentation): 学生评分页`

---

### Task 8: 管理员参数页

**Files:** Create `templates/admin/config.html`、`static/js/pages/config.js`；Modify `routes/pages.py`、`mock.js`、`static/css/app.css`（两列 settings 构图）、`tests/pages/test_pages.py`

**Interfaces:**
- Produces: 路由 `/admin/config`；`MOCK["/api/admin/config"]` 形状
  `{ values: { epsilon, k, epsilonTotal }, ranges: { epsilon: {min, max}, … }, units: { epsilon: "ε", … } }`

- [ ] **Step 1: 写失败的测试**

```python
def test_config_page_names_three_parameters_and_their_scope(app):
    body = app.test_client().get("/admin/config").get_data(as_text=True)
    assert "每次发布 ε" in body
    assert "出数门槛 k" in body
    assert "每门课预算总量" in body
```

- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现**（两列 settings 构图；范围与单位从响应读，模板不写死数字；非法值就地报错）
- [ ] **Step 4: 跑测试、lint 0/0**
- [ ] **Step 5: 提交** `feat(presentation): 管理员参数配置页`

---

### Task 9: 审计日志页

**Files:** Create `templates/admin/audit.html`、`static/js/pages/audit.js`；Modify `routes/pages.py`、`mock.js`、`tests/pages/test_pages.py`

**Interfaces:**
- Produces: 路由 `/admin/audit`；`MOCK["/api/admin/audit"]` 形状
  `{ entries: [{ at, actor, action, target, epsCost }], next: null, courses: [{ code, title }] }`

- [ ] **Step 1: 写失败的测试**

```python
def test_audit_page_renders_read_only_table(app):
    body = app.test_client().get("/admin/audit").get_data(as_text=True)
    assert "查询留痕" in body
    assert "操作者" in body and "消耗 ε" in body
    assert "删除" not in body
```

- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现**（筛选、表格、加载更多、空结果一句；管理员与审计员都能进）
- [ ] **Step 4: 跑测试、lint 0/0**
- [ ] **Step 5: 提交** `feat(presentation): 审计日志页`

---

### Task 10: 六页一致性收尾

- [ ] **Step 1**: 六页逐个 `lint.mjs --app`，全绿。
- [ ] **Step 2**: 其余四页补 390 宽度检查，确认无横向滚动。
- [ ] **Step 3**: 手工核对 Review Focus 2 与 3：清 cookie 直接开 `/teacher/SE201-03` 应跳登录；把 `mock.js` 的统计接口改成 reject，确认块内出错误文案与重试。
- [ ] **Step 4**: 把 `api.js` 的 `USE_MOCK` 临时改 `false`，确认六页取数路径全在 `API_CONTRACT.md` 里，改回。
- [ ] **Step 5**: 提交 `chore(presentation): 六页一致性与手机宽度收尾`

---

## 附：本计划不做的事

- 不实现 `API_CONTRACT.md` 里标「待实现」的后端接口。
- 不做导出 PDF / CSV 的实际生成，按钮先禁用并注明接口未实现。
- 不做真正的服务端判权，登录态由页面调 `/api/auth/me` 后自行跳转。
