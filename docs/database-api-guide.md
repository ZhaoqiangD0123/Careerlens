# HTTP 查询接入 PostgreSQL：运行与验收

2026-10-07：默认 `GET /jobs` 已改为查询数据库。它不再读取 JSON；显式文件模式只保留给测试。`POST /jobs/validate` 和你新增的首页保持原样，不连接或写入数据库。

## 本次改了什么

| 文件 | 职责与变化 |
| --- | --- |
| `src/careerlens/api.py` | 列表路由通过 `Depends(get_job_page)` 验证参数并查询分页；不合法参数先返回 422；转换 500/503 |
| `src/careerlens/job_repository.py` | `query_database_jobs` 使用 SQL 筛选、COUNT 和分页，只校验当前页；全量函数保留给其他用途 |
| `src/careerlens/database.py` | 复用已有配置/身份检查/超时，没有另写连接机制 |
| `tests/test_api_database.py` | 普通回归：配置、读取调用、错误脱敏、规则复用、查询边界 |
| `tests/conftest.py`、数据库集成测试与测试脚本 | 共享隔离库，验证实际 PostgreSQL 与 HTTP，不使用练习表 |

数据流：Apifox → Uvicorn → FastAPI 查询参数验证 → query_database_jobs → psycopg → PostgreSQL WHERE / COUNT / ORDER BY / LIMIT / OFFSET → 当前页校验 → total/items/limit/offset JSON。

数据库驱动只负责 SQL 与行；HTTP 层负责请求响应；catalog 继续负责 CLI 与显式文件测试模式的筛选，不参与默认 HTTP 数据库查询。单条岗位四字段不变，列表外层新增 limit/offset，total 是分页前匹配总数，id 暂只作为排序依据。每次请求使用独立连接并在返回前关闭，不缓存第一次数据，不共享全局连接。

## 在本机启动

前提：Docker Desktop 已运行，`careerlens-postgres-learning` 练习容器运行，已有 `public.jobs` 与导入后的岗位。不要重复建表或清空数据。默认地址 `127.0.0.1:5433`、库 `careerlens_learning`、用户 `careerlens`；非默认情况按 [导入指南](database-import-guide.md) 设置进程变量。

在项目根目录同步依赖：

```powershell
uv sync --group dev
```

### 使用本机 .env 配置

2026-10-07：本机配置统一放在项目根目录 `.env`（与 `pyproject.toml` 同级）。用户已在本机填写并报告按下方命令启动后数据库查询成功；真实值不记入本文。其他人首次克隆时可把无密码的 `.env.example` 复制为 `.env`，自行填写；不能覆盖已有本机配置。

文件包含数据库地址、端口、库名、用户名和 `CAREERLENS_DB_PASSWORD`。密码建议放在双引号内；含引号、反斜杠等特殊字符时须遵循 dotenv 格式，不把整个连接字符串或 Python 代码填到密码处。

在项目根目录启动：

```powershell
# uv 将文件内容加载到它启动的子进程环境，不在命令行传递真实密码。
uv run --env-file .env uvicorn careerlens.api:app --host 127.0.0.1 --port 8000 --reload
```

加载流程：`.env` → uv 子进程环境变量 → `DatabaseConfig.from_env()` → psycopg 连接。现有 Python 读取逻辑无需另加 dotenv 依赖；未带 `--env-file` 的旧启动方式不应被认为会自动加载该文件。参见 [uv 环境文件说明](https://docs.astral.sh/uv/concepts/configuration-files/#environment-variable-files)。

已有同名环境变量优先于 `.env`，如果之前终端设置过旧密码或端口，建议使用没有这些旧变量的新终端。修改 `.env` 后先 Ctrl+C 停止，再执行上述命令完整重启；热重载不保证重新加载环境文件。若旧服务仍占用 8000，先在它自己的终端停止，不强制结束未知进程。

`.env` 是明文且只保留本机，Git 忽略规则覆盖 `.env` 和 `.env.*`，仅 `.env.example` 例外。`.gitignore` 本身不是密码存储文件；若秘密曾经提交或推送，删除注释不能消除历史泄漏，应更换秘密。不要将真实配置加入 Git。生产环境后续采用部署环境变量或秘密管理，不承诺这个文件是生产安全方案。

HTTP 请求期间不会弹密码提示；密码为空、配置缺失或认证失败时 `/jobs` 返回 503，但首页和校验路由仍可用。用户已确认正常启动查询；这不自动证明所有 Apifox 用例、故障实验、代码审查或设计解释均已完成。

### 环境配置协作约定

- 环境相关的数据库/外部服务地址、端口、超时、模型名称和确实需要的凭据统一通过环境变量读取，本机值集中在 `.env`；业务常量与固定规则不一概配置化。现有固定超时不因本次归档擅自改写，后续有相关需求时再增加配置。
- 新增配置同时更新 `.env.example` 的中文注释，说明用途、默认值/必填性、单位和取值限制。模板只用安全默认值或空占位，不复制真实秘密。
- 修改 `.env` 仅新增必要字段，保留用户已有值；不输出、记录或提交密码/令牌。当前配置读取由 `DatabaseConfig.from_env()` 承担，不新增自动加载逻辑。
- 已有环境变量优先；项目运行显式 `--env-file .env`，配置变化完整重启。没有该参数（或明确的 `UV_ENV_FILE` 等外部设置）时，不假定 uv 自动发现 `.env`。
- 尚未使用的外部服务不预配无用字段。AI 接入遵守既有账号授权偏好，不擅自改为强制 API Key。
- 不将秘密硬编码，或暴露到日志、异常、测试报告与学习笔记。生产使用部署环境变量或秘密管理，不把本机明文文件当作生产安全方案。
- 移除 `.gitignore` 中的旧密码注释不等于清理 Git 历史或撤销泄漏；此次没有清理历史、提交推送或更换数据库密码。

## Apifox：复用原请求

使用已有查询集合与 `baseUrl=http://127.0.0.1:8000`，无需重新创建接口。以下数量仅适用于当前 83 条合成数据尚未修改：

| 请求 | 核对 |
| --- | --- |
| GET /jobs | 200，total=83，items 长度 20，limit=20、offset=0；单条四字段 |
| GET /jobs?city=杭州 | 200，17 条，每条城市都是杭州 |
| GET /jobs?keyword=FastAPI | 200，13 条，匹配名称/城市/描述 |
| GET /jobs?city=杭州&keyword=FastAPI | 200，3 条，同时满足两条件 |
| GET /jobs?city=不存在的城市 | 200，total=0、items=[] |
| POST /jobs/validate（合法 Body） | 200，清洗对象；调用前后列表不增加 |

不要只看数量一样就认定来自数据库；调用路径由代码审查与真实隔离库测试验证，也可只读对照 SQL 数据。API 不导出 Markdown、不重新清洗写库、不创建岗位。

## 一个安全的故障实验

无需停止容器、删除 JSON 或改密码。在另一个**没有数据库密码变量的新终端**运行：

```powershell
# 8001 上的服务故意缺配置，不影响正在使用的 8000 服务或数据库。
uv run --no-env-file uvicorn careerlens.api:app --host 127.0.0.1 --port 8001
```

在 Apifox 新建单独调试请求，使用 `http://127.0.0.1:8001`（不要覆盖原正常环境）：

- GET /jobs：503，`detail` 为“岗位数据库暂时不可用，请检查服务端配置与数据库连接”。旧 JSON 存在也不回退。
- GET /：200，仍为你的 Hello World。
- POST /jobs/validate，合法 JSON：200；错误 Body：422。

对 503 请求的后置脚本可以写：

```javascript
// 这是预期失败场景，收到 503 才代表测试通过；不是统一期待 200。
pm.test("缺配置时返回 503", function () {
    pm.expect(pm.response.code).to.eql(503);
});
pm.test("不伪装成空岗位列表", function () {
    const data = pm.response.json();
    pm.expect(data.detail).to.eql("岗位数据库暂时不可用，请检查服务端配置与数据库连接");
    pm.expect(Object.prototype.hasOwnProperty.call(data, "items")).to.eql(false);
});
```

运行后 Ctrl+C 停止 8001 服务。若新终端继承了你另设的长期密码变量，先核对配置，不在共享环境中随意清除它；普通 pytest 已覆盖缺配置场景。

## 错误如何区分

- 200 空数组：无匹配、空库或 offset 超过匹配数；后者 total 不归零。
- 503：配置不合法/缺失、连接或认证失败、连接中断、查询/锁等待超时。日志只记录固定错误类别，不记录密码或驱动原文。
- 500：缺表、错误列/SQL、当前页的行格式错误、非法岗位或未清洗记录；不把合法部分返回成成功。
- 422：分页参数不合法（数据库访问前拒绝），或 POST 校验输入不合规则。
- 服务没启动：连接失败，通常没有 HTTP 状态码，不能与 503 混淆。

## 测试与本轮验收

```powershell
# 不需要数据库；真实集成用例缺专用测试配置时明确跳过。
uv run --no-env-file pytest -q

# Docker 已启动时，随机临时容器/密码/端口，测试结束只清理本次容器。
uv run --no-env-file python -X utf8 scripts/run_database_tests.py
```

普通测试、真实数据库测试、你在 Apifox 的实践分别记录；不能把测试客户端成功说成你已经验收。实现结果见学习进度日志。

2026-10-07 用户运行记录：用户确认 `uv run --env-file .env uvicorn careerlens.api:app --host 127.0.0.1 --port 8000 --reload` 启动后数据库查询成功。Agent 核对字段名、空密码模板、Git 忽略/未跟踪状态与配置读取路径；不复述真实值，也没有在这次核对中重新连接练习库。其他筛选/失败用例和个人审查按实际反馈另记。

建议你审查 `git diff`，以及 `git status` 中新增文件（未跟踪文件不会出现在普通 diff 中）。回答：谁发送 SELECT？为什么 Apifox 请求无需改变？无匹配与数据库故障为何不同？保留一个局部测试修改，例如补充数据库模式下空白查询参数的用例。不自动提交、推送。

## 当前限制

2026-10-07 已增加 SQL 筛选与分页，详见 [分页指南](pagination-guide.md)。请求内 COUNT 与页查询共用只读 REPEATABLE READ 快照；仅校验当前页，不保证发现页外坏记录。减少传输不等于数据库无需扫描；大 OFFSET 和关键词包含搜索仍可能昂贵。索引、连接池与游标分页后续再学。无认证、无 CRUD、无生产级秘密管理，不能直接暴露到公网。
