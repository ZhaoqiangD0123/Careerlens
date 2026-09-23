# CareerLens

CareerLens 是一个面向 AI 求职研究的学习型项目。项目将逐步实现招聘岗位数据的导入、校验、筛选、统计和 AI 辅助分析，用真实项目练习 Python 工程、测试、后端和 AI 应用开发。

## 当前进度

目前可以校验和过滤岗位数据，并通过命令行展示、搜索、筛选和统计合法岗位。

`validate_job(job)` 接收字典或其他映射对象，并检查以下必填字段：

| 字段 | 含义 | 规则 |
|---|---|---|
| `title` | 岗位名称 | 非空字符串 |
| `city` | 工作城市 | 非空字符串 |
| `description` | 岗位描述 | 非空字符串 |
| `source_url` | 信息来源 | 非空的 HTTP/HTTPS 地址 |

校验成功时，函数返回去除字段首尾空格的新字典，不修改原始输入。校验失败时抛出 `JobValidationError`，错误信息会指出有问题的字段。

## 项目结构

```text
careerlens/
├─ src/careerlens/
│  ├─ __init__.py
│  ├─ catalog.py
│  ├─ explore_jobs.py
│  ├─ filter_jobs.py
│  ├─ validator.py
│  └─ validate_file.py
├─ tests/
│  ├─ test_catalog.py
│  ├─ test_filter_jobs.py
│  ├─ test_validator.py
│  └─ test_validate_file.py
├─ data/
│  ├─ invalid_jobs.json
│  ├─ jobs.json
│  ├─ sample_job.json
│  └─ valid_jobs.json
├─ pyproject.toml
├─ uv.lock
└─ README.md
```

## 环境要求

- Python 3.12 或更高版本
- uv

## 安装与同步

克隆仓库后，在项目根目录执行：

```powershell
uv sync --group dev
```

该命令会根据 `pyproject.toml` 和 `uv.lock` 创建或同步虚拟环境，并安装测试依赖。

## 运行测试

```powershell
uv run pytest -v
```

pytest 会自动查找 `tests/` 中以 `test_` 开头的测试函数。目前测试覆盖：

- 有效岗位数据的清理和返回；
- 原始输入不会被修改；
- 缺少必填字段；
- 字段内容无效；
- 非 HTTP/HTTPS 来源链接。

## 校验 JSON 文件

使用项目中的示例数据运行：

```powershell
uv run python -m careerlens.validate_file data/sample_job.json
```

成功时会输出清理后的岗位数据。文件不存在、JSON 语法错误或岗位字段不符合契约时，程序会输出具体原因并返回失败退出码。

## 批量过滤岗位数据

`data/jobs.json` 包含 20 条演示数据，其中 11 条符合规则、9 条故意包含缺字段、错误类型、空内容或非法链接。

运行批量过滤：

```powershell
uv run python -m careerlens.filter_jobs data/jobs.json
```

命令会生成：

- `data/valid_jobs.json`：清理后的合法岗位；
- `data/invalid_jobs.json`：非法岗位的原始序号、错误原因和原始数据。

程序不会静默丢弃错误数据，因此可以根据错误报告追查数据质量问题。

## 展示、搜索和筛选

以下命令都使用过滤后的 `data/valid_jobs.json`：

```powershell
# 展示全部岗位
uv run python -m careerlens.explore_jobs data/valid_jobs.json list

# 在岗位名称、城市和描述中搜索
uv run python -m careerlens.explore_jobs data/valid_jobs.json search AI

# 按城市精确筛选
uv run python -m careerlens.explore_jobs data/valid_jobs.json filter --city 杭州

# 同时按城市和岗位名称筛选
uv run python -m careerlens.explore_jobs data/valid_jobs.json filter --city 西安 --title Python
```

## 词频统计

```powershell
uv run python -m careerlens.explore_jobs data/valid_jobs.json stats
```

统计包含城市分布、岗位关键词频次和技能关键词频次。V0 使用代码中明确列出的关键词进行匹配；同一关键词在同一岗位中重复出现时只计算一次。

## 使用示例

```python
from careerlens.validator import validate_job

job = {
    "title": " Python 开发工程师 ",
    "city": " 西安 ",
    "description": " 开发 AI 应用 ",
    "source_url": " https://example.com/jobs/1 ",
}

cleaned_job = validate_job(job)
print(cleaned_job)
```

输出：

```python
{
    "title": "Python 开发工程师",
    "city": "西安",
    "description": "开发 AI 应用",
    "source_url": "https://example.com/jobs/1",
}
```

## 当前限制

- `source_url` 只检查协议和基本结构，不访问网络，也不保证页面真实存在。
- 当前批量文件必须以 JSON 数组作为最外层结构。
- 岗位和技能词频使用预定义关键词匹配，还没有中文分词、同义词归并和 AI 信息抽取。

## 后续计划

1. 导出 Markdown 分析报告。
2. 扩充岗位字段和真实样本数据。
3. 为搜索增加排序和组合条件。
