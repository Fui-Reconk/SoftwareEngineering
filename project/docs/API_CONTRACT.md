# 前端依赖的接口契约

本文记录当前已实现的业务接口，供页面与HTTP客户端使用。账号管理完整契约见 [AUTH.md](AUTH.md)，课程管理、事务与隐私假设见 [BACKEND.md](BACKEND.md)。字段变更须同步调用方并在末尾登记。

页面默认连接真实API，真实登录与按角色跳转已验证；导出按钮尚未接入已实现的导出API。

统一约定：成功响应 `{"data": ...}`，错误响应 `{"error": {"code": "...", "message": "..."}}`。
登录请求携带 `X-TACES-Request: 1`；已登录员工的写操作带 `X-CSRF-Token`，值来自登录响应或 `/api/auth/me`。`/api` 前缀以外的请求返回 HTML 错误页。

**例外：学生端的两个写接口不带 CSRF。** `POST /api/evaluation-codes/verify` 与 `POST /api/submissions`
面向没有账号的学生，没有会话可绑 CSRF；它们的能力由一次性评价码本身承担。前端在这两个请求上不发
`X-CSRF-Token`，后端也不要因此拒绝它们。

## 已有

| 方法与路径 | 状态 | data 形状 |
| --- | --- | --- |
| `POST /api/auth/login` | 已有 | `{account, csrf_token, expires_at}` |
| `GET /api/auth/me` | 已有 | `{account, csrf_token, expires_at}` |
| `POST /api/auth/logout` | 已有 | `{logged_out: true}` |
| `GET /api/courses` | 已有 | `{courses: [{course_id, name, teacher_id, term}]}`，教师只看到本人的课 |

`account` 为 `{user_id, username, role, is_active, created_at}`，`role` 取 `teacher` / `admin` / `auditor`。
**审计员调不了 `GET /api/courses`**（`list_courses` 只放行 admin 与有 `courses:own` 的教师），页面不要对审计员发这个请求。

## 业务契约与实现状态

2026-10-27：统计、评价码校验、匿名提交、配置、审计查询及CSV/PDF导出均已实现。以下JSON展示data部分，请求体示例除外。

### 1. 统计发布（第 4 片）

`GET /api/courses/<course_id>/statistics`

**拒绝不是错误响应。** 样本不足时返回 `200`，`state` 为 `unpublished`，字段如下：

```json
{ "state": "unpublished", "reason": "below_threshold",
  "sample": 3, "threshold": 5, "shortfall": 2, "charged": false }
```

发布成功时（合成字段示例，默认三维、n=235、ε=0.1；每次实际发布值随机）：

```json
{ "state": "published", "publicationId": "0123456789abcdef0123456789abcdef", "charged": true,
  "courseCode": "SE201-03", "courseTitle": "数据结构", "term": "2025–2026 学年第二学期",
  "responses": 235, "enrolled": 287, "publishedAt": "2026-06-30T10:13:00+08:00",
  "budgetExhausted": false,
  "pooledMean": 3.86, "interval": 3.48, "spread": 0.30, "distinguishable": false,
  "dimensions": [{ "name": "教学内容", "value": 4.02 },
                 { "name": "教学方法", "value": 3.72 },
                 { "name": "考核方式", "value": 3.84 }],
  "distribution": [{ "score": 1, "count": 15 }, { "score": 2, "count": 30 },
                   { "score": 3, "count": 50 }, { "score": 4, "count": 90 },
                   { "score": 5, "count": 50 }],
  "openText": { "responses": 118, "terms": [{ "word": "作业", "count": 42 }] } }
```

三条硬要求：
- `interval`、`spread`、`distinguishable` **由后端算**。前端不重算差分隐私，两份实现迟早不一致。
- 扣费按发布。重复查看命中发布缓存，返回同一份 `publishedAt` 与数值，不再扣预算、不再加噪。
- 已有快照时，预算用完后仍是 `state: "published"`（返回最后一次发布）；`budgetExhausted` 为 `true`，页面在页脚说明「这份不会再更新」。没有任何历史快照时可以返回未发布，见下文。

后端补充：published含publicationId（已发布快照标识）及charged（本请求是否新发布）。精确参与数不受差分隐私保护；interval是噪声误差界，模型假设见BACKEND.md第14节。若历史账本已耗尽却从未保存发布，则200 unpublished/reason=budget_exhausted，仍带sample/threshold/shortfall/charged=false。门槛升高也不会撤回已有公开结果。

### 2. 评价码校验（第 3 片）

`POST /api/evaluation-codes/verify`，请求 `{"code": "<32 位十六进制>"}`

```json
{ "valid": true,
  "course": { "code": "SE201-03", "title": "数据结构", "teacher": "李砚秋",
              "dimensions": [{ "name": "教学内容" }, { "name": "教学方法" }, { "name": "考核方式" }] } }
```

失败返回 `200` 且 `{"valid": false, "reason": "used" | "unknown" | "expired"}`，三种原因页面各有一句文案。
校验不消耗评价码；码在提交时作废。

### 3. 提交评价（第 3 片）

`POST /api/submissions`

```json
{ "code": "<同一串评价码>",
  "ratings": [{ "dimension": "教学内容", "score": 4 },
              { "dimension": "教学方法", "score": 4 },
              { "dimension": "考核方式", "score": 4 }],
  "openText": "选填，≤500 字" }
```

成功返回201，data为 `{"submissionId": "..."}`。必须按课程配置提交全部维度，示例为默认三维；评分为严格整数1–5，开放题可省略或为空，非法字段/评分/文本返回400 INVALID_INPUT且不耗码。评价码随同一次请求提交，**不放 URL**。
码已失效返回 `409` / `CODE_USED`，窗口关闭返回 `409` / `WINDOW_CLOSED`。

### 4. 隐私参数（第 5 片）

`GET /api/admin/config` 与 `PATCH /api/admin/config`

```json
{ "values": { "epsilon": 0.1, "k": 5, "epsilonTotal": 4.0 },
  "ranges": { "epsilon": { "min": 0.01, "max": 1.0 },
              "k": { "min": 3, "max": 50 },
              "epsilonTotal": { "min": 0.1, "max": 20.0 } },
  "units": { "epsilon": "ε", "k": "份", "epsilonTotal": "ε" } }
```

范围与单位由接口给，页面不写死。`epsilonTotal` 是**每门课**的预算总量，不是全局一个。
`PATCH` 请求为顶层 `{"epsilon": 0.1, "k": 5, "epsilonTotal": 4.0}` 或其中非空子集，不加 `values` 包装；只接受这三个键，非法值返回 `422` / `INVALID_VALUE` 并带上 `field`。

预算数值最多六位小数；单次epsilon不超过epsilonTotal；总预算不能低于任一课程已消费金额。仅修改总预算不清零消费、不重采样已有缓存。epsilon或k实际变化将使下一次符合门槛的发布使用新策略并扣费。

### 5. 审计留痕（第 5 片）

`GET /api/admin/audit?from=&to=&course=&limit=50&offset=0`，管理员与审计员都可读。

```json
{ "entries": [{ "at": "2026-06-30T10:13:00+08:00", "actor": "李砚秋",
                "action": "登录", "target": "—", "epsCost": 0 }],
  "next": 50,
  "courses": [{ "course_id": "SE201-03", "name": "数据结构" }] }
```

- `actor`、`action` 已翻译成人与中文；`at` 是 `Asia/Shanghai` 的 ISO 时间。前端只填槽，不自建动作字典。
- `courses` 由这个接口自己返回，因为审计员只有 `audit:read`，调不了 `/api/courses`。
- 只读，没有删除或编辑入口。

from/to支持上海本地YYYY-MM-DD日期和带时区ISO时间（最多六位小数秒）；日期to含整天，ISO to含该时刻。limit默认50、上限100；offset非负。重复/未知查询键、非法或反向时间范围400。

### 6. 快照导出（第6片，后端新增）

`GET /api/courses/<course_id>/export?format=csv|pdf&publication=<可选publicationId>`，仅课程所属教师。format默认csv，指定publicationId可取历史发布；省略则取最后一次发布。返回附件文件，不套JSON data。CSV为UTF-8 BOM；PDF支持中文。导出不触发发布、不扣预算，保留与看板相同的快照编号、时间和数值。
无发布409 NOT_PUBLISHED，指定快照不存在或不属于该课404 PUBLICATION_NOT_FOUND，非法/重复/未知查询参数400。看板按钮当前仍禁用，页面导出与Mock切换尚待接入。

## 差异登记

后端实现与上面不一致时，在这里加一行：`日期 · 接口 · 改了什么 · 前端要跟着改哪里`。

2026-10-27 · GET /api/courses / GET /api/admin/audit · 课程列表保持course_id/name/teacher_id/term；审计筛选courses为course_id/name，以用户最新同步为准，不添加code/title别名。

2026-10-27 · 文档与实现对齐 · 补齐publicationId/charged、三维完整提交与五档分布示例，明确登录请求头、顶层配置请求及无历史快照预算耗尽例外；不更改API行为。
