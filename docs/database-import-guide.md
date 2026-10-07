# PostgreSQL 岗位导入：运行与验收

V1b-04 本指南讲独立导入命令。后续 V1b-05 已将默认 `GET /jobs` 改读数据库，启动说明见 [数据库 API 指南](database-api-guide.md)；`POST /jobs/validate` 仍只校验、不保存。所有岗位都是合成演示数据。

## 先理解三个模块

| 文件 | 职责 |
| --- | --- |
| `src/careerlens/database.py` | 读取本机连接配置、创建连接、核对数据库身份；密码不参与配置 repr |
| `src/careerlens/job_repository.py` | 参数化 SQL、来源冲突跳过、计数与整批事务 |
| `src/careerlens/import_jobs.py` | 读取文件、复用清洗/去重前置检查、隐藏密码提示、输出摘要 |

数据流：已清洗去重 JSON → 整份前置检查 → 连接 → INSERT → COUNT → 提交成功 → 摘要。

输入必须是已清洗、去重的数组。无效、仍需清洗、有额外字段或文件内重复时，在读取连接配置/写入前拒绝整批。已有数据库来源跳过而不覆盖，即使输入描述变了也不会更新旧记录。其他数据库错误回滚本次新增；提交中断等结果不确定情况不假报成功，应核对后重跑。

## 前提

在项目目录运行，Docker Desktop 已启动，练习容器 `careerlens-postgres-learning` 正常运行，`careerlens_learning.public.jobs` 已按上一课创建。不重复创建、不删除表或数据卷。

```powershell
# 安装包含稳定 psycopg 3 驱动的已锁定项目依赖。
uv sync --group dev

# 只读核对已有练习数据；下文三条是导入前的历史基线，请以当前表为准。
docker exec careerlens-postgres-learning psql -X -U careerlens -d careerlens_learning -c "SELECT id, source_url FROM public.jobs ORDER BY id;"
```

当前实现验证前，Agent 只读确认三条来源为 `/learning/sql-1`、`sql-2`、`sql-3`；第三条是用户新增练习数据，全部保留。未来运行时请以实际库状态为准。

## 连接配置

| 进程变量 | 默认值 |
| --- | --- |
| `CAREERLENS_DB_HOST` | `127.0.0.1`（本版本仅本机地址） |
| `CAREERLENS_DB_PORT` | `5433`（不是容器内的 5432） |
| `CAREERLENS_DB_NAME` | `careerlens_learning` |
| `CAREERLENS_DB_USER` | `careerlens` |
| `CAREERLENS_DB_PASSWORD` | 无；普通终端中可隐藏提示输入 |

默认使用与 HTTP 服务共用的本机 `.env`：首次配置从无密码的 `.env.example` 复制（不要覆盖已有文件），在本机填写 `CAREERLENS_DB_PASSWORD`；`.env` 不提交 Git。加载和安全边界见 [数据库 API 指南](database-api-guide.md)。

```powershell
# 显式加载本机配置；密码为空且是普通终端时，仍会隐藏提示输入。
# -X utf8 统一 Python 文本输出，避免 Windows 中文编码差异。
uv run --env-file .env python -X utf8 -m careerlens.import_jobs data/deduplicated_jobs.json
```

非交互环境没有密码则明确失败，不降级为明文提示。库名或用户名配置错误时要修改本机配置，不删除数据库重来。

### 上一课随机密码忘记了怎么办

上课用 GUID 初始化时没有要求记住它。你可以在**新开的普通 PowerShell** 中执行下面一段：由你明确读取自己练习容器的初始化密码，只存在当前进程内，不打印、不写文件或聊天。不是重新设置密码；若曾修改过数据库密码，该初始化值可能已失效，需停止并核对。

```powershell
# 不覆盖当前会话可能已经存在的其他项目密码配置。
if (Test-Path Env:CAREERLENS_DB_PASSWORD) {
    throw '当前会话已有密码配置；请使用该配置直接运行，或换一个新 PowerShell。'
}

# docker 输出被接收到变量中，不显示整个容器配置。
$taskPgEnv = docker inspect --format '{{json .Config.Env}}' careerlens-postgres-learning | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw '无法读取练习容器，请先核对 Docker。' }
$taskPgEntries = @($taskPgEnv | Where-Object { $_.StartsWith('POSTGRES_PASSWORD=') })
if ($taskPgEntries.Count -ne 1) { throw '初始化密码未找到，请先核对本机配置。' }

try {
    $env:CAREERLENS_DB_PASSWORD = $taskPgEntries[0].Substring('POSTGRES_PASSWORD='.Length)
    uv run python -X utf8 -m careerlens.import_jobs data/deduplicated_jobs.json
    # 第一次失败时不要盲目运行第二次；先看错误。
    if ($LASTEXITCODE -eq 0) {
        uv run python -X utf8 -m careerlens.import_jobs data/deduplicated_jobs.json
    }
}
finally {
    # 只清理本段创建的临时密码变量，不删除任何文件或数据。
    Remove-Item Env:CAREERLENS_DB_PASSWORD -ErrorAction SilentlyContinue
    Remove-Variable taskPgEnv, taskPgEntries -ErrorAction SilentlyContinue
}
```

不要单独输出 `$taskPgEnv`、密码变量或完整 `docker inspect` 内容。Docker 管理者可以读到容器环境变量，因此这只是本机练习办法，不是生产秘密管理；环境变量清除也不代表操作系统内存被安全擦除。现有练习管理员不应直接作为未来部署应用账号。

## 用户两次运行的验收

2026-10-06 实际验收已完成：用户首次新增 83、跳过 0、总数 83；再次新增 0、跳过 83、总数仍 83。只读检查教学来源已为 0，83 个数据库来源与文件完全一致。下面的 86 仅是“保留三条教学记录”的历史条件预期，不是必须达到的固定数字；不要为了凑数补数据。运行通过不代表事务解释或个人代码审查已完成。

若仍为上述三条已有来源、83 条文件岗位不变且没有其他写入：

```text
首次：文件岗位 83 条，本次新增 83 条，已有来源跳过 0 条，数据库总数 86 条
再次：文件岗位 83 条，本次新增 0 条，已有来源跳过 83 条，数据库总数 86 条
```

这些是保留三条教学数据时的历史**预期**，不是当前目标；用户实际两次结果已经记录为总数 83，Agent 未代为执行。之后用 SQL 检查：

```sql
-- 在 psql 里检查，不是在 PowerShell 直接执行。
SELECT COUNT(*) AS job_count FROM public.jobs;
```

空数组合法，新增/跳过为 0，但仍连接数据库读取总数。文件内错误与已有数据库重复是不同情况：前者拒绝，后者显式跳过。数据库计数为事务内快照；第一遍验收不涉及其他客户端并发写入。

## 测试：普通回归与真实数据库分开

```powershell
# 普通回归：不加载本机 .env；无专用测试配置时，真实数据库用例明确跳过。
uv run --no-env-file pytest -q

# 临时 PostgreSQL 18、随机密码、本机临时端口、内存数据目录。
# 目前包括导入与 API 共 15 项；结束只移除本次创建的测试容器。
uv run --no-env-file python -X utf8 scripts/run_database_tests.py
```

集成测试不使用 `careerlens_learning`，包括 83 条 CLI 首次导入与重跑、不覆盖旧记录、引号/类 SQL 文本安全保存、写入中途回滚、COMMIT 失败不报告成功、空输入和错误密码。测试脚本仅对本次创建的确切容器 ID 清理；清理失败会返回非零，请根据输出核对临时容器，不批量删除其他资源。

## 审查与口述

运行 `git diff` 审查已跟踪文件，新文件需打开阅读；未暂存的新文件不出现在普通 diff 中。重点检查以上三模块及测试。

只需解释：为何第二次不重复新增？为何计数已经算出也要等提交后才报告？为什么只用唯一约束还不能代替上游清洗？

少量局部练习：可亲自添加一个“`CAREERLENS_DB_PORT=70000` 必须拒绝”的配置测试，再运行它；不必逐行重写数据库驱动。

依据：[Psycopg 基本使用](https://www.psycopg.org/psycopg3/docs/basic/usage.html)、[参数化 SQL](https://www.psycopg.org/psycopg3/docs/basic/params.html)、[ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html)。
