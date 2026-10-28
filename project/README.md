# TACES 可信匿名评教系统

学生凭一次性评价码提交匿名评分和选填评语；教师查看课程统计；管理员管理账号、课程和隐私参数；审计员只读查询留痕。

当前已实现课程与发码、匿名提交、差分隐私统计发布、预算与发布缓存、配置、审计及 CSV/PDF 导出。各功能页面和入口页已由 Flask 提供。**页面默认连接真实后端，可使用数据生成器创建的演示账号登录。**

## 安装与启动

以下命令均以 `project/` 为当前目录。需要 Python 3.12+ 和下列依赖；本项目为应用，通过 `run.py` 启动，不作为 Python 包安装。使用已配置好的 Python 环境即可，不要求特定的环境管理工具。若系统使用 `python3` 命令，请将下文的 `python` 替换为 `python3`。

`pyproject.toml` 声明 Python 版本与直接依赖，`requirements.txt` 提供兼容的安装清单。例如，可以在已选好的环境中执行 `python -m pip install -r requirements.txt`；若依赖已配置好，可直接运行。

| 环境或依赖 | 要求/用途 |
| --- | --- |
| Python | 3.12+ |
| Flask、Werkzeug | Web路由、模板、密码散列 |
| tzdata | >=2026.5，提供Windows的上海时区数据 |
| reportlab、pypdf | >=5.1.0 / >=6.21.2，生成PDF及校验导出内容 |
| pytest、pytest-cov | Python测试与覆盖率 |
| Node.js | 仅运行JS回归测试需要，应用启动不需要 |

`pyproject.toml` 与 `requirements.txt` 是安装工具读取的声明，会随源码保留；虚拟环境、缓存与本机依赖锁文件不提交。

选择下面一种数据准备方式。

### 本机合成演示

先停止运行中的演示服务，再执行：

```bash
python scripts/generate_test_data.py --check --install-demo
python run.py
```

生成器默认提供 25 门课、包含 1 万份性能样本的合成评价、演示账号和评价码，校验通过后安装到 `db/`，已有三库先备份。默认输出目录为 `tests/experiments/output/testdata/`，必须不存在；再次生成请指定新的 `--output`，例如 `--output tests/experiments/output/demo-2`。

账号、评价码、覆盖范围、备份与恢复方式见 [scripts/README.md](scripts/README.md)。学生演示码在生成清单的 `codes.student_demo`，有效窗口为生成后 30 天。数据校验在临时副本执行，不消耗演示库中的码或预算。

### 空库开始

```bash
python -m flask --app run.py init-db
python -m flask --app run.py create-admin --username admin
python run.py
```

管理员密码通过终端隐藏输入。空库没有默认账号；管理员可在工作区创建员工账号、创建课程、分配教师并发放评价码。应用启动不会隐式建库或发码。已有 v1/v2 库须先停服务并备份三个文件，再执行 `upgrade-db`，不要用删库代替升级；当前结构版本为 v3。

默认监听 [http://127.0.0.1:5000](http://127.0.0.1:5000)。`/api/health` 检查进程，`/api/ready` 检查三库是否就绪。

## 页面与真实接口

| 页面 | 路径 |
| --- | --- |
| 员工登录 | `/login` |
| 学生验码与评分 | `/`、`/student`、`/student/evaluate` |
| 员工工作区分流 | `/workspace` |
| 员工修改本人密码 | `/account/password` |
| 教师看板 | `/teacher/<course_id>` |
| 教师快照导出 | `/teacher/exports/history` |
| 管理员账号管理 | `/admin/accounts` |
| 管理员课程管理 | `/admin/courses` |
| 管理员隐私配置 | `/admin/config` |
| 管理员/审计员日志 | `/admin/audit` |

管理员侧栏提供“账号管理 / 课程管理 / 隐私参数 / 查询留痕”，审计员只提供“查询留痕”，教师侧栏列出本人课程。管理员可维护员工账号，创建课程、分配教师、设置评价截止时间和创建时的评分维度，并发放评价码；管理员不具有教师的课程结果读取权限。发码结果只在发放时显示一次，请立即复制或下载保存；修改课程截止时间不会延长已发评价码的有效期。教职工可从账号区修改自己的密码，成功后所有会话均须重新登录。品牌与账号退出固定在侧栏顶部/底部，中间导航独立滚动。

`/` 默认进入学生验码页；教职工可通过页面中的链接登录，登录后由 `/workspace` 在浏览器端根据账号角色跳转；教师暂无课程时可重新检查分配、修改密码或退出登录。教师看板可导出当前已发布结果的 CSV/PDF；侧栏“导出快照”可不打开看板，直接下载最近一次发布或输入已知编号下载历史快照，不会触发新的统计发布。正式模板位于 `src/taces/presentation/templates/`，页面取数统一经过 `static/js/api.js`，Mock 数据集中在 `static/js/mock.js`。`USE_MOCK=true` 时，页面中的登录、统计、配置和日志均为模拟交互，不代表真实库中的账号或数据。

真实接口入口是 `src/taces/presentation/static/js/api.js`，`USE_MOCK` 默认为 `false`，静态调试时可手动启用Mock。真实登录、Cookie会话与四个启用演示账号的角色跳转已有回归，其他页面边缘交互仍需继续验收。真实后端也可通过HTTP客户端与自动化测试使用，字段及错误码见 [API_CONTRACT.md](docs/API_CONTRACT.md)，账号权限见 [AUTH.md](docs/AUTH.md)。

## 数据与发布规则

- 三个物理 SQLite 文件：`identity.db` 存账号/会话与评价码，`evaluation.db` 存匿名评分/评语，`metadata.db` 存课程、策略、账本、快照与审计；三库共 15 张表。
- 学生没有登录账号。身份库不保存提交 ID，评价库不保存学生标识、评价码、IP 或精确提交时间。
- 每门课默认三个等权维度：教学内容、教学方法、考核方式；创建课程时可指定 1–10 个维度。评分必须为整数 1–5，开放题选填且最多 500 字符，原文不通过统计或导出接口外发。
- 默认每次发布 ε=0.1、k=5、每课总预算4.0；实际参数保存于 `privacy_policy`，管理员可修改。预算以整数微单位记录。
- **新发布扣费，读取同一发布缓存免费，导出复用快照免费。** 数据版本或 ε/k 策略变化可能触发新发布；预算不足时优先返回已有快照，没有快照则返回未发布状态。
- 精确参与数为公开信息，k 门槛限制新发布，不撤回已公开的快照；噪声误差界由后端计算。当前浮点 Laplace 实现未经有限精度形式化审计，具体隐私假设见 [BACKEND.md](docs/BACKEND.md)。

## 代码结构

```text
project/
├─ run.py                       应用入口
├─ pyproject.toml               Python版本与直接依赖声明
├─ requirements.txt             pip 直接依赖清单
├─ src/taces/
│  ├─ config.py                 运行配置
│  ├─ presentation/             Flask 路由、CLI、模板与静态资源
│  ├─ business/                 认证、课程、提交、隐私统计、配置、审计与导出
│  └─ data/                     SQLite 连接/事务与 schema/ 建表脚本
├─ tests/                       unit / integration / system / pages / js / experiments
├─ scripts/                     测试数据生成器与副本校验器
├─ docs/                        当前架构与接口说明
└─ db/                          本机运行三库及备份，不入版本库
```

Flask 负责表现层，业务与数据层不依赖 Flask。纯隐私计算位于 `business/privacy/mechanism.py`；持久化预算、发布缓存与事务由统计服务和数据层组织。

## 测试

```bash
python -m pytest -q --cov=taces --cov-report=term-missing
python -m pytest -q tests/integration/test_test_data.py
node --test tests/js/*.test.cjs

# 复核已生成的数据，不改演示库；首次需先生成默认数据集
python scripts/generate_test_data.py --verify-only tests/experiments/output/testdata
```

Python 测试使用临时库；系统测试包含真实本地 HTTP 闭环。JS 回归需要 Node.js，涵盖配置页请求、账号与课程管理、一次性发码、改密、快照导出、登录会话与角色跳转，以及学生提交后的返回行为。涉及后端的 JS 测试使用 PATH 中的 Python（Windows 为 `python`，其他系统为 `python3`）；也可通过环境变量 `TACES_TEST_PYTHON` 指定解释器。数据校验另检查阈值、评分/文本边界、权限、缓存、预算、导出及性能。

已完成 Windows 本地验证；Linux双平台对照、长期运行及全部页面边缘交互尚未验收。文档更新不代表重新运行全部业务测试，执行记录应注明实际命令与范围。

## 版本控制

源码、共享测试、SQL、依赖声明和当前维护文档正常跟踪。数据库及备份、测试/导出产物、账号与评价码清单、虚拟环境、uv.lock和缓存不提交。旧静态原型、本地 AI 上下文及历史实施计划仅本地保留。提交格式见 [COMMIT_CONVENTION.md](COMMIT_CONVENTION.md)。
