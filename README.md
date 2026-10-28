# 软件工程实验 · TACES

TACES（Trusted Anonymous Course Evaluation System）是本仓库的课程项目：学生凭一次性评价码匿名评教，教师读取受样本门槛、差分隐私噪声与发布预算约束的统计结果。

实现采用 Python 3.12+、Flask 和 SQLite。源码、页面、共享测试和测试数据工具位于 [`project/`](project/README.md)。Flask 页面默认连接真实后端；管理员可管理课程和发放评价码，教师可查看统计并导出已发布快照，教职工可修改本人密码。

## 本机运行

配置好 Python 和项目依赖后，从仓库根目录执行：

```bash
cd project
python run.py
```

首次使用需要初始化数据库，或生成并安装合成演示数据。具体命令、账号和测试方法见 [项目说明](project/README.md) 与 [测试数据工具说明](project/scripts/README.md)。

## 仓库内容

- `class1/hello_world.py`：实验1的环境验证代码。
- `project/src/`：正式应用、模板、静态资源和 SQL 结构。
- `project/tests/`、`project/scripts/`：共享测试与可复现的数据生成/校验工具。
- `project/docs/`：当前架构、认证、接口契约和前端说明。
- `project/pyproject.toml`、`project/requirements.txt`：依赖声明和兼容安装清单。

课程原始资料与手工交付文档、AI 工作上下文、历史实施计划及旧静态原型仅在本地保留。数据库、备份、生成的数据清单、测试报告、虚拟环境、uv.lock和缓存不提交。忽略规则不会删除这些本地文件。
