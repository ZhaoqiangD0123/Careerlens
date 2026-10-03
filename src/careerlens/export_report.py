"""从原始岗位数据依次清洗、去重、统计并导出 Markdown 报告。"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from careerlens.catalog import Job, build_job_statistics
from careerlens.deduplicate_jobs import deduplicate_job_records
from careerlens.filter_jobs import filter_job_records
from careerlens.validate_file import JobFileError, read_json_file


@dataclass(frozen=True)
class ReportSummary:
    """记录原始数据经过过滤和去重后的各阶段数量。"""

    input_count: int
    invalid_count: int
    duplicate_count: int
    kept_count: int


def _table_cell(value: str) -> str:
    """转义表格分隔符和换行，防止岗位文字打乱 Markdown 表格。"""
    return (
        value.replace("|", "\\|")
        .replace("\r\n", "<br>")
        .replace("\n", "<br>")
        .replace("\r", "<br>")
    )


def _count_lines(counts: dict[str, int]) -> list[str]:
    """将已按频次排序的统计结果转为列表项。"""
    return [f"- {name}：{count}" for name, count in counts.items()] or ["- 暂无数据"]


def build_markdown_report(
    jobs: list[Job], source_name: str, summary: ReportSummary
) -> str:
    """复用现有统计规则，生成一份岗位市场观察报告。"""
    statistics = build_job_statistics(jobs)
    lines = [
        "# AI 岗位观察报告",
        "",
        f"数据来源：{source_name}",
        f"岗位总数：{summary.kept_count}",
        "",
        "## 处理概况",
        f"- 原始岗位：{summary.input_count}",
        f"- 无效岗位：{summary.invalid_count}",
        f"- 重复岗位：{summary.duplicate_count}",
        f"- 最终保留：{summary.kept_count}",
        "",
        "## 岗位关键词频次",
        *_count_lines(statistics["roles"]),
        "",
        "## 城市分布",
        *_count_lines(statistics["cities"]),
        "",
        "## 常见技能",
        *_count_lines(statistics["skills"]),
        "",
        "## 岗位列表",
        "| 岗位 | 城市 | 来源 |",
        "| --- | --- | --- |",
    ]
    for job in jobs:
        lines.append(
            "| "
            + " | ".join(
                _table_cell(job[field]) for field in ("title", "city", "source_url")
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def export_report(input_path: Path, output_path: Path) -> ReportSummary:
    """从原始 JSON 自动完成清洗、去重、统计和报告导出。"""
    if input_path.resolve() == output_path.resolve():
        raise JobFileError("报告输出路径不能与原始数据路径相同")

    # 过滤阶段调用 validate_job，将合法岗位的字段首尾空格清理干净。
    filtered = filter_job_records(read_json_file(input_path))
    # 去重函数要求输入已经清洗；这里传入过滤阶段产生的合法数据。
    deduplicated = deduplicate_job_records(filtered.valid_jobs)
    summary = ReportSummary(
        input_count=len(filtered.valid_jobs) + len(filtered.invalid_jobs),
        invalid_count=len(filtered.invalid_jobs),
        duplicate_count=len(deduplicated.duplicate_jobs),
        kept_count=len(deduplicated.unique_jobs),
    )
    report = build_markdown_report(deduplicated.unique_jobs, str(input_path), summary)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
    except OSError as exc:
        raise JobFileError(f"无法写入报告：{output_path}") from exc
    return summary


def build_parser() -> argparse.ArgumentParser:
    """解析输入文件及可选输出路径。"""
    parser = argparse.ArgumentParser(description="导出 CareerLens Markdown 岗位报告")
    parser.add_argument("input", type=Path, help="原始岗位 JSON 数组文件")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/job-market-summary.md"),
        help="报告输出路径（默认 reports/job-market-summary.md）",
    )
    return parser


def main() -> int:
    """执行报告导出并给出可读的运行结果。"""
    args = build_parser().parse_args()
    try:
        summary = export_report(args.input, args.output)
    except JobFileError as exc:
        print(f"导出失败：{exc}", file=sys.stderr)
        return 1
    print(
        f"报告已生成：{args.output}（原始 {summary.input_count} 条，"
        f"无效 {summary.invalid_count} 条，重复 {summary.duplicate_count} 条，"
        f"保留 {summary.kept_count} 条）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
