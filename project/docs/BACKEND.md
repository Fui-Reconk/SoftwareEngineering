# TACES 后端实现说明

更新日期：2026-10-27。本文描述已合入主分支的当前实现；本机用途为合成数据演示与自动化测试。

本文说明后端能力、层间协作、数据与权限边界，以及已有验证和未验收范围。
账号操作见 [AUTH.md](AUTH.md)，业务字段见 [API_CONTRACT.md](API_CONTRACT.md)。
除命令明确切换目录外，文件路径与 PowerShell 命令均相对仓库根目录。

## 1. 当前状态与依据

| 范围 | 实际状态 | 核验入口 |
| --- | --- | --- |
| 工程底座，第 1 片 | 已实现应用工厂、配置、JSON 错误、健康检查、三库事务 | src/taces/presentation、config.py、data/database.py（相对 project/） |
| 账号权限，第 2a 片 | 已实现登录、退出、改密、账号管理、角色与课程归属 | src/taces/business/auth、presentation/routes/auth.py（相对 project/） |
| 数据库 | 当前 schema 版本为 3，三库共 15 张表 | data/database.py 的 SCHEMA_VERSION / TABLES |
| 课程与评价码，第 2b 片 | 已实现管理员课程创建/修改、教师分配、评价窗口与随机评价码批量生成 | 本文第12节 |
| 匿名提交，第3片 | 已实现无会话验码与原子提交，不要求CSRF | business/submission/service.py、routes/submissions.py |
| 统计发布，第4片 | 已实现阈值、向量噪声、发布缓存、预算原子扣费 | 本文第14节 |
| 配置与审计，第5片 | 已实现参数范围校验、每课预算上限和审计筛选查询 | 本文第15节 |
| 快照导出，第6片 | 已实现CSV/PDF、指定历史快照、导出留痕 | 本文第16节 |
| 前端 | 六个功能页面和入口页已实现，USE_MOCK=true；导出按钮尚未接API | [FRONTEND.md](FRONTEND.md) |

需求编号沿用 SRS 的 FR1–FR10、NFR1–NFR7。需求原稿在 class2/assets/docs/，用例在
class3/assets/docs/，实现说明不覆盖或重生成这些手工维护的资料。
2026-10-26 已确定的预算口径是：**新发布扣预算，读取已有发布结果免费，重新采样视为新发布**。
v3迁移建立发布缓存agg_result及工作流支撑表；统计服务使用数据版本和策略修订号确定发布缓存。

本机合成演示三库已由数据生成器安装；数据库与账号/评价码清单不进入版本库。重新生成、备份和恢复见 [测试数据工具](../scripts/README.md)。

## 2. 维护边界

沿用 presentation / business / data 三层结构与原有迁移路径，不引入 ORM 或独立数据库服务。业务及数据层不依赖 Flask，纯隐私计算与聚合可脱离 Web 层验证。持久化预算和发布缓存由业务服务组织事务。

本文是当前实现说明，历史实施计划和本机 AI 上下文只在本地保留。课程 SRS 和手工报告属于独立交付物，更新实现说明不会重生成那些文件。

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
统计与隐私计算可脱离 Web 测试；持久化预算/发布由业务服务组织事务。

## 4. 已有 API 契约

所有下列路径均已注册。成功返回 data，失败返回 error.code / error.message。
统计GET可在首次满足门槛时发布并扣费；其余GET只读业务数据。认证后的拒绝和统计读取可写审计。

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
| POST /api/admin/courses | 管理员+CSRF | 创建课程、维度、窗口与每课预算，201 |
| PATCH /api/admin/courses/<course_id> | 管理员+CSRF | 修改课程名/学期/归属/截止时间 |
| POST /api/admin/courses/<course_id>/evaluation-codes | 管理员+CSRF | 批量发码，201；只此响应可得明文 |
| POST /api/evaluation-codes/verify | 学生评价码，无会话/CSRF | 校验不耗码；200 valid/原因 |
| POST /api/submissions | 学生评价码，无会话/CSRF | 原子评分写入与耗码，201 submissionId |
| GET /api/courses/<course_id>/statistics | 课程所属教师 | 门槛拒绝200，发布与预算/审计同事务，缓存免费 |
| GET/PATCH /api/admin/config | 管理员，PATCH需CSRF | values/ranges/units；非法值422并带field |
| GET /api/admin/audit | 管理员/审计员 | 已翻译日志、上海时间、分页和独立课程筛选项 |
| GET /api/courses/<course_id>/export | 课程所属教师 | format=csv/pdf，复用已发布快照，导出留痕且免费 |

账号响应仅包含 user_id、username、role、is_active、created_at。账号字段见 AUTH.md，业务字段见 API_CONTRACT.md。
员工账号角色为 admin / teacher / auditor；学生使用匿名评价码，不提供学生注册/登录接口。

| 角色 | 元信息与账号 | 业务授权 |
| --- | --- | --- |
| admin | 管理账号、读取课程元信息 | 管理课程、配置隐私参数、读取审计；不自动取得教师统计权 |
| teacher | 读取本人课程元信息 | 统计/导出须同时满足角色权限和本人课程归属 |
| auditor | 登录、查看本人账号、改本人密码 | 审计只读；不能管理账号或访问课程结果 |

所有账号写入都在同一个写事务内重新验证操作者，阻止预认证后被停用/撤权仍然修改。
最后一个启用管理员不能被停用或降权。教师仍有课程时，改变其角色返回 ROLE_IN_USE。
已有课程 teacher_id 不自动映射新账号，课程分配必须通过管理 API 显式处理。

常用错误：400 INVALID_INPUT、401 UNAUTHENTICATED/INVALID_CREDENTIALS、403 FORBIDDEN/CSRF_REJECTED、
404 ACCOUNT_NOT_FOUND/COURSE_NOT_FOUND、409 USERNAME_EXISTS/LAST_ADMIN/ROLE_IN_USE、
415 UNSUPPORTED_MEDIA_TYPE、429 LOGIN_THROTTLED、503 DATABASE_NOT_READY/DATABASE_UNAVAILABLE。
未知路径 404，错误方法 405 并保留 Allow；内部异常 500 不返回堆栈。
所有响应包含 Cache-Control: no-store 与 X-Content-Type-Options: nosniff。

## 5. 三库、版本与迁移

| 文件/schema | 已有表 | 个人数据边界 |
| --- | --- | --- |
| project/db/identity.db / identity | student、enroll_code、account、auth_session、login_throttle、code_state | 员工凭证和会话不进入评价库 |
| project/db/evaluation.db / evaluation | rating、open_text | 不存学生标识、评价码、IP、精确提交时间 |
| project/db/metadata.db / main | course、dimension、budget_ledger、audit_log、course_state、privacy_policy、agg_result | 课程、预算、审计元信息 |

SQL 位于 project/src/taces/data/schema/，版本以 SCHEMA_VERSION=3 为准。
八张原有核心表、三张账号表及四张工作流支撑表，共15张。原表不加列，保持原插入与匿名边界。course_state保存截止时间与数据版本，code_state仅保存码摘要及过期时间，privacy_policy保存配置，agg_result保存不可变发布快照。

- rating 每维度一行，用随机 submission_id 将同份评价分组，同一份评价的维度不可重复。
- open_text 通过 rating_id 关联其中一条评分，不将原文直接返回教师接口。
- score 仅允许整数 1–5；开放题行长度 1–500，未填写时不建行。
- enroll_code 仅预留 64 字符 code_hash、course_id、used_flag，不留学生到提交的关联。
- 提交服务在同一写事务内校验课程与全部维度，不能依赖不存在的跨文件外键。
- 预算使用整数微单位，1 ε = 1,000,000 微单位；SQL防负消耗和超支，发布时条件更新扣费。
- audit_log 拒绝 UPDATE / DELETE；每个连接启用 recursive_triggers，阻止 REPLACE 隐式删除覆盖。
- 版本与预期表名检查不是完整结构指纹、完整性检查或磁盘可写性证明。

init-db 只为新库创建当前结构；当前版本可重复执行，保留数据。
v1/v2必须显式upgrade-db，保留现有核心数据并更新三库版本至3。旧窗口与旧码默认关闭，需管理员明确重新配置并发行新码，不猜测旧教师ID到新账号的映射。未知/混合版本、缺失核心表拒绝接管。
DDL、版本号与事务内的数据改变一起回滚；失败可能留下空文件，但不能靠删库绕过迁移。

## 6. 事务、读取和审计边界

三库使用磁盘主库、ATTACH、DELETE 回滚日志与 FULL 同步；拒绝 WAL。
写入通过 BEGIN IMMEDIATE 串行化，连接关闭时回滚尚未完成的事务。
初始化/迁移逐条执行完整 SQL，避免 executescript 提前提交已有事务。

读取入口与结构校验：

| 数据入口 | 当前行为 | 约束 |
| --- | --- | --- |
| Database.transaction() | 写锁后校验当前结构，再交给业务，异常回滚 | 保留 |
| Database.read() | 低层只读快照，不自动检查版本，供迁移诊断读取 | 保留原语义，明确限制 |
| Database.check_ready() | 通过 read_current 检查版本与表名 | 已与业务读取统一入口 |
| 账号/课程只读服务 | 已使用 read_current，在同一事务内先验证当前结构 | 保持角色与资源归属约束 |

业务只读统一使用 read_current()，在同一只读事务内完成版本与表名校验后再交付连接；低层 read() 保留给旧库诊断。未知版本、混合版本或缺表时，业务读取与 ready 一致返回503。该行为由 tests/integration/test_checked_reads.py 覆盖（相对 project/）。

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

新库从仓库根进入 project/ 执行：

~~~powershell
Set-Location project
uv sync --locked
uv run --locked python -m flask --app run.py init-db
uv run --locked python -m flask --app run.py create-admin --username admin
uv run --locked python run.py
~~~

create-admin 隐藏输入并确认密码，仅空账号表可首次引导，没有预置密码。
旧库先停服务、备份三个文件，再将 init-db 换成 upgrade-db；不运行删库命令。

~~~powershell
Invoke-RestMethod http://127.0.0.1:5000/api/health
Invoke-RestMethod http://127.0.0.1:5000/api/ready
~~~

uv 方式无需改写虚拟环境解释器路径；尚未在 Linux 验收。
每个工作树在project/执行uv sync --locked同步其本地虚拟环境；pyproject.toml、requirements.txt和uv.lock同步维护。tzdata提供Windows时区数据，ReportLab生成PDF，pypdf用于文档回归校验。
Cookie/CSRF/登录限流/密码规则详见 AUTH.md；HTTPS 与代理部署仍需独立联调。

## 8. 测试与验证记录

共享测试与 pytest.ini 纳入版本库；数据库、覆盖率和实验输出不提交。从 project/ 执行：

~~~powershell
uv run --locked python -m pytest -q --cov=taces --cov-report=term-missing --tb=short
uv run --locked python -m pytest -q tests/integration/test_test_data.py
node --test tests/js/config.test.cjs
~~~

2026-10-27已记录的执行结果：最近一次全量运行收集359项，359通过，taces语句覆盖97%（1297语句、42未覆盖）；随后补充两项备份连接关闭/安装失败恢复回归，最终数据工具17项全部通过，Node配置回归2项通过。当前完整收集应为361项，但不能把分别执行的结果称为同一次361项全量运行。

数据生成器的默认数据集另有171项检查通过：1万份原始聚合0.151秒，首次完整统计发布0.212秒，均为本机单次观察。生成器在临时副本回放113条HTTP请求语料，源演示码和预算保持不变。详见 [工具说明](../scripts/README.md)。

文档与忽略规则更新只核验事实、命令、链接和跟踪边界，不因此重复运行全部业务测试。执行记录须区分收集、实际运行、历史结果和未验收项。

## 9. 已实现模块与回归入口

以下路径以 project/ 为基准。

| 模块 | 核心回归 |
| --- | --- |
| 账号与权限 | tests/integration/test_auth.py、test_auth_atomicity.py |
| 数据库与迁移 | tests/integration/test_database.py、test_auth_migration.py、test_workflow_migration.py、test_checked_reads.py |
| 课程与评价码 | tests/integration/test_courses.py |
| 匿名提交 | tests/integration/test_submissions.py |
| 统计、缓存、预算与性能 | tests/integration/test_statistics.py、test_statistics_performance.py；tests/unit/test_privacy.py |
| 配置与审计 | tests/integration/test_governance.py |
| 快照导出 | tests/integration/test_exports.py |
| 真实HTTP闭环 | tests/system/test_business_flow.py |
| 页面与配置衔接 | tests/pages/test_pages.py、tests/js/config.test.cjs |
| 数据生成及安装恢复 | tests/integration/test_test_data.py |

默认参数epsilon=0.1、k=5、每课总预算4.0；隐私模型和工程限制见第14节。

## 10. 结构与事务不变量

| 场景 | 当前行为 |
| --- | --- |
| 当前v3 + 有效会话 | 正常业务读取200，角色或资源归属不符403 |
| 当前v3 + 无效会话 | 401 |
| 任一库未知/混合版本、缺预期表 | 业务读取与ready一致拒绝，503 DATABASE_NOT_READY |
| 完整旧库 + 低层诊断读取 | 可读取以备份/复核，不能供当前业务继续使用 |
| 结构校验失败 | 无隐式升级或文件重建，不新增业务行 |
| 提交/发布/配置/迁移中的写入或审计失败 | 所涉及三库事务回滚 |

临时测试库覆盖上述拒绝路径与并发撤权、重复码、首次并发发布和审计不可覆盖行为。

## 11. 当前前后端衔接

正式页面、静态资源、错误页和业务接口均已合入主分支。应用工厂通过 routes/__init__.py 注册蓝图；非/api请求返回HTML错误页，/api请求返回JSON。

| 入口 | 当前契约 |
| --- | --- |
| GET /api/courses/<id>/statistics | 未发布/阈值拒绝返回200；interval、spread、distinguishable由后端计算 |
| 发布/读取 | 新发布扣预算，重复读取同一缓存免费 |
| GET /api/admin/config | values、ranges、units；PATCH为顶层epsilon/k/epsilonTotal |
| GET /api/admin/audit | 用户名、中文动作、Asia/Shanghai时间及独立courses筛选项 |

页面的USE_MOCK仍为true，模拟账号/评价码与真实库互不关联；导出API已实现，但看板按钮仍禁用。整页真实数据联调尚未完成，不能将页面Mock演示等同于后端闭环验证。

## 12. 课程与评价码管理（第2b片）

管理员先创建启用的teacher账号，再调用POST /api/admin/courses，JSON字段为course_id/name/teacher_id/term，可选closes_at（UTC Unix秒）和dimensions=[{name,weight}]。
course_id允许1–64位英文字母、数字、点、短横线、下划线；课程名至多200、学期至多100字符。默认窗口7天，默认三个等权维度：教学内容/教学方法/考核方式。
维度数量1–10、名称唯一、正权重合计为1；不支持在已有课程中隐式更换维度。PATCH支持name/teacher_id/term/closes_at，closes_at=0立即关闭。
发码POST /api/admin/courses/<id>/evaluation-codes，JSON为count（1–1000）与可选expires_at（不晚于课程截止）。返回codes数组，每码128位熵、32位小写十六进制，仅响应可得明文，数据库只留SHA256摘要。
创建/转移/发码均管理员权限+CSRF，写入与审计同一事务；当前/api/courses原字段不加别名。发码不记录学生姓名或把码关联到评价记录，分发由管理员离线完成。


## 13. 匿名提交（第3片）

两学生接口仅接收JSON，不读取员工身份，也不要求X-CSRF-Token或登录Cookie。verify返回的course仍按学生契约使用code/title/teacher/dimensions，不改变已有/api/courses员工课程列表的字段。
评价码允许32位大小写十六进制，规范为小写后取SHA256。未知或畸形码校验为200 valid=false/unknown；已用为used；过期或关闭窗口为expired。验码不耗码。
提交必须覆盖课程全部维度且名称唯一，score为严格整数1–5（拒绝bool/浮点/字符串），openText可省略或为空，最多500字符，拒绝无效Unicode和NUL。
写事务原子执行条件耗码、评分/开放题写入及课程数据版本+1；写入失败均回滚。两请求同时使用一码仅一个201，另一409 CODE_USED；过期为409 WINDOW_CLOSED，未知码400 INVALID_CODE。
评价库不增加code_hash/student/user/IP/提交时间字段；身份表不加submission_id；匿名验码和个人提交不写审计时间，避免按日志关联身份。

## 14. 统计与隐私发布（第4片）

教师GET /api/courses/<id>/statistics必须有statistics:own且当前仍拥有课程；管理员、审计员不能借课程管理权限读取结果。
默认epsilon=0.1、k=5、每课总预算4.0，均取自privacy_policy；管理员可通过配置API修改。
样本不足返回200 unpublished，包含sample/threshold/shortfall/charged=false，无评分或文本结果。
已发布结果包含publicationId、charged以及前端所需的interval/spread/distinguishable/budgetExhausted。
缓存键为课程、course_state.data_version、privacy_policy.revision；相同键重读不采样、不扣费。
新发布在同一BEGIN IMMEDIATE事务内验证权限、读取评价、条件扣预算、插入快照并留痕；失败整体回滚，并发首次查看只发布一次。
预算不足以支付完整一次发布时返回最后快照、budgetExhausted=true。旧账本已耗尽却没有快照时，200 unpublished/reason=budget_exhausted，不构造虚假结果。
提高门槛不会撤回已经公开的快照；新数据不满足新门槛时仍返回最后快照。统计成功/缓存读取/业务拒绝均记固定动作，只有statistics.publish记实际epsilon费用。

隐私模型是**固定参与名单和精确样本数下，替换一份已接受评价的评分与受限文本**。responses、enrolled、门槛判断、发布时机不是参与隐私保护机制，不能声称隐藏某人是否提交。
使用Laplace向量机制和顺序组合，参考[Dwork与Roth，第3章](https://www.cis.upenn.edu/~aaroth/Papers/privacybook.pdf)。每次发布的epsilon按以下三份相加，账本扣除完整epsilon：

| 输出 | 预算份额 | 替换邻接L1敏感度 |
| --- | --- | --- |
| d个维度均值（1–5分） | epsilon/2 | 4d/n |
| 每份评价等权均分四舍五入后的五档直方图 | epsilon/4 | 2 |
| 12词公开词表文档频数及有文本份数的联合向量 | epsilon/4 | 至多7（每份最多3个不同词，文本有无另计1） |

公开词表为作业/反馈/节奏/实验/清晰/互动/实践/例子/考核/答疑/难度/内容，按固定顺序至多取3词；同词在一份内只计一次。旧库多条文本也按submission_id限贡献。所有词与文本份数始终采样，包括真实计数0的坐标；不做私有候选词选择，不返回原文或自选关键词。
维度噪声后裁剪至[1,5]，pooledMean由这些噪声均值及课程权重后处理。直方图非负化后按公开n归一化、最大余数取整；全部非正时使用公开均匀分配。文本份数裁剪至[0,n]，词频裁剪至该噪声份数。
interval是90%同时噪声误差界，b为均值噪声尺度：min(4,向上保留两位(b·ln(10d)+0.005))。它不是总体抽样置信区间。spread为展示维度最大值减最小值，只有spread>2interval才distinguishable。
生产采样来自secrets.SystemRandom，HTTP没有seed或无噪声开关；纯函数测试可注入确定性噪声回调。当前使用浮点逆CDF，未做有限精度形式化审计，不能等同经验证的严格DP实现。

## 15. 配置与审计（第5片）

GET/PATCH /api/admin/config只允许管理员；PATCH还需CSRF。返回values/ranges/units，epsilon范围0.01–1.0，k为整数3–50，epsilonTotal为每课0.1–20.0。预算只接受JSON数值，最多六位小数，拒绝bool/字符串/非有限数；单次epsilon不能超过总量。非法值或未知键422 INVALID_VALUE，error.field标明字段；空请求标为request。
epsilonTotal明确设置时更新每课总上限和新课程默认值，保留已消费整数微单位；若低于任一已消费金额，整笔拒绝。epsilon/k实际变化才增加策略revision；仅改总上限不使同数据缓存失效。配置、所有课账本、成功审计同事务回滚。

GET /api/admin/audit允许管理员与审计员；教师403。返回entries/next/courses，courses独立查询为[{course_id,name}]，不绕过课程API授权。日志映射固定中文动作、账号用户名和Asia/Shanghai时间；账号操作的目标转换为目标用户名，课程操作转为课程名。历史未知动作显示“历史操作”，不存在的历史账号显示“历史账号”。不返回密码/令牌/评价码/开放题原文。
支持from/to（YYYY-MM-DD本地日期或带时区ISO时间，最多六位小数秒）、course、limit（默认50，1–100）、offset（0–2147483647）。日期from含当天00:00，日期to含整天；ISO时间to含该时刻，拒绝无时区时间、超出微秒精度和反向范围。按整数UTC微秒比较与倒序，时间相同时按插入顺序倒序；next为下一页offset或null。未知/重复查询键和非法过滤400；查询本身不写审计，不递归留痕。
预算JSON小数在解析时保留Decimal，先验证原始十进制范围和微单位可表示性，再转整数；不先经float舍入。审计过滤不使用会舍入至毫秒的julianday。
极端指数导致Decimal无法表示时仍按原字段返回422；未知字段名含不可编码Unicode时以安全的field=request返回422，避免错误响应本身编码失败。

## 16. 快照导出与整体验证（第6片）

GET /api/courses/<id>/export?format=csv|pdf&publication=<可选快照编号>，format默认csv。必须具备exports:own且当前拥有该课；默认取最后发布，可指定32位十六进制publicationId。无任何快照409 NOT_PUBLISHED；指定快照不存在或不属于该课404 PUBLICATION_NOT_FOUND。格式/编号/未知或重复查询键错误400。
导出服务只读agg_result.payload，不调用统计发布或读取评分原文；新提交尚未发布时仍导出旧快照。生成文件与导出审计处于同一事务，失败不返回文件；不加噪、不改账本。
CSV为UTF-8 BOM的两列“指标/值”，基础键对应快照字段，维度/分布/词频键分别为dimension:<名称>、score:<1–5>、term:<公开词>，开放题噪声份数为openText.responses。字符串去前导空白后以=、+、-、@开头时加单引号，避免表格公式执行；数字保持数值。下载文件名仅由保存的发布编号和格式构成。
PDF使用ReportLab并对用户文字转义，表头跨页重复。优先使用环境变量TACES_PDF_FONT指定的本地TrueType/TTC字体，其次动态定位Windows字体目录中的simsun.ttc，再回退STSong-Light CID字体。机器字体路径仅在环境中配置，不写入仓库；非Windows字体回退尚未双平台验收。PDF与CSV均包含同一发布编号、时间和噪声结果，不含开放题原文。
快照保留发布当时的课程名称/学期；后续改名不重写历史。显式字体配置失效时返回通用JSON 500并回滚导出留痕，不生成不完整文件。

本地临时库真实HTTP闭环：管理员登录/建教师与审计员/建课/发码→学生无会话验码并提交→教师发布/缓存重读/导出→审计员读取带课程筛选项的日志。使用随机本地端口，结束时关闭服务，无真实库写入。
单次1万份、每份3维的临时数据首次发布耗时0.166秒（仅本机观察，非跨机器性能承诺）。两页中文PDF已用pypdf校验文本/数值，并渲染逐页检查。尚未运行Linux/Windows双平台对照、72小时长期运行、断电/磁盘满故障、HTTPS代理联调或形式化有限精度DP审计；前端mock开关和页面联调由前端负责。
本轮执行环境为Windows；Linux对照、长稳和OS故障注入需另设验收环境与运行窗口，HTTPS需部署环境，形式化DP需独立审计，均未纳入这次业务闭环验证。前后端代码已合入主分支，页面真实联调仍待mock开关切换和导出按钮等行为接入。
