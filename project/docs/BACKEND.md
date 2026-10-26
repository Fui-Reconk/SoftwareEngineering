# TACES 后端运行说明

## 当前交付范围：工程底座与第 2a 片账号权限

已实现应用工厂、集中配置、统一 JSON 错误响应、存活与就绪检查、三库初始化、数据库事务封装和测试。
第 2a 片新增账号管理、登录会话、角色与课程归属校验，以及版本 1 → 2 的显式数据库迁移。
初始化管理员、接口与权限矩阵见 [账号与权限说明](AUTH.md)。

后续顺序：第 2 片账号与权限 → 第 3 片匿名提交 → 第 4 片统计与隐私发布 → 第 5 片配置与审计接口 → 第 6 片导出与整体验证。
下一小步为第 2b 片课程管理与评价码；提交评价和查询统计仍待后续分片实现。当前没有前端页面。
原有 `project/README.md` 是此前的总体施工计划；本说明记录当前可执行的后端操作。

## Windows / PowerShell 启动

在仓库根目录执行（以下相对路径均以仓库根目录为基准）：

```powershell
# 首次启动前显式初始化；重复执行保留现有数据。
.\project\.venv\Scripts\python.exe -m flask --app .\project\run.py init-db

# 启动本地开发服务，默认监听 127.0.0.1:5000。
.\project\.venv\Scripts\python.exe .\project\run.py
```

已有第 1 片数据库须先停止服务、备份三个库文件，并将上述 `init-db` 换为 `upgrade-db`；
`init-db` 会拒绝直接处理旧版本。升级过程不创建账号，首次管理员通过 `create-admin` 交互创建，详见账号说明。

另开一个终端验证：

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/health
Invoke-RestMethod http://127.0.0.1:5000/api/ready
```

Linux 使用同样的 Python 命令，将解释器路径替换为 `./project/.venv/bin/python`。当前仅在 Windows / Python 3.12.10 上实际验证，Linux 尚未运行验收。

## API

| 方法与路径 | 含义 | 成功响应 |
| --- | --- | --- |
| `GET /api/health` | 进程存活检查，不访问数据库 | `200`，`{"data":{"service":"taces","status":"ok"}}` |
| `GET /api/ready` | 检查三库文件、表版本和核心表是否存在 | `200`，`{"data":{"service":"taces","status":"ready"}}` |

未初始化时，`/api/ready` 返回 `503` 和错误码 `DATABASE_NOT_READY`；不会自动创建文件。
数据库访问失败返回 `503 / DATABASE_UNAVAILABLE`；未知内部错误返回 `500 / INTERNAL_SERVER_ERROR`。
不存在的路径返回 `404 / NOT_FOUND`，不支持的方法返回 `405 / METHOD_NOT_ALLOWED`，并保留 `Allow` 响应头。

错误响应统一为：

```json
{"error":{"code":"DATABASE_NOT_READY","message":"数据库尚未就绪，请运行 init-db；已有旧库请运行 upgrade-db。"}}
```

响应不包含堆栈、SQL 或本地文件路径。内部异常记入服务端日志。
响应带有 `Cache-Control: no-store` 和 `X-Content-Type-Options: nosniff`。
就绪检查用于判断初始化状态，不代替完整的数据完整性检查或磁盘可写性检查。

## 运行配置

配置入口：`src/taces/config.py`。环境变量在每次创建应用时读取。

| 环境变量 | 默认值 | 约束 |
| --- | --- | --- |
| `TACES_DATA_DIR` | `project/db` | 相对路径始终以 `project/` 为基准，与启动时的工作目录无关 |
| `TACES_HOST` | `127.0.0.1` | 非空字符串 |
| `TACES_PORT` | `5000` | 1–65535 的整数 |
| `TACES_SQLITE_TIMEOUT` | `5` | 数据库锁等待秒数，大于 0、不超过 60 的有限数值 |

例如，临时更换端口：

```powershell
$env:TACES_PORT = '5001'
.\project\.venv\Scripts\python.exe .\project\run.py
```

应用工厂 `taces.create_app({...})` 支持测试配置覆盖；创建应用本身不创建目录或数据库。
调试器和自动重载默认关闭。HTTP 请求体大小默认限制为 16 KiB，后续业务路由沿用此限制。
ε、k 等隐私策略由后续业务配置模块实现，本片不设定未验收的隐私默认值。

## 三库与核心表

| 文件 | SQLite schema | 核心表 |
| --- | --- | --- |
| `identity.db` | `identity` | `student`、`enroll_code` |
| `evaluation.db` | `evaluation` | `rating`、`open_text` |
| `metadata.db` | `main` | `course`、`dimension`、`budget_ledger`、`audit_log` |

初始化 SQL 位于 `src/taces/data/schema/`，当前三库的 `PRAGMA user_version` 均为 `1`。
`init-db` 只创建表、索引和触发器，不生成账号、课程或测试评价。
版本 2 额外在身份库新增账号、会话和登录限流三张支撑表，结构与升级方式见 [账号说明](AUTH.md)。
遇到未知版本、带有旧表但没有版本号的库时拒绝初始化；不静默接管或清空既有数据库。
初始化中断时 DDL 和版本号一起回滚；可能留下空文件，修复原因后可重新初始化。

字段约定：

- `rating` 每个维度一行，用随机 `submission_id` 将同一份评价分组；`rating_id` 是每一评分行的独立标识。
- `open_text` 挂在同份评价的一条评分行上，通过外键关联 `rating_id`，同份评价只保存一份开放题。后续提交服务负责选择关联行。
- 评价库不保存学生标识、评价码、IP 或精确提交时间。`enroll_code` 预留 SHA-256 格式的 `code_hash`，不存评价记录标识或精确使用时间。
- 评分为 1–5 的整数，同一份评价不可重复写入同一维度。开放题内容限制为 1–500 字符，未填写时不创建该行。
- 跨库的课程、维度关系由后续服务在事务内验证；SQLite 的本库外键约束已启用。当前不能只凭 SQL 约束宣称完整业务校验已完成。
- 预算字段采用整数微单位，`1 ε = 1,000,000` 微单位，避免累计浮点误差；数据库约束已防止负消耗和超支。**扣费按"发布事件"计**（首次把某统计量的加噪值发出），重复查看命中发布缓存不扣；发布扣费与缓存写入属于第 4 片。
- 审计表拒绝 `UPDATE` / `DELETE`，每个连接启用递归触发器以拦截 `REPLACE` 覆盖。账号操作与权限拒绝已写审计；审计查询接口属于第 5 片。此保护针对应用数据库操作，不能阻止有数据库文件控制权的人修改结构。

本片增加了提交分组、整数预算等实现字段，并省略可用于按时间关联学生的提交时间；课程 SRS / 设计流程原稿没有被重写。后续模型变化需要显式迁移，不应通过删库覆盖数据。

## 事务约定

数据访问层 `Database` 不依赖 Flask，每次操作独立打开并关闭连接：

- `read()` 使用只读连接和读事务；缺失文件时拒绝访问，不自动建库。
- `transaction()` 使用 `BEGIN IMMEDIATE` 串行化写事务，身份库、评价库和元数据库一起提交或回滚。
- 三库均要求 `journal_mode=DELETE`、`synchronous=FULL`，拒绝自动切换到 WAL。该设置依照 [SQLite ATTACH 事务说明](https://sqlite.org/lang_attach.html)，用于保持文件库之间的提交原子性。
- 初始化逐条执行完整 SQL 语句，避免 `executescript()` 提前提交现有事务；见 [Python sqlite3 文档](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.executescript)。

已验证程序异常下的跨库回滚；尚未执行断电或操作系统崩溃注入测试，不能将前者当作后者的实测结果。

## 测试

`project/tests/` 和 `project/pytest.ini` 仅保留在开发者本地，已加入忽略规则，不随仓库提交；下列命令适用于保留了这些文件的本地工作区。重新克隆仓库不会获得测试代码或 pytest 配置。

从仓库根目录进入 `project/` 执行（覆盖率文件留在该目录的忽略范围内）：

```powershell
Set-Location .\project
.\.venv\Scripts\python.exe -m pytest --cov=taces --cov-report=term-missing
```

不统计覆盖率时执行 `.\.venv\Scripts\python.exe -m pytest` 即可。

第 1 片历史验证：54 项测试通过，当时已实现 Python 代码语句覆盖率 99%。
包括初始化与重入、三库整体提交与回滚、初始化 SQL 失败回滚、版本拒绝、只读连接、评分与预算约束、审计不可改删、JSON 错误处理，以及从项目外目录调用真实 Flask CLI。
该历史覆盖率只描述第 1 片工程底座。本轮实际测试结果见本地 `assets/REVIEW_HANDOFF.md`（相对仓库根目录）；
账号测试覆盖登录/撤销、CSRF、权限、课程归属、并发管理员保护和数据库升级，隐私与统计仍待实现。
