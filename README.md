# CareerLens

CareerLens 是一个面向 AI 求职研究的学习型项目。项目将逐步实现招聘岗位数据的导入、校验、筛选、统计和 AI 辅助分析，用真实项目练习 Python 工程、测试、后端和 AI 应用开发。

## 当前进度

目前完成了第一项能力：校验并清理单条招聘岗位数据。

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
│  └─ validator.py
├─ tests/
│  └─ test_validator.py
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
- 当前只处理单条岗位数据，尚未实现文件导入、搜索、筛选和统计。
- 当前没有命令行交互入口。

## 后续计划

1. 从 JSON 文件导入多条岗位数据。
2. 增加岗位列表展示、搜索和筛选。
3. 统计城市、岗位和技能词频。
4. 导出 Markdown 分析报告。
