# SQL 筛选与分页：运行验收

2026-10-07，V1b-06 已按用户确认实现。学习重点是数据流与接口契约，不要求你手写整套 SQL。

## 1. 重启服务

先在原服务终端 Ctrl+C；在项目根目录执行，保留你已填写的 `.env`：

```powershell
uv run --env-file .env uvicorn careerlens.api:app --host 127.0.0.1 --port 8000 --reload
```

配置加载、环境变量优先级与凭据约定仍见 [数据库 API 指南](database-api-guide.md)，本课没有新增环境配置。分页默认值是接口规则，不搬到 `.env`。

## 2. 在 Apifox 运行

将 [分页集合](careerlens.pagination.postman_collection.json) 作为 Postman 格式导入独立目录，保留旧接口；本机地址 `http://127.0.0.1:8000`，GET 请求不填 Body 或凭据。同路径可能合并为测试用例，务必核对各项 Params 与后置操作。

以下数量只适用于当前 83 条合成数据，实际增删后按数据库数量核对，不修改代码迎合旧样本：

| 请求 | total | 本页条数 | 状态码 |
| --- | --- | --- | --- |
| `/jobs` | 83 | 20 | 200 |
| `/jobs?limit=20&offset=20` | 83 | 20 | 200 |
| `/jobs?offset=80` | 83 | 3 | 200 |
| `/jobs?offset=100` | 83 | 0 | 200 |
| `/jobs?city=杭州&limit=5&offset=5` | 17 | 5 | 200 |
| `/jobs?city=杭州&keyword=FastAPI&limit=2` | 3 | 2 | 200 |
| 不存在的关键词 | 0 | 0 | 200 |
| limit=0、101、abc 或 offset=-1 | 无分页响应 | 无分页响应 | 422 |

响应外层为 total、items、limit、offset；岗位仍只有 title、city、description、source_url。limit 默认20、范围1—100；offset默认0且非负，是跳过的匹配记录数，不是主键或页码。

已经导入的旧脚本不会自动更新。重新导入更新后的基础/查询集合，或把 [列表通用后置脚本](apifox-jobs-post-response.js) 替换进去，保留城市和关键词检查。若启用响应契约校验，同步四字段分页模型；不要再要求 total===items.length。原 POST 校验用例无需改变。

## 3. 理解分工

```text
Apifox 参数 → FastAPI 检查范围 → query_database_jobs
  → SQL WHERE 决定匹配记录
  → 同一只读快照 COUNT 取得 total
  → ORDER BY id ASC / LIMIT / OFFSET 取得本页
  → Python 校验本页四字段 → 分页 JSON
```

城市精确匹配；keyword 在名称、城市、描述拼接文本中作字面包含；组合条件为 AND，空白忽略。用户值单独绑定，不能拼接成 SQL；`%`、`_`、反斜线、引号不是通配符。[Psycopg 参数化](https://www.psycopg.org/psycopg3/docs/basic/params.html)。

本版针对 PostgreSQL 18/UTF8 使用 casefold 与 pg_unicode_fast，而非把 lower 当作 Python casefold 的等价替换。选定中文、ASCII、ß/ss、希腊大小写与跨字段样例已实测；不同 Unicode 版本仍可能有差异，不保证覆盖所有语言。[PostgreSQL 字符串函数](https://www.postgresql.org/docs/current/functions-string.html)。

COUNT 与页查询用相同 WHERE、同一只读 REPEATABLE READ 事务；并发测试确认中间提交不会改变同请求内快照。多个 HTTP 请求之间不共享快照，增删可能让页面位置变化。[事务隔离](https://www.postgresql.org/docs/current/transaction-iso.html)。

只校验当前页：页内坏记录返回500，页外或未匹配坏记录不保证发现；COUNT不是内容审计。503仍表示配置/连接/认证/超时；首页与POST校验仍不依赖数据库。没有故障回退文件。

分页减少传输与应用处理，不保证 COUNT/包含搜索无需扫描；大 OFFSET 仍可能昂贵。本课未引入索引、游标分页、连接池或 ORM，不作生产性能承诺。[分页排序与限制](https://www.postgresql.org/docs/current/queries-limit.html)。

## 4. 你的验收

1. 运行上述第一页、第二页、末页、空页及422用例，查看实际 JSON 和后置断言结果。
2. 查看 `git diff` 与 `git status`；新增未跟踪文件不在普通 diff 里，单独打开。重点看 api.py 的参数职责、job_repository.py 的查询职责。
3. 用自己的话解释：为什么先筛选再分页？total 与本页条数的区别？为什么指定排序？只检查当前页意味着什么？
4. 少量局部练习可在 Apifox 新增 `limit=3&offset=3` 用例，不必重复手写查询实现。未经你的指令不提交或推送。

自动证据：180 项普通测试通过；41 项真实集成测试另在临时 PostgreSQL 18 通过；30 个真实 HTTP 集合请求、123 个 pm 兼容后置断言通过。普通测试中的41项跳过是因为未设置隔离库配置，不是用假数据库代替真实验证。临时容器已移除，练习库与本机配置未动。这些不替代你的个人验收。
