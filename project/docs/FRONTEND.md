# TACES 前端实现说明

更新日期：2026-10-27。本文描述当前已合入主分支的 Flask 页面；字段定义见 [API_CONTRACT.md](API_CONTRACT.md)。

## 当前状态

登录、教师看板、学生验码、学生评分、管理员隐私配置、审计日志六个功能页面及入口页均已实现。Flask 已启用模板与静态资源，页面路由位于 `src/taces/presentation/routes/pages.py`（以下源码路径均以 `project/` 为基准）。

**当前 `static/js/api.js` 中的 `USE_MOCK=true`。** 页面交互读取 `static/js/mock.js`，不会使用本机真实数据库中的演示账号、评价码、配置或评价。真实业务接口已经实现，但整页切换和浏览器真实联调尚未验收。

看板的导出按钮仍为禁用状态，提示文案还沿用旧占位描述；后端CSV/PDF导出API已实现。后续接入页面时需要同时处理按钮行为与该提示，不能据此认为导出后端缺失。

## 页面入口

| 页面 | 路径 | 实现 |
| --- | --- | --- |
| 入口 | `/` | entry.html + pages/entry.js，浏览器读取会话并按角色跳转 |
| 登录 | `/login` | auth/login.html + pages/login.js |
| 教师看板 | `/teacher/<course_id>` | teacher/board.html + pages/board.js |
| 学生验码 | `/student` | student/code.html + pages/code.js |
| 学生评分 | `/student/evaluate` | student/evaluate.html + pages/evaluate.js |
| 隐私配置 | `/admin/config` | admin/config.html + pages/config.js |
| 审计日志 | `/admin/audit` | admin/audit.html + pages/audit.js |

模板位于 `src/taces/presentation/templates/`，JS位于 `src/taces/presentation/static/js/`。员工页面共用 `base.html` 与 `shell.js`：会话守卫、CSRF元信息、课程列表、账号、退出和移动侧栏。会话Cookie只在 `/api` 路径发送，页面路由不从Cookie判断角色，入口分流在浏览器完成。

## 布局与取数

- Jinja 提供标题、固定文案与内容槽位；页面JS填充数据和绘制图表。不引入前端框架或构建工具。
- 公共token位于 `static/css/app.css` 的 `:root`，纸色 `#edf1ee`、数据色 `#1f6b4e`。字体优先本机 Noto Sans SC，并配置系统字体回退。
- 登录与学生页面使用单列壳；教师、配置、审计使用侧栏壳。公共壳来自同一模板。
- 页面统一通过 `window.API` 取数。`api.js` 的Mock分支与fetch分支返回接口的data部分，错误转换为APIError。
- fetch分支携带同源Cookie与 `X-TACES-Request: 1`；员工写请求有CSRF值时发送 `X-CSRF-Token`。学生凭评价码提交，不要求员工会话或CSRF。
- 审计员没有课程列表权限，shell不会对其调用 `/api/courses`。审计筛选项直接由 `/api/admin/audit` 返回。
- `project/demo/` 是正式页面实现前的独立静态原型，只在本地保留，正式运行与验收均不依赖该目录。历史实施计划也只本地保存。

## 业务展示规则

教师看板读取已发布统计或未发布状态。噪声区间、维度差距与可区分性由后端计算；前端不重新实现隐私计算。当前模板与文案仍围绕默认三个维度，后端支持1–10维不代表页面所有维度数均已验收。

发布成功显示均分、区间、维度、分布与受限词频，不展示开放题原文或预算账本。`enrolled` 的真实后端含义是发行码数，页面目前使用“选课”措辞，尚不能把它当成独立学生名册统计。未发布屏目前按样本不足文案展示；无历史快照的预算耗尽状态等真实边缘路径仍需联调。

已有快照时，预算不足只限制新发布，旧结果可以继续读取；`budgetExhausted=true` 时页面提示该版本不会再更新。默认每次发布ε=0.1，实际噪声区间由后端根据样本与维度计算，不能把Mock中的固定区间当成真实默认值。

学生评价码经POST校验，不放URL。评分页从前端会话状态取课程与评价码，无该状态则返回验码页。所有维度选满后才允许提交，开放题最多500字符；成功后显示回执，已用码或过期码返回入口处理。

隐私配置页从接口读取values/ranges/units，提交顶层epsilon/k/epsilonTotal。ε与k是全局策略，epsilonTotal是每门课预算上限。审计页只读，提供时间/课程过滤与分页，不提供编辑或删除。

## 运行与验证

以 `project/` 为当前目录：

```powershell
uv sync --locked
uv run --locked python run.py
uv run --locked python -m pytest -q tests/pages tests/system/test_entrypoint.py
node --test tests/js/config.test.cjs
```

页面测试检查路由、模板骨架与关键控件；Node回归执行真实配置页JS，并分别用真实后端与Mock验证请求保存回读。它们不等同于所有页面的浏览器联调或当前版本的响应式视觉验收。

后续真实联调需覆盖登录/角色跳转、一次性码完整提交、统计拒绝和缓存状态、导出按钮、配置与审计，以及桌面/平板/手机交互。当前文档更新不修改页面、Mock开关或业务代码。
