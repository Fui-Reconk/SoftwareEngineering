# TACES 后端实现说明

更新日期：2026-10-26。当前代码基线：29f2477；工作树为 .agents/worktrees/backend，与 frontend 同级。

本文说明后端已经实现什么、各层如何协作、数据与权限边界，以及后续怎样分片验收。
账号接口的字段示例和操作细节见 [AUTH.md](AUTH.md)。文中“待实现”均不代表已有可调用接口。
除命令明确切换目录外，文件路径与 PowerShell 命令均相对仓库根目录。

## 1. 当前状态与依据

| 范围 | 实际状态 | 核验入口 |
| --- | --- | --- |
| 工程底座，第 1 片 | 已实现应用工厂、配置、JSON 错误、健康检查、三库事务 | src/taces/presentation、config.py、data/database.py（相对 project/） |
| 账号权限，第 2a 片 | 已实现登录、退出、改密、账号管理、角色与课程归属 | src/taces/business/auth、presentation/routes/auth.py（相对 project/） |
| 数据库 | 当前 schema 版本为 2，三库共 11 张表 | data/database.py 的 SCHEMA_VERSION / TABLES |
| 课程与评价码，第 2b 片 | 只有课程元信息读取；课程写入、教师分配、评价码生成待实现 | 本文第 9 节 |
| 匿名提交、统计发布、配置查询、导出 | 待实现，相应 business 包目前为空 | 本文第 9 节 |
| 前端 | 已有独立静态样例 project/demo，尚未接入 Flask | [FRONTEND.md](FRONTEND.md) |

需求编号沿用 SRS 的 FR1–FR10、NFR1–NFR7。需求原稿在 class2/assets/docs/，用例在
class3/assets/docs/，实现说明不覆盖或重生成这些手工维护的资料。
2026-10-26 已确定的预算口径是：**新发布扣预算，读取已有发布结果免费，重新采样视为新发布**。
发布缓存 agg_result 已进入需求设计，当前 SQL 尚未创建该表；不能把设计中的九张核心表误写成当前数据库的表数。

当前产品与文档中若仍有“每次查询重新加噪并扣费”等旧表述，以已确认的发布口径组织后续实现，
并在交接中标出冲突；本轮不修改前端演示或其他课程文档。

## 2. 目标与本轮边界

目标是让开发者能从本文找到真实代码入口、明确调用契约，按同一规则检查与维护已有后端。
本轮采用用户选择的方式：先整理说明，再检查现有代码、修复已确认的问题、补充回归测试。
不在本轮扩展第 2b 片或统计等后续功能，也不将静态样例接到真实数据。

对比过的方式：

- 保留现有三层结构，按可复现问题做小范围整理：本轮采用，能保留已验收的账号行为和迁移路径。
- 重新搭建后端或先拆一套通用仓储框架：会扩大变更与回归面，当前代码规模没有这项需求。
- 直接继续开发剩余业务：不属于用户选定的本轮范围，保留在分片路线中。

完成标准：说明与实际版本、路由、角色、事务一致；确认的问题先有失败回归，再有最小修复；
本地全量测试通过，执行日志记录命令、数量、未运行项与范围；使用review-agent skill的子代理独立审查，修复验证后自主提交。

## 3. 层次与调用关系

~~~text
HTTP / Flask CLI
        |
        v
presentation：请求解析、Cookie、CSRF、JSON、状态码、CLI 提示
        |
        v
business：账号认证、角色/归属、不变量、业务事务与留痕决策
        |
        v
data：连接生命周期、SQLite 读写事务、结构检查、初始化/迁移
        |
        v
metadata.db（main） + identity.db + evaluation.db
~~~

| 入口 | 职责 | 不承担的工作 |
| --- | --- | --- |
| project/run.py | 从项目外启动也能定位 src；提供 Flask app | 不隐式建库、升级或建立默认账号 |
| presentation/app.py | 配置应用、装配 Database/AuthService、注册路由与错误处理 | 不容纳领域规则 |
| presentation/routes/auth.py | 校验 JSON/请求来源/CSRF，转接账号与课程元信息服务 | 不相信请求中的角色 |
| business/auth/service.py | 认证、会话、限流、账号管理与课程归属，组织事务 | 不 import Flask |
| business/auth/policy.py | 显式权限表与课程资源校验 | 不根据前端隐藏按钮判断权限 |
| data/database.py | 三库连接、读写事务、版本约束和 DDL | 不决定教师是否有权查询统计 |
| business/errors.py | 传递可公开的业务错误 | 不暴露 SQL、路径或内部异常 |

应用工厂通过 app.extensions 注入 taces_database 与 taces_auth；每次数据库操作拥有自己的连接。
业务层当前直接使用参数化 SQL，不为整理而强行加入 ORM 或通用仓储框架。
后续统计与隐私计算应保持可脱离 Web 测试；持久化预算/发布则由业务服务组织事务。

## 4. 已有 API 契约

所有下列路径均已注册。成功返回 data，失败返回 error.code / error.message。
GET 不写入业务数据；已认证的越权拒绝可以独立写入审计。

| 方法与路径 | 调用者/约束 | 行为 |
| --- | --- | --- |
| GET /api/health | 公开 | 只确认进程可响应，不访问数据库 |
| GET /api/ready | 公开 | 检查三库文件、版本与预期表名 |
| POST /api/auth/login | JSON + X-TACES-Request: 1 | 建立或轮换当前浏览器会话 |
| GET /api/auth/me | 有效员工会话 | 返回安全账号字段、CSRF、绝对到期秒数 |
| POST /api/auth/logout | 会话 + X-CSRF-Token | 撤销当前会话并清 Cookie |
| POST /api/auth/password | 会话 + CSRF + 当前密码 | 改密并撤销本人全部会话 |
| GET /api/admin/accounts | 管理员 | 按 limit / offset 列账号，不返回密码散列 |
| POST /api/admin/accounts | 管理员 + CSRF | 创建员工账号 |
| PATCH /api/admin/accounts/<user_id> | 管理员 + CSRF | 修改角色、状态或密码，撤销目标全部会话 |
| GET /api/courses | 管理员或教师 | 管理员读全部元信息，教师只读本人课程 |
| GET /api/courses/<course_id> | 管理员或该课程教师 | 单课元信息，跨教师访问拒绝 |

账号响应仅包含 user_id、username、role、is_active、created_at。接口详情、JSON 字段见 AUTH.md。
员工账号角色为 admin / teacher / auditor；学生使用匿名评价码，不提供学生注册/登录接口。

| 角色 | 已有授权 | 后续接口的约束 |
| --- | --- | --- |
| admin | 管理账号、读取课程元信息 | 管理课程、配置隐私参数、读取审计；不自动取得教师统计权 |
| teacher | 读取本人课程元信息 | 统计/导出须同时满足角色权限和本人课程归属 |
| auditor | 登录、查看本人账号、改本人密码 | 审计只读；不能管理账号或访问课程结果 |

所有账号写入都在同一个写事务内重新验证操作者，阻止预认证后被停用/撤权仍然修改。
最后一个启用管理员不能被停用或降权。教师仍有课程时，改变其角色返回 ROLE_IN_USE。
已有课程 teacher_id 不自动映射新账号，后续课程分配必须显式处理。

常用错误：400 INVALID_INPUT、401 UNAUTHENTICATED/INVALID_CREDENTIALS、403 FORBIDDEN/CSRF_REJECTED、
404 ACCOUNT_NOT_FOUND/COURSE_NOT_FOUND、409 USERNAME_EXISTS/LAST_ADMIN/ROLE_IN_USE、
415 UNSUPPORTED_MEDIA_TYPE、429 LOGIN_THROTTLED、503 DATABASE_NOT_READY/DATABASE_UNAVAILABLE。
未知路径 404，错误方法 405 并保留 Allow；内部异常 500 不返回堆栈。
所有响应包含 Cache-Control: no-store 与 X-Content-Type-Options: nosniff。

## 5. 三库、版本与迁移

| 文件/schema | 已有表 | 个人数据边界 |
| --- | --- | --- |
| project/db/identity.db / identity | student、enroll_code、account、auth_session、login_throttle | 员工凭证和会话不进入评价库 |
| project/db/evaluation.db / evaluation | rating、open_text | 不存学生标识、评价码、IP、精确提交时间 |
| project/db/metadata.db / main | course、dimension、budget_ledger、audit_log | 课程、预算、审计元信息 |

SQL 位于 project/src/taces/data/schema/，版本以 SCHEMA_VERSION=2 为准。
八张原有核心表加三张账号支撑表，共 11 张；未来 agg_result 须随显式版本迁移添加。

- rating 每维度一行，用随机 submission_id 将同份评价分组，同一份评价的维度不可重复。
- open_text 通过 rating_id 关联其中一条评分，不将原文直接返回教师接口。
- score 仅允许整数 1–5；开放题行长度 1–500，未填写时不建行。
- enroll_code 仅预留 64 字符 code_hash、course_id、used_flag，不留学生到提交的关联。
- 课程与维度跨库关系须在未来提交业务事务中校验，不能依赖不存在的跨文件外键。
- 预算使用整数微单位，1 ε = 1,000,000 微单位；已有 SQL 防负消耗和超支，扣费业务尚未实现。
- audit_log 拒绝 UPDATE / DELETE；每个连接启用 recursive_triggers，阻止 REPLACE 隐式删除覆盖。
- 版本与预期表名检查不是完整结构指纹、完整性检查或磁盘可写性证明。

init-db 只为新库创建当前结构；当前版本可重复执行，保留数据。
v1 必须显式 upgrade-db，新增身份支撑表并更新三库版本。未知/混合版本、缺失核心表拒绝接管。
DDL、版本号与事务内的数据改变一起回滚；失败可能留下空文件，但不能靠删库绕过迁移。

## 6. 事务、读取和审计边界

三库使用磁盘主库、ATTACH、DELETE 回滚日志与 FULL 同步；拒绝 WAL。
写入通过 BEGIN IMMEDIATE 串行化，连接关闭时回滚尚未完成的事务。
初始化/迁移逐条执行完整 SQL，避免 executescript 提前提交已有事务。

现有接口与本轮整理结果：

| 数据入口 | 当前行为 | 本轮目标 |
| --- | --- | --- |
| Database.transaction() | 写锁后校验当前结构，再交给业务，异常回滚 | 保留 |
| Database.read() | 低层只读快照，不自动检查版本，供迁移诊断读取 | 保留原语义，明确限制 |
| Database.check_ready() | 通过 read_current 检查版本与表名 | 已与业务读取统一入口 |
| 账号/课程只读服务 | 已使用 read_current，在同一事务内先验证当前结构 | 保持角色与资源归属约束 |

已在临时库复现：将 main.user_version 改为 99，ready 返回 503，
但持有效会话读取 auth/me、admin/accounts、courses 仍为 200。
本轮已在 data 层新增 read_current()，在同一只读事务中完成版本/表名校验后再交付连接；
业务只读统一使用它，低层 read() 保留给旧库诊断。下列回归与全量验证用于确认实际修复结果。

账号/会话变更和成功审计在同一事务中提交，审计失败整体回滚。
权限拒绝发生后先退出失败业务事务，再独立提交拒绝日志，避免拒绝记录一同回滚。
日志记录可信账号 ID 与固定动作，不写密码、Cookie、CSRF 或请求体。
文件控制者仍可直接修改数据库或结构，应用内触发器不构成对文件所有者的防护。

## 7. 配置与本地启动

环境变量在创建应用时读取，显式 create_app({...}) 覆盖环境值。
默认调试与重载关闭，请求体上限 16 KiB；创建工厂本身不生成数据库或默认账号。

| 环境变量 | 默认值 | 约束 |
| --- | --- | --- |
| TACES_DATA_DIR | project/db | 代码动态定位；传入相对值以 project/ 为基准，与工作目录无关 |
| TACES_HOST | 127.0.0.1 | 非空字符串 |
| TACES_PORT | 5000 | 整数 1–65535 |
| TACES_SQLITE_TIMEOUT | 5 | 大于 0、至多 60 的有限秒数 |
| TACES_SESSION_SECONDS | 28800 | 整数 60–86400，绝对有效期不滑动续期 |
| TACES_COOKIE_SECURE | false | true/false；HTTPS 部署应启用 true |

新库在仓库根执行：

~~~powershell
.\project\.venv\Scripts\python.exe -m flask --app .\project\run.py init-db
.\project\.venv\Scripts\python.exe -m flask --app .\project\run.py create-admin --username admin
.\project\.venv\Scripts\python.exe .\project\run.py
~~~

create-admin 隐藏输入并确认密码，仅空账号表可首次引导，没有预置密码。
旧库先停服务、备份三个文件，再将 init-db 换成 upgrade-db；不运行删库命令。

~~~powershell
Invoke-RestMethod http://127.0.0.1:5000/api/health
Invoke-RestMethod http://127.0.0.1:5000/api/ready
~~~

Linux 替换为项目虚拟环境的 bin/python；尚未在 Linux 验收。
已有环境由用户通过 uv 配置，不因本轮整理重复安装依赖。
Cookie/CSRF/登录限流/密码规则详见 AUTH.md；HTTPS 与代理部署仍需独立联调。

## 8. 测试与执行记录

提交 2c5b44d 已将 tests 和 pytest.ini 纳入版本库，新的 clone 会获得共享测试。新增回归正常跟踪，不能为变绿而放宽对方的断言；数据库、覆盖率与实验输出仍不提交。
从仓库根进入 project/ 执行：

~~~powershell
Set-Location .\project
.\.venv\Scripts\python.exe -m pytest -q --cov=taces --cov-report=term-missing --tb=short
~~~

本轮在29f2477基线执行完整套件：208 passed、0 failed、0 skipped，语句覆盖率98%（569条语句、14条未覆盖），耗时227.56秒。
其中原有176项未改断言，新增32项只读校验回归。具体命令、红绿过程与未运行项保存在本地执行日志；不再额外生成 reviewer 交接文档。
每次记录执行目录、命令、通过/失败/跳过、deselected/errors、回归场景和未执行原因。

按用户指定的 executing-plans 方式执行：先确定文档/设计，再生成有接口与验收命令的任务计划；
任务开始记录 BASE 和范围，先运行失败回归，再改代码、观察转绿，最后跑完整套件。
不为人类说明文字编写“包含某段文本”的伪测试；文档做事实、链接、路径与命令检查。
同一轮内不反复扩大测试，发现新的问题或代码改变时才补相应验证。
2026-10-27用户授权：使用review-agent skill的子代理独立审查，修复验证后由主代理自主commit，不再等待用户复核；merge/push仍需另行指示。

## 9. 后续分片与验收口径

| 片段 | 工作内容 | 完成时必须验证 |
| --- | --- | --- |
| 2b 课程与评价码 | 管理员创建/分配课程、维度、随机码与安全分发 | 非教师归属拒绝；仅存码摘要；不建立学生到评价的关联；批量失败回滚 |
| 3 匿名提交 | 码校验、维度/评分/开放题校验、消费码与写评价 | 失效/重复码拒绝；并发只成功一次；三库回滚；评价无身份字段 |
| 4 统计与隐私发布 | 均值/分布/维度/受限词频、阈值、噪声、缓存、预算 | 同一发布重复读取值相同且不扣费；新采样新扣费；发布/预算/审计原子提交 |
| 5 配置与审计查询 | 管理员配置策略，管理员/审计员只读日志 | 非法参数拒绝；仅新发布使用新策略；日志不泄露敏感输入 |
| 6 导出与整体验证 | 复用已发布结果导出 PDF/CSV，跨平台与性能 | 导出与看板同源，不重新采样；真实网络端到端；性能/长期/故障测试 |

第 4 片的设计门槛：噪声使用的 ε 必须与实际扣除的 ε_cost 一致；
区分均值与向量统计量的敏感度和输出范围；固定公开词表并限制单份评价贡献。
精确样本数与 k 门槛的发布边界、隐私邻接定义、数据/策略版本与缓存键须在实现前明确。
重新采样、更新评价数据或更改策略不能借“缓存免费”绕过预算。
本轮不替未实现模块选未经确认的 ε/k 默认值，也不宣称已提供完整差分隐私保证。

## 10. 本轮代码整理验收与审查

本轮只处理上述读取结构校验问题及其直接依赖，必要的现有分支回归按风险补齐，
保留健康检查、账号响应结构、Cookie 路径、三角色权限、旧库迁移和审计 REPLACE 防护。

验收矩阵：

| 场景 | 期望 |
| --- | --- |
| 当前 v2 + 有效会话 | 原账号/课程读取仍 200，权限拒绝仍 403 |
| 当前 v2 + 无效会话 | 仍 401 |
| 任一库未知/混合版本、缺预期表 | 业务读取与 ready 一致拒绝，503 DATABASE_NOT_READY，无数据泄露 |
| 完整 v1 + 低层诊断读取 | 仍可读取以备份/复核；不能直接供业务继续使用 |
| 业务版本校验异常 | 三库无新增行、无隐式升级或文件重建 |
| 管理写入、并发撤权、迁移与审计原回归 | 不回归 |

前端演示、PRODUCT.md、前端计划、README 和忽略规则已经由主区提交，
本轮以29f2477为基线保留，不回退或覆盖。进度台账和执行日志保留，使用review-agent skill的子代理直接对照diff、需求与测试证据审查；不再生成reviewer交接文档。


## 11. 前后端协作与前端预留契约

2026-10-26 用户同步的边界优先于旧计划中的“仅本地测试”约定。主区与前端工作树均有独立归属，后端只在 backend 分支工作。

| 归属 | 文件范围（相对 project/src/taces/） |
| --- | --- |
| 前端 | presentation/templates/**、presentation/static/**、presentation/routes/pages.py、presentation/app.py、errors.py 的 HTML 分支 |
| 后端 | business/**、data/**、routes 下除 pages.py 的路由、errors.py 的 JSON 分支，以及 project/docs/ |
| 注册衔接 | 前端 T1 将提供 presentation/routes/__init__.py 的 register(app)；后端新蓝图只增加 import/register_blueprint，不修改 app.py |

前端后续将使非 /api 请求渲染 HTML 错误页，/api 请求继续返回现有 JSON，并将未知页面测试迁入 tests/pages。当前29f2477基线仍统一返回JSON；后端保留未知 API JSON 契约，不抢改页面测试。

以下四项为用户确认的前端设计前提，**前端预留，尚未实现**。相关业务动工前读取前端随后提供的 project/docs/API_CONTRACT.md，核对完整字段类型与可空性，不自行发明不兼容形状。

| 前端预留入口 | 后端必须提供的契约 |
| --- | --- |
| GET /api/courses/<id>/statistics | 统计业务未发布/阈值拒绝返回200，state为unpublished；interval、spread、distinguishable在后端算好，前端不重算差分隐私 |
| 发布/读取 | 新发布扣预算，重复读取同一缓存免费；不得免费重新采样 |
| GET /api/admin/config | 返回 values、ranges、units 三组，前端不写死参数范围 |
| GET /api/admin/audit | 返回已翻译用户名、中文动作、Asia/Shanghai时间，并自带courses供筛选；审计员只有audit:read，不能靠调用/api/courses补齐筛选项 |

统计业务的“未发布”是正常200状态；认证、越权、数据库不可用仍按现有API错误契约处理。本轮只读版本拒绝使用503，不引入统计业务或改变其预留状态码。
