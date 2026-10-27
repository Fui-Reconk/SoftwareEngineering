# 后端业务闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use executing-plans inline; user explicitly requires each part to be reviewed by a subagent that reads the system review-agent skill before committing.

**Goal:** 在保留前端文件与现有账号契约的前提下，补齐课程/码、匿名提交、统计发布、配置/审计和导出，逐段测试、审查、提交。
**Architecture:** Flask仅负责协议；business服务在既有三库事务内认证、写入和审计。原八核心表与三账号表保留，v3显式迁移新增workflow支撑表；发布缓存/预算/留痕同一事务。
**Tech Stack:** Python>=3.12、Flask、Werkzeug、SQLite；导出与时区如需依赖则同步pyproject/requirements/uv.lock，不引外部服务。
**Spec:** ../BACKEND.md、../API_CONTRACT.md，以及用户2026-10-27转达的frontend最新契约（用户消息优先于尚未同步主区的文档）。
**Baseline:** 754d681；frontend68a8c49的契约修正仅作依据，不合并该分支，不修改其受保护文件。

## Global Constraints

- 保持GET /api/courses返回course_id/name/teacher_id/term，不加code/title别名。
- 不编辑app.py、pages.py、templates/static、HTML错误分支、assets/AI_HANDOFF.md；不生成REVIEW_HANDOFF。
- 蓝图仅在routes/__init__.py注册。共享测试正常跟踪，不能削弱旧断言；版本升级的当前版本硬编码可改为SCHEMA_VERSION，保留同等拒绝断言。
- 学生verify/submissions仅凭32位十六进制评价码，无会话/CSRF。码只存摘要，消费与评价写入原子完成，不保存码到submission的关联或个人提交时间。
- 统计业务拒绝200+unpublished，含sample/threshold/shortfall/charged；成功含interval/spread/distinguishable/budgetExhausted；预算耗尽仍可返回最后发布。
- 首次发布扣费，同一版本缓存免费、同数值/时间；配置/数据新版本触发新发布并计费。导出复用已发布快照，不重新采样。
- 审计自带courses=[{course_id,name}]，用户名/中文动作/Asia/Shanghai时间，支持from/to/course/limit/offset。
- 复用已批准的分片及用户自主执行/提交授权，不重新请求设计或计划审批。每段红绿测试和完整回归后使用实际review-agent skill只读审查，修复确认问题后commit；不merge/push。
- 不写真实库，所有故障与并发测试用临时库，路径相对化，执行日志只保留忽略目录。

## 隐私实现口径

精确参与样本数/码总数按契约视为公开元信息；保护对象是固定参与集合中一人的评分和受限开放题贡献替换，不宣称保护是否参与。
单份提交每维一分(1..5)，d<=10；均值向量L1敏感度4d/n，用本次epsilon的1/2；五档每人均分直方图L1敏感度2，用epsilon的1/4。
开放题采用固定公开12词表、每人最多3个不同词的文档频率，并含是否填写的计数，联合L1敏感度最多7，用epsilon的1/4；不用私有词表，不返回原文。
所有显示量为上述输出的后处理；pooledMean由加噪维度均值加权计算，区间为联合90%噪声界并包含舍入误差，spread=max-min，distinguishable检查区间分离。
整数微单位预算扣epsilon总量，与三个机制分配之和一致。有限精度采样是教学实现，不声称浮点实现已有形式化纯DP证明。参考Dwork/Roth第3章Laplace与顺序组合。
完整v1/v2保留数据迁移v3，不改旧表列顺序，旧码默认关闭到人工重新分配。

## Review Focus

跨库/版本迁移与失败回滚；匿名提交并发重复码；预算/缓存并发发布与回滚；新旧策略和耗尽后缓存读取；权限、CSRF边界；匿名文本不得经日志/异常/词表/导出泄露；配置降低预算不得低于已消费；日期/分页/CSV注入与PDF中文。

### Task 1: 课程、评价码与v3迁移
**Files:** data/database.py、data/schema/workflow.sql、business/courses/service.py、business/common.py、routes/courses.py、routes/__init__.py；新tests/integration/test_courses.py、test_workflow_migration.py。
**Interfaces:** CourseService(db,auth).create(token,body)、update(token,id,body)、issue_codes(token,id,count,expires_at=None)；返回原course形状或一次性明文codes。v3新增course_state(截止/数据版本)、code_state(码过期)、privacy_policy(默认epsilon0.1,k5,total4,revision1)、agg_result(课程/数据/策略/JSON发布快照)。
- [x] 写HTTP/迁移失败、保存旧核心数据、重复/错教师、维度/窗口/批量码、只存摘要和审计回滚红测。
- [x] 观察真实红测；实现最小业务与v1/v2→v3原子迁移；旧测试仅将当前版本2改为SCHEMA_VERSION。
- [x] 定向与全量绿测；独立review-agent审查此段全部diff，修复后commit。

### Task 2: 无会话匿名提交
**Files:** business/submission/service.py、routes/submissions.py、registry；tests/integration/test_submissions.py。
**Interfaces:** verify(code)->{valid,reason?/course?}；submit(code,ratings,openText='')->{submissionId}，整笔原子写入/码消费/数据版本++。
- [x] 写无CSRF、无效/已用/过期、完整维度整数分/文本、失败不耗码、两并发只一成功、匿名字段与无个人审计的红测。
- [x] 实现并转绿；全量回归、review-agent、修复、commit。

### Task 3: 纯隐私计算与原子发布
**Files:** business/privacy/mechanism.py、business/stats/service.py、routes/statistics.py、registry；unit/test_privacy.py、integration/test_statistics.py。
**Interfaces:** pure release(means,hist,wordcounts,textcount,n,weights,epsilon,noise=laplace)->numeric payload；StatisticsService(db,auth).get(token,id)->unpublished/published。
- [ ] 用手算确定的敏感度/组合参数与确定性测试采样钩子写红测；生产随机源不可通过HTTP控制。
- [ ] 写threshold拒绝、非法角色/他人课程、缓存同值同时间免费、并发只发布一次、回滚、预算耗尽旧结果/无旧结果、新数据/策略发布的红测。
- [ ] 实现同一写事务中的权限/读数据/预算/快照/审计；导出用已发布快照读取而非触发发布。
- [ ] 全量回归、review-agent、修复、commit；文档准确说明假设/边界，不虚称正式DP验收。

### Task 4: 配置与审计查询
**Files:** business/config/service.py、business/audit/service.py、business/errors.py(field)、errors.py的JSON分支、routes/governance.py、registry；tests/integration/test_governance.py。
**Interfaces:** config GET/PATCH(values/ranges/units)，PATCH非法422+field；审计GET(entries,next,courses)，from/to本地日期或带时区时间，默认limit50上限100，offset非负。
- [ ] 写admin/auditor/teacher矩阵、CSRF、每课预算、低于已花费拒绝、策略revision与总预算区别、中文动作/用户名/上海时间/课程筛选和日期分页的红测。
- [ ] 实现与测试，不更改HTML错误分支；只读审计不产生递归日志。
- [ ] 全量回归、review-agent、修复、commit。

### Task 5: 快照导出与整体验证
**Files:** business/export/service.py、routes/exports.py、registry；依赖清单/锁文件（如需）、tests/integration/test_exports.py、system/test_business_flow.py、docs/BACKEND.md/API_CONTRACT.md。
**Interfaces:** GET /api/courses/<id>/export?format=csv|pdf&publication=<optional-id>，仅本人教师；默认最后发布，返回已发布数字，未发布409，不扣费。支持明确publicationId精确选择。
- [ ] 写权限/无快照/旧快照/缓存数值一致/不收费/CSV字符安全/PDF、完整管理员建课→学生提交→教师发布→审计员读取闭环红测。
- [ ] 同步必要依赖，验证导出的中文与数值；不修改前端开关（当前仍USE_MOCK=true）。
- [ ] 全量+实际网络烟雾测试、路径/归属检查；review-agent审查、修复后commit。更新后端文档事实，未验收平台/性能项如实记录。
