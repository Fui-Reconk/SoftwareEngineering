# TACES 可信匿名评教系统

学生凭一次性评价码提交匿名评分和选填评语；教师查看课程统计；管理员管理账号、课程和隐私参数；审计员只读查询留痕。

当前已实现课程与发码、匿名提交、差分隐私统计发布、预算与发布缓存、配置、审计及 CSV/PDF 导出。六个功能页面和入口页已由 Flask 提供。**页面默认启用 Mock，尚未切换为读取真实后端；看板导出按钮也尚未接入已实现的导出 API。**

## 安装与启动

以下命令均以 `project/` 为当前目录。需要 Python 3.12+ 和 uv；本项目为应用，通过 `run.py` 启动，不作为 Python 包安装。

```powershell
uv sync --locked
```

`pyproject.toml` 声明依赖，`uv.lock` 锁定版本；项目显式使用清华 PyPI 镜像。`requirements.txt` 保留直接依赖清单，供 pip 环境使用，版本锁定以 uv 为准。

选择下面一种数据准备方式。

### 本机合成演示

先停止运行中的演示服务，再执行：

```powershell
uv run --locked python scripts/generate_test_data.py --check --install-demo
uv run --locked python run.py
```

生成器默认提供 25 门课、包含 1 万份性能样本的合成评价、演示账号和评价码，校验通过后安装到 `db/`，已有三库先备份。默认输出目录为 `tests/experiments/output/testdata/`，必须不存在；再次生成请指定新的 `--output`，例如 `--output tests/experiments/output/demo-2`。

账号、评价码、覆盖范围、备份与恢复方式见 [scripts/README.md](scripts/README.md)。学生演示码在生成清单的 `codes.student_demo`，有效窗口为生成后 30 天。数据校验在临时副本执行，不消耗演示库中的码或预算。

### 空库开始

```powershell
uv run --locked python -m flask --app run.py init-db
uv run --locked python -m flask --app run.py create-admin --username admin
uv run --locked python run.py
```

管理员密码通过终端隐藏输入。空库没有默认账号；其他员工账号、课程与评价码由管理员通过 API 创建。应用启动不会隐式建库或发码。已有 v1/v2 库须先停服务并备份三个文件，再执行 `upgrade-db`，不要用删库代替升级；当前结构版本为 v3。

默认监听 [http://127.0.0.1:5000](http://127.0.0.1:5000)。`/api/health` 检查进程，`/api/ready` 检查三库是否就绪。

## 页面与真实接口

| 页面 | 路径 |
| --- | --- |
| 员工登录 | `/login` |
| 学生验码与评分 | `/student`、`/student/evaluate` |
| 教师看板 | `/teacher/<course_id>` |
| 管理员隐私配置 | `/admin/config` |
| 管理员/审计员日志 | `/admin/audit` |

`/` 在浏览器端根据账号角色跳转。正式模板位于 `src/taces/presentation/templates/`，页面取数统一经过 `static/js/api.js`，Mock 数据集中在 `static/js/mock.js`。`USE_MOCK=true` 时，页面中的登录、统计、配置和日志均为模拟交互，不代表真实库中的账号或数据。

切换真实接口的入口是 `src/taces/presentation/static/js/api.js` 的 `USE_MOCK`。目前尚未完成整页真实联调，单独切换该值不代表所有页面行为已验收。真实后端可通过 HTTP 客户端与自动化测试使用，字段及错误码见 [API_CONTRACT.md](docs/API_CONTRACT.md)，账号权限见 [AUTH.md](docs/AUTH.md)。

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
├─ pyproject.toml / uv.lock      依赖声明与锁定版本
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

```powershell
uv run --locked python -m pytest -q --cov=taces --cov-report=term-missing
uv run --locked python -m pytest -q tests/integration/test_test_data.py
node --test tests/js/config.test.cjs

# 复核已生成的数据，不改演示库；首次需先生成默认数据集
uv run --locked python scripts/generate_test_data.py --verify-only tests/experiments/output/testdata
```

Python 测试使用临时库；系统测试包含真实本地 HTTP 闭环。JS 回归需要 Node.js，涵盖配置页请求与真实 API/Mock 的衔接。数据校验另检查阈值、评分/文本边界、权限、缓存、预算、导出及性能。

已完成 Windows 本地验证；Linux 双平台对照、长期运行与整页真实联调尚未验收。文档更新不代表重新运行全部业务测试，执行记录应注明实际命令与范围。

## 版本控制

源码、共享测试、SQL、依赖锁文件和当前维护文档正常跟踪。数据库及备份、测试/导出产物、账号与评价码清单、虚拟环境和缓存不提交。旧静态原型、本地 AI 上下文及历史实施计划仅本地保留。提交格式见 [COMMIT_CONVENTION.md](COMMIT_CONVENTION.md)。
