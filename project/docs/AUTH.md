# TACES 账号、会话与权限

本模块提供教师、管理员、审计员的账号和会话，以及课程元信息的归属校验。学生凭评价码匿名参与，不建立学生登录账号。课程、匿名提交、统计、配置、审计和导出接口均已实现；整体接口见 [API_CONTRACT.md](API_CONTRACT.md) 与 [BACKEND.md](BACKEND.md)。

登录及角色页面已实现，当前默认使用 Mock；页面状态见 [FRONTEND.md](FRONTEND.md)。本文命令均以 `project/` 为工作目录，先执行 `uv sync`。

## 初始化与升级

全新数据库执行：

```powershell
uv run python -m flask --app run.py init-db
```

已有 v1/v2 数据库先停止服务并备份三个库文件，再显式执行：

```powershell
uv run python -m flask --app run.py upgrade-db
```

当前三库结构版本为 v3，共15张表。v1升级会补齐三个账号表与四个工作流表；v2升级补齐工作流表，保留已有数据。旧评价窗口与旧码在迁移时默认关闭，须由管理员重新配置窗口并发行新码。DDL 和版本更新同事务提交，失败整体回滚。
`init-db` 遇到旧版本会拒绝；重复初始化当前版本、重复升级当前版本均保留数据。
混合版本、未知版本或缺失核心表需要先排查，不能靠删库重建处理。

首次管理员通过终端创建：

```powershell
uv run python -m flask --app run.py create-admin --username admin
```

随后隐藏输入密码并确认。密码为 12–128 个字符；用户名为 3–64 位英文字母、数字、
点、下划线或短横线，存储时转小写，因此大小写不区分。空库初始化不会创建默认账号或密码；合成演示账号由 [数据生成器](../scripts/README.md) 显式创建。
此命令仅允许账号表为空时执行；其他账号由已登录的管理员创建。
Werkzeug 的直接依赖已列入 `pyproject.toml` 与 `requirements.txt`；安装工具按声明解析版本，生成的 `uv.lock` 只在本地保留。

## 权限

| 角色 | 当前权限 |
| --- | --- |
| 管理员 `admin` | 创建/列出/修改员工账号；管理课程与发码；配置隐私参数；读取审计日志 |
| 教师 `teacher` | 查看本人课程元信息、发布/读取本人课程统计、导出本人课程快照 |
| 审计员 `auditor` | 登录、查看自己账号、修改自己密码、只读审计日志；不能调用课程列表 |

未登录返回 401，角色或课程归属不符返回 403。角色取自服务端账号，客户端提交角色不能改变权限。
教师的 `user_id` 对应课程的 `teacher_id`；教师账号降为其他角色前须先转移课程。
已有课程的旧 `teacher_id` 不会自动猜测映射到新账号，需通过课程管理 API 显式分配。
管理员对课程元信息的访问不赋予统计查询权，统计与导出服务分别校验对应权限；统计服务校验 `statistics:own` 和课程归属。

账号禁用、角色修改、管理员重置密码、本人修改密码会撤销该账号全部会话。
修改当前账号后需重新登录。系统始终保留至少一个启用的管理员，冲突返回 `409 / LAST_ADMIN`。
账号管理写入与操作者的权限复核在同一个写事务中完成。

## API 契约

成功响应为 `{"data": ...}`，错误为 `{"error":{"code":"...","message":"..."}}`。
JSON 接口拒绝未知字段和错误类型；账号响应不含密码散列或会话摘要。

| 方法与路径 | 输入 | 成功 data |
| --- | --- | --- |
| `POST /api/auth/login` | JSON：`username`, `password`；请求头 `X-TACES-Request: 1` | `account`, `csrf_token`, `expires_at`；设置会话 Cookie |
| `GET /api/auth/me` | 会话 Cookie | `account`, `csrf_token`, `expires_at` |
| `POST /api/auth/logout` | 会话 Cookie + CSRF 头 | `logged_out: true`；撤销当前会话 |
| `POST /api/auth/password` | JSON：`current_password`, `new_password`；Cookie + CSRF 头 | `login_required: true`；撤销本人全部会话 |
| `GET /api/admin/accounts` | 管理员 Cookie；可选 `limit`（1–100，默认 100）、`offset`（非负整数，至多 9 位） | `accounts` 列表，按用户名排序 |
| `POST /api/admin/accounts` | 管理员 Cookie + CSRF 头；JSON：`username`, `password`, `role` | 201，`account` |
| `PATCH /api/admin/accounts/<user_id>` | 管理员 Cookie + CSRF 头；JSON：`role`、布尔 `is_active`、`password` 中至少一项 | `account` |
| `GET /api/courses` | 管理员或教师 Cookie | `courses`，教师仅看到本人课程 |
| `GET /api/courses/<course_id>` | 管理员或该课程教师 Cookie | `course`，不存在返回 404 |

`account` 包含 `user_id`、`username`、`role`、布尔 `is_active` 和整数 `created_at`。
`created_at` 与 `expires_at` 是 UTC Unix 秒。所有已登录的写请求携带 `X-CSRF-Token`，
值从登录响应或 `/api/auth/me` 获取，并与当前会话绑定。登录要求 JSON 与自定义请求头，
阻止浏览器通过跨站表单发起登录；不开放跨来源 CORS，存在 `Origin` 时须匹配请求来源。
命令行客户端可不发送 `Origin`，但必须遵循同样的 JSON/请求头要求。

本地 PowerShell 调用示例（会提示隐藏输入，演示账号密码只在内存中组装）：

```powershell
$credential = Get-Credential -UserName admin
$body = @{ username = $credential.UserName; password = $credential.GetNetworkCredential().Password } | ConvertTo-Json
$login = Invoke-RestMethod http://127.0.0.1:5000/api/auth/login -Method Post `
  -ContentType application/json -Headers @{ 'X-TACES-Request' = '1' } `
  -Body $body -SessionVariable staffSession
$body = $null
Invoke-RestMethod http://127.0.0.1:5000/api/auth/me -WebSession $staffSession
Invoke-RestMethod http://127.0.0.1:5000/api/admin/accounts -WebSession $staffSession
Invoke-RestMethod http://127.0.0.1:5000/api/auth/logout -Method Post `
  -WebSession $staffSession -Headers @{ 'X-CSRF-Token' = $login.data.csrf_token }
```

## 会话与安全配置

密码使用 Werkzeug 的 `scrypt:32768:8:1` 加盐散列；会话使用 256 位随机值，数据库仅存 SHA-256 摘要。
服务端检查固定过期时间；读取会话不会续期。重复登录会替换该浏览器旧会话，每个账号最多保留 10 个会话。
退出后的 Cookie 重放无效。Cookie 为 `taces_session`，`HttpOnly`、`SameSite=Strict`，范围 `/api`。
CSRF 值由随机会话值通过 HMAC 派生，不是身份或角色凭证。

| 环境变量 | 默认值 | 作用 |
| --- | --- | --- |
| `TACES_SESSION_SECONDS` | `28800` | 绝对有效期，允许 60–86400 秒 |
| `TACES_COOKIE_SECURE` | `false` | 本地 HTTP 开发可用；HTTPS 部署时设置 `true` |

不存在的账号、错误密码和禁用账号均返回相同凭证错误。按规范化用户名计数，15 分钟内累计
5 次失败后，该用户名后续登录返回 429；窗口届满恢复。限流状态跨进程、重启保留，
不记录学生身份或 IP。此限流不能代替部署层的整体请求速率限制，也可能让被恶意尝试的账号暂时无法登录。
本服务没有内置反向代理信任配置；HTTPS 代理部署须正确传递经过信任的外部请求协议和主机，
避免来源校验不匹配。当前默认绑定本机回环地址。

账号创建/修改、密码修改、成功登录/退出与已认证用户的越权拒绝写入只增审计日志。
日志不写入密码、会话值、CSRF 值或请求体。拒绝日志在业务事务回滚后独立提交，
避免失败操作把自身拒绝记录回滚掉。新功能继续保留审计 REPLACE 覆盖保护。

密码和 Cookie/CSRF 配置分别参考 [Werkzeug 安全接口](https://werkzeug.palletsprojects.com/en/stable/utils/#werkzeug.security.generate_password_hash)
与 [Flask 安全说明](https://flask.palletsprojects.com/en/stable/web-security/)。

## 本地验证

测试和 `pytest.ini` 已随 `2c5b44d` 纳入版本库，共享测试不得为单方改动而放宽断言。可运行：

```powershell
uv run python -m pytest -q --cov=taces --cov-report=term-missing
```

测试命令运行于临时库，不使用本机演示库。实际命令、结果和未运行项记录在执行日志或提交说明中；历史覆盖率不代表本轮重跑。
