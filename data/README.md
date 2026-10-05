# 演示 JD 数据集说明

更新日期：2026-10-05。

## 来源与使用边界

这些是为 CareerLens 教学编写的合成演示记录，不是采集或核实过的真实招聘岗位。来源 URL 使用 example.com 占位链接；项目没有访问这些页面确认招聘信息，也没有真实公司、薪资或采集时间证据。

可以用来练习 JSON 校验、清洗、去重、查询参数、统计和报告。不能据此得出就业市场分布、真实技能需求频率或招聘趋势结论。

## 扩充方式

保留原有 23 条记录，追加 72 条不同来源 URL 的合法合成 JD，再追加 5 条来源相同的重复记录，共 100 条原始记录。新增 JD 覆盖 Python 后端、AI 应用、RAG、Agent、数据、NLP、模型服务、测试与评测等方向，以及杭州、西安、南京、深圳、合肥。

描述包含职责、技能和工程要求；部分字段刻意带首尾空格，用于验证清洗。原有缺字段、错误类型、空内容和非法 URL 样例保留。

## 处理数量

| 阶段 | 数量 |
| --- | --- |
| 原始 jobs.json | 100 |
| 无效记录 | 11 |
| 校验清洗后的合法记录（含重复） | 89 |
| 合法记录中的重复项 | 6 |
| 最终唯一岗位 | 83 |

最终城市数量为：杭州 17、深圳 17、南京 17、合肥 16、西安 16。这是人为构造的练习分布，不是市场调查结果。数量会随后续数据变更而变化。

## 文件职责与重新生成

- jobs.json：原始混合数据。
- valid_jobs.json、invalid_jobs.json：清洗结果与错误报告。
- deduplicated_jobs.json、duplicate_jobs.json：去重结果与重复报告。
- sample_job.json：单条岗位校验示例，与批量数据分别使用。

在项目根目录执行已有命令，重新生成派生文件和报告：

```powershell
uv run python -m careerlens.filter_jobs data/jobs.json
uv run python -m careerlens.deduplicate_jobs data/valid_jobs.json
uv run python -m careerlens.export_report data/jobs.json
```

API 读取 deduplicated_jobs.json，不会每次请求自动清洗原始数据。测试 test_demo_dataset.py 检查已保存的清洗与去重结果是否与原始数据一致，不固定总数为 100。
