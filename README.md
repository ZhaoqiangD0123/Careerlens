# CareerLens

CareerLens 是一个面向 AI 求职研究的学习型项目。项目将逐步实现招聘岗位数据的导入、校验、筛选、统计和 AI 辅助分析，用真实项目练习 Python 工程、测试、后端和 AI 应用开发。

## 当前进度

目前可以校验、清洗、过滤和去重岗位数据，并通过命令行展示、搜索、筛选、统计和导出 Markdown 报告。FastAPI 的 `GET /jobs` 支持可选 city 和 keyword 查询参数；`POST /jobs/validate` 接收单条 JSON 并返回清洗结果，只校验，不保存岗位。

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
│  ├─ api.py
│  ├─ catalog.py
│  ├─ deduplicate_jobs.py
│  ├─ export_report.py
│  ├─ explore_jobs.py
│  ├─ filter_jobs.py
│  ├─ job_files.py
│  ├─ validator.py
│  └─ validate_file.py
├─ tests/
│  ├─ test_api.py
│  ├─ test_catalog.py
│  ├─ test_deduplicate_jobs.py
│  ├─ test_demo_dataset.py
│  ├─ test_export_report.py
│  ├─ test_filter_jobs.py
│  ├─ test_validator.py
│  └─ test_validate_file.py
├─ data/
│  ├─ README.md
│  ├─ deduplicated_jobs.json
│  ├─ duplicate_jobs.json
│  ├─ invalid_jobs.json
│  ├─ jobs.json
│  ├─ sample_job.json
│  └─ valid_jobs.json
├─ reports/
│  └─ job-market-summary.md
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
- HTTP 岗位查询的正常、空数据、数据源失败、只读行为和每次请求重新读取；
- 路由不存在、请求方法错误和接口文档。
- 城市与关键词筛选、组合条件、空白参数、具体结果与筛选后数量；
- 原始演示数据与清洗、去重派生文件的一致性。
- 请求体结构、严格字符串类型、业务校验、额外字段忽略，以及校验成功或失败都不改写岗位库。

## 启动 HTTP 服务

在项目根目录（包含 `pyproject.toml` 和 `data/` 的目录）执行：

```powershell
uv sync --group dev
uv run uvicorn careerlens.api:app --host 127.0.0.1 --port 8000 --reload
```

终端保持运行，按 `Ctrl+C` 停止。`careerlens.api:app` 指定模块及应用对象；Uvicorn 监听本机 8000 端口，FastAPI 按请求方法与路径调用处理函数。`--reload` 仅用于开发，代码修改后自动重启。

- 岗位列表：`http://127.0.0.1:8000/jobs`
- 交互式接口文档：`http://127.0.0.1:8000/docs`
- OpenAPI 接口描述：`http://127.0.0.1:8000/openapi.json`

### GET /jobs 契约与数据流

客户端 → Uvicorn → FastAPI 解析 city/keyword → `job_files.load_validated_jobs` → `catalog.filter_jobs` → `catalog.search_jobs` → JSON 响应。

数据源固定为启动目录下的 `data/deduplicated_jobs.json`。服务每次请求读取并校验文件，不接受客户端指定本机文件路径，不写文件、不重新去重，也不生成报告。数据应提前由已有过滤、去重命令生成；报告导出本身不会保存中间 JSON 文件。

| 场景 | 状态码与结果 |
| --- | --- |
| 正常读取 | 200，`{"total": 83, "items": [...]}`；无参数时返回全部，筛选后 total 为匹配数量 |
| 文件内容为 `[]` | 200，`{"total": 0, "items": []}` |
| 文件缺失、无法读取、JSON 损坏或含非法岗位 | 500，`{"detail": "岗位数据暂时不可用，请检查服务端数据文件"}` |
| 请求未知路径 | 404 |
| 使用 POST 请求 `/jobs` | 405，方法不允许 |

`items` 中每个岗位包含 `title`、`city`、`description` 和 `source_url`。遇到非法岗位时不会静默过滤后返回部分成功数据。详细错误写入服务端日志，响应不暴露本机文件路径。服务未启动时是连接失败，通常没有 HTTP 状态码。

### 城市和关键词查询

| 参数 | 规则 |
| --- | --- |
| city | 城市精确匹配，去首尾空格，英文不区分大小写 |
| keyword | 对岗位名称、城市、描述的拼接文本做包含搜索，去首尾空格，英文不区分大小写 |

两个参数均可选，不传、空字符串或仅空白时不限制对应条件。组合条件是 AND，必须同时满足；返回顺序沿用文件顺序。无匹配是 200 空列表，不是 404。查询仍读取完整文件后在内存筛选，不包含分页、数据库或智能语义搜索。

```text
GET /jobs?city=杭州
GET /jobs?keyword=FastAPI
GET /jobs?city=杭州&keyword=FastAPI
```

中文 URL 仅作易读展示，可以在 Apifox Params 中填写并由客户端编码。响应 total 始终等于当前 items 的长度，不固定为全库数量。

### POST /jobs/validate：校验请求体

Body 发送单条 JSON 对象，Content-Type 为 `application/json`：

```json
{
  "title": " Python 后端工程师 ",
  "city": " 杭州 ",
  "description": " 使用 FastAPI 开发岗位服务 ",
  "source_url": " https://example.com/jobs/body-demo "
}
```

成功返回 200，响应直接为清洗后的四字段岗位对象，没有 `total/items`。四个字段必填，且必须为字符串；字段首尾空格清理后不能为空，URL 沿用 `validate_job` 规则。额外字段忽略、不返回。

数据流：Apifox Body → FastAPI 解析 JSON → `JobValidationRequest` 检查结构与严格字符串类型 → `validate_job` 校验并清洗 → `JobResponse`。

| 输入失败 | 状态码与 detail |
| --- | --- |
| 缺字段、错误类型、无请求体、错误 JSON、不是对象 | 422，detail 为框架错误列表 |
| 空白字段或非法 URL | 422，detail 为业务错误说明字符串 |

校验不读取或改写任何岗位文件，不入库、不去重、不增加 GET /jobs 数量。即使岗位库不存在也可以校验收到的 JSON。POST 不代表一定保存；本接口未创建资源，因此成功为 200 而非 201。原 POST /jobs 仍返回 405。

### 使用 Apifox 调试

保持服务终端运行，在电脑上的 Apifox 中创建 HTTP 请求：

- 方法：`GET`；
- URL：`http://127.0.0.1:8000/jobs`；
- 获取全部岗位时无需 Params；筛选时在 Params 填写 city、keyword，无需请求体或认证；
- 发送后核对状态码 200、响应的 `total` 与 `items` 数量是否一致；
- 用 `/unknown` 对比 404，再把 `/jobs` 方法改为 POST 对比 405。

Apifox 是客户端，不负责启动 Python 服务。接口自动化测试仍通过 `uv run pytest -v` 运行；TestClient 在进程内调用应用，不需要先启动 Uvicorn。当前 Starlette 测试客户端使用 `httpx2`，因此将它列为开发依赖，见 [官方 TestClient 文档](https://www.starlette.io/testclient/)。

已提供 [可导入 Apifox 的请求集合](docs/careerlens.postman_collection.json) 和 [导入指南](docs/apifox-guide.md)，包含用户新增的根路径、岗位列表以及 404/405 请求，并附响应断言。集合采用 Postman 格式，不需要安装 Postman；在 Apifox 中导入后核对本机环境与后置脚本。导入文件不会新增 Python 接口。

另外提供 [查询参数练习集合](docs/careerlens.query.postman_collection.json)，涵盖仅城市、仅关键词、AND、无匹配和空白。建议导入到单独目录，避免覆盖原有请求；同一方法与路径在导入后可能以用例形式呈现，需核对各用例的 Params 和脚本。也可在已导入的 GET /jobs 请求上手动填写条件。

新增 [请求体校验练习集合](docs/careerlens.validation.postman_collection.json)，包含九个 POST /jobs/validate 用例，覆盖清洗成功、缺字段、类型错误、空白字段、FTP 地址、数组、错误 JSON、无请求体和额外字段。请在 Body 而不是 Params 中填写岗位；422 用例是预期输入失败。集合后置脚本已在本地 pm 兼容环境针对真实 HTTP 响应验证，实际 Apifox 导入仍需用户核对。

第一版仅供本机学习：无认证、分页或缓存，不应直接暴露到公网。同步文件读取使用普通 `def` 路由，框架将其放在线程池中执行，见 [FastAPI 同步与异步说明](https://fastapi.tiangolo.com/async/)。

## 校验 JSON 文件

使用项目中的示例数据运行：

```powershell
uv run python -m careerlens.validate_file data/sample_job.json
```

成功时会输出清理后的岗位数据。文件不存在、JSON 语法错误或岗位字段不符合契约时，程序会输出具体原因并返回失败退出码。

## 批量过滤岗位数据

`data/jobs.json` 当前包含 100 条合成演示记录：89 条符合规则（含重复）、11 条无效；清洗后按来源去重得到 83 条唯一岗位。已保留原有错误样例，并增加多城市、多岗位和更完整的职责、技能描述。详情见 [数据集说明](data/README.md)。这些并非真实招聘信息，不能用于推断市场分布。

运行批量过滤：

```powershell
uv run python -m careerlens.filter_jobs data/jobs.json
```

命令会生成：

- `data/valid_jobs.json`：清理后的合法岗位；
- `data/invalid_jobs.json`：非法岗位的原始序号、错误原因和原始数据。

程序不会静默丢弃错误数据，因此可以根据错误报告追查数据质量问题。

## 按来源链接去重

去重功能只接受已经通过校验和清洗的岗位数据。请先运行批量过滤，再执行：

```powershell
uv run python -m careerlens.deduplicate_jobs data/valid_jobs.json
```

命令以 `source_url` 精确匹配作为重复判断标准，并保留每个链接第一次出现的岗位。它会生成：

- `data/deduplicated_jobs.json`：去重后的岗位；
- `data/duplicate_jobs.json`：重复数据的原始序号、首次出现序号和岗位内容。

如果输入数据未通过校验，或字段仍有需要清理的首尾空格，去重会停止并提示先完成清洗。

## 展示、搜索和筛选

以下命令使用清洗并去重后的 `data/deduplicated_jobs.json`：

```powershell
# 展示全部岗位
uv run python -m careerlens.explore_jobs data/deduplicated_jobs.json list

# 在岗位名称、城市和描述中搜索
uv run python -m careerlens.explore_jobs data/deduplicated_jobs.json search AI

# 按城市精确筛选
uv run python -m careerlens.explore_jobs data/deduplicated_jobs.json filter --city 杭州

# 同时按城市和岗位名称筛选
uv run python -m careerlens.explore_jobs data/deduplicated_jobs.json filter --city 西安 --title Python
```

## 词频统计

```powershell
uv run python -m careerlens.explore_jobs data/deduplicated_jobs.json stats
```

统计包含城市分布、岗位关键词频次和技能关键词频次。V0 使用代码中明确列出的关键词进行匹配；同一关键词在同一岗位中重复出现时只计算一次。

## 导出 Markdown 报告

报告导出命令直接读取原始岗位数据，自动完成校验、清洗、无效数据过滤、按 `source_url` 去重和统计。报告包含处理概况、岗位总数、城市分布、常见技能和岗位列表。运行：

```powershell
uv run python -m careerlens.export_report data/jobs.json
```

默认生成 `reports/job-market-summary.md`，也可以通过 `--output` 指定路径。无效和重复岗位不会进入最终统计；报告会记录各阶段数量。报告输出路径不能与原始 JSON 路径相同。单独的过滤、去重和查询命令仍可用于检查中间结果。

当前功能完成情况、学习验收状态和后续任务见 [学习进度与下一步](docs/learning-progress.md)。

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
- 去重采用清洗后的 `source_url` 精确匹配，暂未合并带跟踪参数、不同大小写或不同尾部斜杠的等价链接。
- 岗位和技能词频使用预定义关键词匹配，还没有中文分词、同义词归并和 AI 信息抽取。

## 后续计划

1. 扩充岗位字段和真实样本数据。
2. 为搜索增加排序和组合条件。
3. 体验请求体与参数校验，再接入 SQL/PostgreSQL。
