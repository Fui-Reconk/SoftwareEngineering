# 后端文档与已有读取边界对齐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 重写后端实现说明，保留已验收契约，修复业务只读绕过数据库版本/表检查的问题，补充真实回归。
**Architecture:** 在现有 Database 上增加经过当前结构校验的只读上下文 read_current()，复用原 read() 的连接和事务。只读业务与 readiness 统一入口，保留低层 read() 用于旧库诊断。
**Tech Stack:** Python 3.12 本地环境 / Flask / Werkzeug / sqlite3 / pytest；不安装新依赖。
**Spec:** [已获用户确认的后端实现说明](../BACKEND.md)，特别是第 2、6、10 节。
**Baseline:** 29f2477；暂停前基线1f565e2已有176项通过；用户选择隔离 worktree，允许本代理细化计划后直接执行。

## Global Constraints

- 仅整理工程底座与账号权限，不开发第 2b 或后续统计业务，不修改前端样例、PRODUCT、README、他人忽略规则。
- 评价库不新增身份/会话字段；不修改 SQL 或 schema 版本 2，不隐式升级或重建数据库。
- data 与 business 不 import Flask，保持 JSON/角色/Cookie/CSRF/事务现有契约。
- 路径相对仓库或明确的 project/ 基准，禁止写入本地完整路径。
- project/tests 与 project/pytest.ini 自2c5b44d起正常跟踪，新增回归随代码交付；不能为变绿而放宽共同断言。
- 用户指定 executing-plans 自行执行；只在全轮结束做一次独立审查。
- 本轮遵守最新前后端文件归属，app.py不修改，HTML分支不修改，预留接口只记录不实现；2026-10-27用户授权使用review-agent skill的子代理审查、问题修复并验证后自主commit；不自动merge/push。
- 本地验证可用原工作区已安装的 Python 解释器，但执行目录、pytest 配置和加载源码必须来自本 worktree。机器路径只写忽略的执行配置。
- 每个 Task 的 BASE、实际测试和 Ruling 写入执行ledger；简短更新进度台账，不再生成reviewer交接文档。
- 原工作区教师静态 demo、发布扣费设计保持；已确认口径为新发布扣费/复读缓存免费，agg_result 本轮不落库。

## Review Focus

1. 正常业务读取须同时满足当前 schema 与现有权限；未知/混合版本应先拒绝，不泄露账号/课程数据（Task 2）。
2. 检查必须在交付同一只读连接前完成，不能先独立 check_ready 再另开连接读取（Task 1/2，审查事务范围）。
3. 完整 v1 的低层诊断仍可读取，read_current 不得自动迁移或创建缺失文件（Task 1）。
4. 校验异常退出须关闭连接、不留事务锁，后续合法写入可正常工作（Task 1）。
5. 已有角色/归属、管理员并发保护、REPLACE 防护与迁移失败回滚不得回归（Task 2 完整套件）。

---

### Task 1: 为数据层提供带版本校验的只读上下文

**Files:**
- Modify: project/src/taces/data/database.py
- Create (tracked): project/tests/integration/test_checked_reads.py

**Interfaces:**
- Consumes: Database.read() -> ContextManager[sqlite3.Connection]、Database._validate_schema(connection) -> None、StorageError。
- Produces: Database.read_current() -> ContextManager[sqlite3.Connection]，同一只读事务内先校验当前版本/预期表再 yield；不改变 read()。
- Produces: check_ready() 通过 read_current() 实现，外部成功/失败契约不变。

- [x] Step 1: 在本地新文件编写真实 SQLite 回归：正常 checked read 可查询但不能写；main/identity/evaluation 中任一版本为 0、1、99 时拒绝；缺关键表拒绝；失败后可解除损坏并开启合法写事务；不存在的目录不创建；完整 v1 的 raw read 仍能诊断。
- [x] Step 2: 从 project/ 运行 python -m pytest -q tests/integration/test_checked_reads.py -k data --tb=short。
  Expected: 新 checked read 用例因尚无 read_current 而失败；raw 兼容用例可能通过，不伪造其红测。
- [x] Step 3: 实现 read_current(self) -> Iterator[sqlite3.Connection] 的 contextmanager，在 with self.read() 得到的连接内调用 _validate_schema 再 yield；check_ready 改为进入该上下文，不另开第二个连接。
- [x] Step 4: 同命令重跑。
  Expected: 全部 data 用例通过，没有 SQLite 锁或连接泄漏。
- [x] Step 5: 用 task-done 重跑该任务命令并写 ledger；记录未提交状态，测试按正常源码跟踪，不将运行产物加入索引。

### Task 2: 接入账号/课程读取并完成全量回归

**Files:**
- Modify: project/src/taces/business/auth/service.py
- Extend (tracked): project/tests/integration/test_checked_reads.py
- Update: project/docs/BACKEND.md
- Update (local only): assets/AI_HANDOFF.md 与执行日志；停用reviewer交接文件

**Interfaces:**
- Consumes: Task 1 的 Database.read_current()；现有 AuthService._operation(token, action, write=False)。
- Produces: 所有 AuthService 只读操作使用 checked read，写操作继续 transaction；HTTP 不新增路由/字段，不改变正常状态码。

- [x] Step 1: 在完整正常 v2 库引导临时管理员并登录，加入一门课程；对四种故障分别调用 me、accounts、courses、单课接口：仅 main 99、三库同为 99、三库同为 1、identity 缺 login_throttle。全部应为 503 / DATABASE_NOT_READY，三库字节内容不变。恢复后同一会话读取正常。
- [x] Step 2: 从 project/ 运行 python -m pytest -q tests/integration/test_checked_reads.py -k api --tb=short。
  Expected: 修复前至少四个端点仍返回 200，暴露业务绕过校验；有效失败必须来自接口断言而非测试构造。
- [x] Step 3: 仅将 _operation 的 read 分支改为 database.read_current，保留 write 分支及异常审计流程。
- [x] Step 4: 重跑 api 定向用例，再验证全部新文件。
  Expected: 故障状态全部 503，合法读取与既有鉴权保持，连接关闭后可恢复。
- [x] Step 5: 同步 BACKEND 第 6 节从“方案”改为“已实现”，第 8 节写真实本轮结果/交接入口；前端说明改为原工作区的上下文引用，隔离 worktree 不复制未提交前端文件。
- [x] Step 6: 从 project/ 执行 python -m pytest -q --cov=taces --cov-report=term-missing --tb=short，以 task-done 保存完整输出和 completion。
  Expected: 所有已有和新增用例通过，真实 pass/fail/skip/deselected/error 与覆盖率取自输出，不预填数量。
- [x] Step 7: 路径/链接/变更范围检查；以当前工作区快照生成整轮 review package，独立 reviewer 只读审查一次，按影响处理 Important/Critical；每项修复必须 RED→GREEN 和最终全量通过。
- [x] Step 8: 更新进度台账和执行日志；2026-10-27改为使用review-agent skill的子代理独立审查，修复验证后自主commit，保留分支，不再生成交接文档或等待用户复核。

## 计划自检

范围仅包含一个新增数据接口及其既有服务调用者，未拆仓储、重写登录或新增依赖。
Task 2 消费 Task 1 的 read_current，名称与事务语义一致。
人类文档不写内容断言测试；文档做事实、路径/链接与命令检查。
用户已选择“计划由你细化并执行，先建隔离 worktree”，因此无需再次询问执行方式。

恢复说明：2026-10-26 用户要求后端移至 .agents/worktrees/backend，采用29f2477基线；先前Task1结果作为历史事实保留，恢复后须重新验证新基线，不重复设计或丢弃已证实红测。
