# TACES 测试数据与本机演示

以下命令均以 `project/` 为当前目录，不增加依赖。

```powershell
# 生成、自动验证，然后备份并替换本机 db/（先停止正在运行的演示服务）
uv run --locked python scripts/generate_test_data.py --check --install-demo

# 仅生成独立数据，不替换 db/
uv run --locked python scripts/generate_test_data.py --output tests/experiments/output/second --check

# 原数据不动，在临时副本中重新验证；失败退出码为 1
uv run --locked python scripts/generate_test_data.py --verify-only tests/experiments/output/testdata

# 小规模快速生成；0 表示不生成性能课程
uv run --locked python scripts/generate_test_data.py --output tests/experiments/output/small --performance-rows 0 --seed 42 --check
```

默认产物在 `tests/experiments/output/testdata/`，已被现有规则忽略，不提交数据库、密码、评价码或报告。目标目录必须不存在，重复执行会报错；重新生成时使用新的 `--output`。中途失败可能保留不完整目录，只有最后写出 `manifest.json` 才算生成完毕。

`--install-demo` 必须先通过自动验证，再将三库复制到 `db/`；已有三库通过 SQLite 备份接口保存至 `tests/experiments/output/backups/before-demo-*/`。备份失败则不替换，替换中失败则恢复已有三库。拒绝替换缺文件的残缺数据库。该操作面向已停止服务的本机演示，不支持在线替库。恢复时先停止服务，将备份目录中的三个 `.db` 文件一并复制回 `db/`。

## 演示账号和评价码

| 用途 | 用户名 | 密码 |
| --- | --- | --- |
| 管理员 | `demo_admin` | `Taces-demo-2026!` |
| 教师 | `demo_teacher` | 同上 |
| 另一位教师 | `demo_other` | 同上 |
| 审计员 | `demo_auditor` | 同上 |
| 停用账号，登录预期失败 | `demo_disabled` | 同上 |

学生不登录。可用于学生演示的评价码在 `manifest.json` 的 `codes.student_demo`，属于 `at_k` 课程；提交后可演示从 5 份到 6 份、新版本重新发布。`codes.valid` 属于专门验证非法请求的空课程，`codes.submit` 的 5 枚码用于从零开始演示有效提交。

```powershell
(Get-Content tests/experiments/output/testdata/manifest.json -Raw | ConvertFrom-Json).codes.student_demo
uv run --locked python run.py
```

现有前端 `src/taces/presentation/static/js/api.js` 的 `USE_MOCK` 仍为 `true`。本工具生成、安装和验证真实后端数据；页面沿用原有 Mock 时不会读取这些数据库。数据工具不修改前端文件。

## 覆盖范围

默认 25 门合成课程，每门默认 3 个评价维度；性能课默认 10,000 份、30,000 行评分。

| 场景 | 课程/数据 | 核对内容 |
| --- | --- | --- |
| 样本闸门 | `empty/below_k/at_k/above_k`：0、4、5、6 份，k=5 | 前两者不发布，后两者可发布，拒绝不扣预算 |
| 评分分布 | `all_low/all_high/uniform/polarized/random` | 全1、全5、五档均匀、两极分化、固定种子的偏高分样本；核对精确聚合和发布后范围 |
| 维度与权重 | `weighted/one_dimension/ten_dimensions` | 0.7/0.2/0.1 权重、1 维、10 维，完整提交与加权统计 |
| 开放题 | `text_empty/text_500/text_special` | 不填、500/501 字、空白、中文、Emoji、换行、引号、脚本/SQL/公式字面值；重复词每份限一次，最多贡献3个词 |
| 评价码 | 有效、已用、过期、窗口关闭、不存在、格式错误、大小写 | 校验结果、重复提交拒绝，非法评分/文本不消耗码 |
| 预算 | `budget_empty/budget_last` | 无缓存耗尽、恰够最后一次；预算以整数微单位核对 |
| 缓存 | `cache_exhausted/stale_cache/refresh` | 耗尽仍读缓存、数据变化后回退旧快照、可用预算下发布新版本；连续读10次不重采样/不扣费 |
| 权限 | 两位教师、管理员、审计员、停用账号、匿名 | 越权课程/导出/配置/审计、未登录、CSRF 缺失、跨来源、错误密码、5次失败后限流 |
| 配置 | ε=0.01/1、k=3/50、总预算4/20 | 合法边界回读、非法类型/范围/精度/未知键、策略版本改变、预算低于已花费金额时回滚 |
| 审计 | 课程过滤、limit/offset 分页 | 审计员可独立拿到课程列表；非法日期、逆序范围、重复参数拒绝 |
| 导出 | CSV / PDF | 发布编号、CSV数值复用看板快照；PDF可解析且包含相同发布编号；旧快照可导出；原文不外发且不扣预算 |
| 性能 | `performance`，可用 `--performance-rows` 调整 | 原始聚合 <2秒、首次完整HTTP发布 <5秒；报告实测秒数，机器负载会影响结果 |
| 库约束 | 物理分离的身份/评价/元数据库 | SQLite完整性和外键、完整维度、已用码数/数据版本/份数一致、无学生数据、无预置登录会话 |

`budget_empty` 是直接设置账本的边界夹具，不代表完整历史发布流程；常规课程与账号使用真实业务服务创建，大量评分通过事务批量插入。缓存场景使用真实统计服务发布，并通过真实提交服务推进数据版本。所有内容均为合成数据，不对应真实学生或真实评语。

## 产物与判定

- `db/{metadata,identity,evaluation}.db`：可直接运行的当前版本三库。
- `manifest.json`：课程及首次读取的预期状态、账号、评价码、30天窗口截止时间。
- `ground_truth.json`：精确均值、加权均分、五档分布、文本份数/长度、限贡献词频，仅供本地测试。
- `api_cases.json`：按顺序回放的请求体、角色、状态码和字段断言，包括非法请求与有效提交。
- `verification.json`：`--check` 或 `--verify-only` 输出的逐项结果和性能时间。失败退出码为1。

验证器先将三库复制到临时目录，再走真实 Flask 路由与鉴权；不会消耗生成库或演示库中的评价码，也不会改变其预算。先通过SQL与真实聚合服务分别核对精确真值，再验证发布、请求语料、导出和配置生命周期。接口经过真正的路由处理，但验证器不启动网络服务；网络闭环由已有系统测试覆盖。

`--seed` 仅保证相同规模下评分/文本与精确聚合可复现。评价码、随机ID、密码盐、时间和隐私噪声继续使用真实随机性，因此数据库文件和发布值不会逐字节相同；验证不把加噪值与真实均值直接判等。窗口到期后需要重新生成，不能一直复用过期评价码。

工具自身的回归测试：

```powershell
uv run --locked python -m pytest -q tests/integration/test_test_data.py
```
