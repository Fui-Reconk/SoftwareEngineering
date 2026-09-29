# TACES 实现代码

可信匿名评教系统（Trusted Anonymous Course Evaluation System）的源码目录，
对应《设计流程》6.1 里 `src/` 这类代码配置项。

需求看 SRS：`../class2/assets/docs/`（2026-09-29 放宽了依赖约束，现在允许 Flask 等轻量库）。
**这里目前只有目录骨架和这份计划，一行业务代码都没写。**

接下来先建 `requirements.txt` 装依赖，然后从 P1 隐私核心动工。

---

## 目录结构

```
project/
├─ README.md                      ← 本文件
├─ requirements.txt               ← 待建，依赖只从这里装（SRS 2.5 / 2.6 / NFR7 的约定）
├─ .gitignore                     ← 挡掉库文件、__pycache__、导出产物
├─ src/taces/                     包名 taces
│  ├─ __init__.py                 Flask 应用工厂 create_app()
│  ├─ config.py                   运行期配置（端口、路径、会话密钥）
│  ├─ presentation/               表现层（《设计流程》4.2）
│  │  ├─ routes/                  Flask 蓝图，按角色分 student / teacher / admin
│  │  ├─ templates/
│  │  │  ├─ base.html             公共版式
│  │  │  ├─ student/              评价码校验页、评分页
│  │  │  ├─ teacher/              结果看板
│  │  │  └─ admin/                参数配置页、审计日志页
│  │  └─ static/{css,js}/         样式与图表脚本
│  ├─ business/                   业务逻辑层
│  │  ├─ privacy/                 核心：Laplace、k 闸门、预算账本
│  │  ├─ submission/              评价服务
│  │  ├─ stats/                   真实统计量（均值、分布、维度对比、词频）
│  │  ├─ audit/                   查询留痕
│  │  ├─ config/                  ε、k、预算总量
│  │  └─ export/                  导出 PDF / CSV
│  └─ data/                       数据访问层
├─ tests/                         unit / integration / system / experiments
├─ db/                            SQLite 库文件和建表脚本，库文件本身不进版本库
├─ docs/                          设计文档、测试报告、使用手册
└─ scripts/                       造数据、计时、备份
```

有三条约束是硬的，写代码时不能绕：

- `student`、`enroll_code` 放身份库，`rating`、`open_text` 放评价库，两个库物理分开，
  中间不留任何可关联字段。这是 NFR1，也是中心化差分隐私能成立的前提。
- `PrivacyMechanism`、`BudgetLedger`、`ThresholdGate` 写成无状态纯函数，不碰数据库、不 import Flask，
  这样能脱离 Web 层单独跑单元测试（NFR5）。
- ε、k、ε_total 只在 `business/config/` 和 `config.py` 里定义，改参数不能牵动业务代码（NFR6）。

## 技术栈

Python 3.10+ + Flask + SQLite。不引需要单独部署的数据库或消息队列，SQLite 经内置 `sqlite3` 访问。
装了哪些库、为什么装，都记在 `requirements.txt` 里（SRS 2.6 的要求）。

Flask 只出现在表现层，负责路由、请求解析和 JSON 响应。`business/` 和 `data/` 里不放它，
否则 NFR5 就没法满足了。

NFR7 的验收方式也跟着改成：干净环境里照 `requirements.txt` 装一遍，Windows 和 Linux 各跑一次端到端。

---

## 需求落在哪个模块

FR 编号沿用 SRS 第 8 章，和《设计流程》3.2 的需求清单对得上。

| 需求 | 功能 | 位置 | 优先级 |
|---|---|---|---|
| FR1 | 评价码校验进入，无效码、已用码拒绝 | `business/submission/` + `data/` | 必须 |
| FR2 | 三个维度各打 1–5 分，写进匿名评价表 | `business/submission/` + `data/` | 必须 |
| FR3 | 开放题选填，≤500 字，原文不外发 | `business/submission/` | 应该 |
| FR4 | 均分、评分分布、维度对比 | `business/stats/` + `business/privacy/` | 必须 |
| FR5 | n < k 时拒绝出数 | `business/privacy/` 的 `ThresholdGate` | 必须 |
| FR6 | 按查询扣预算，耗尽后拒绝 | `business/privacy/` 的 `BudgetLedger` | 必须 |
| FR7 | 管理员配 ε、k、ε_total，即时生效 | `business/config/` | 必须 |
| FR8 | 开放题词频，不显示原文 | `business/stats/` 的 `word_freq` | 应该 |
| FR9 | 审计日志查看与筛选 | `business/audit/` | 应该 |
| FR10 | 导出 PDF / CSV，数值跟看板一致 | `business/export/` | 可以 |

NFR 里能落到具体写法的几条：

| 需求 | 写代码时要满足什么 |
|---|---|
| NFR1 完整性 / 安全性 | 两个库分开；接口层任何地方都不返回开放题原文 |
| NFR2 正确性 | Laplace 采样跟定义一致；输出截断到 [1,5] |
| NFR3 易用性 | 学生三步内提交完 |
| NFR4 效率 | 1 万条记录下聚合查询 < 2 s，用 `scripts/` 造数据后计时 |
| NFR5 可测试性 | 隐私和统计模块脱离 Web 层能测，覆盖率 ≥ 90% |
| NFR6 可维护性 | 改一次 ε 策略，动的文件数 ≤ 2 |
| NFR7 可移植性 | 按 `requirements.txt` 装完，两个平台都能跑 |

---

## 施工顺序

按 SRS 1.6 的优先级（必须 / 应该 / 可以）排，思路是《设计流程》4.4 那句：
先把「提交 → 聚合 → 发布」这条最小闭环纵向打通，再横向补管理和审计。
每个阶段先把测试写完再进下一个。

### 必须项

不实现就没有系统，也兑现不了隐私承诺。

| 序 | 阶段 | 做什么 | 需求 | 怎么算完成 |
|---|---|---|---|---|
| P0 | 工程底座 | 应用工厂、`config.py`、数据访问层、8 张表建表脚本 | NFR6、NFR7 | 空库能建表，表结构核对通过 |
| P1 | 隐私核心 | `PrivacyMechanism`（Laplace 采样、敏感度表）、`ThresholdGate`、`BudgetLedger` | FR5、FR6、NFR2、NFR5 | TC-P1 至 TC-P4 全过 |
| P2 | 评价提交 | 评价码校验、维度校验、同事务写库并作废码 | FR1、FR2、NFR1 | 无效码、已用码、越界值都被拒；TC-I3 过 |
| P3 | 聚合发布 | 真实统计量 → 双重闸门 → 加噪 → 截断 → 扣预算 → 留痕 | FR4、FR5、FR6 | 返回加噪值、样本量 n 和剩余预算；拒绝路径也对 |
| P4 | 参数配置 | 配 ε、k、ε_total，校验后即时生效 | FR7 | 非法值拒绝；改完新查询确实用新参数 |
| P5 | 表现层贯通 | 学生端两个页面、教师端看板 | FR1–FR4、NFR3 | TC-E1 端到端跑通 |

### 应该项

| 序 | 阶段 | 做什么 | 需求 |
|---|---|---|---|
| P6 | 开放题词频 | 中文词频聚合，只出高频词 | FR3、FR8 |
| P7 | 审计与留痕 | 查询留痕，按时间和课程筛选，日志只增不改 | FR9 |

### 可以项

| 序 | 阶段 | 做什么 | 需求 |
|---|---|---|---|
| P8 | 结果导出 | 导出 PDF / CSV，导出也留痕 | FR10 |
| P9 | 非功能验证 | 1 万条计时、ε 对比实验 TC-P5、双平台运行、覆盖率报告 | NFR4、NFR5、NFR7 |
| P10 | 交付文档 | 设计文档、测试报告、使用手册 | 《设计流程》7.3 |

---

## 几个还没定的问题

1. `requirements.txt` 还没建，内容大概是 `Flask` 加测试用的 `pytest`、`pytest-cov`。
   本机这两个都没装，pip 是 26.0.1，第一步就把这件事做掉。
2. ε 和 ε_total 的默认值：SRS 附件C 的 Q1 还挂着「待调研确定」，
   《设计流程》5.1 给的是 ε=0.5、单次查询 ε_cost=0.1。先按设计文档的取值写进配置，
   注释里标明出处，等调研结果出来再改。
3. 维度定名和数量：附件C 的 Q3 没定，先按「教学内容 / 教学方法 / 考核方式」三个做。
4. 表名以 SRS 为准：SRS 第 6 章写的是 `dimension` 和 `audit_log`，
   《设计流程》5.4 写的是 `dim` 和 `audit`，两处不一致，实现跟 SRS 走。
5. 仓库根的 `.gitignore` 是 `**/assets/*`，`assets/`、`class1/assets/`、`class2/assets/` 都被它忽略掉，
   包括两个实验的交付文档。目前只有 `project/` 是未跟踪、可以入库的。
   这个目录下还有一层自己的 `.gitignore`，挡掉 `*.db`、`__pycache__`、导出产物和实验中间结果。
