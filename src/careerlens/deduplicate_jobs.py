"""使用 source_url 对已经清洗的岗位数据进行去重。"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from careerlens.filter_jobs import write_json_file
from careerlens.validate_file import JobFileError, read_json_file
from careerlens.validator import JobValidationError, validate_job


class UncleanedJobError(ValueError):
    """输入岗位尚未完成校验和清洗。"""


@dataclass
class DeduplicationResult:
    """一次岗位去重的结果。"""

    unique_jobs: list[dict[str, str]]
    duplicate_jobs: list[dict[str, Any]]


def _require_cleaned_job(job: Any, index: int) -> dict[str, str]:
    """确认岗位已通过校验，而且内容与清洗结果完全一致。"""
    try:
        cleaned_job = validate_job(job)
    except JobValidationError as exc:
        raise UncleanedJobError(f"第 {index} 条岗位未通过校验：{exc}") from exc

    if cleaned_job != job:
        raise UncleanedJobError(
            f"第 {index} 条岗位尚未完成清洗，请先运行批量过滤命令"
        )
    return cleaned_job


def deduplicate_job_records(data: Any) -> DeduplicationResult:
    """按 source_url 去重，保留每个链接第一次出现的岗位。"""
    if not isinstance(data, list):
        raise JobFileError("批量岗位文件的最外层必须是 JSON 数组")

    unique_jobs: list[dict[str, str]] = []
    duplicate_jobs: list[dict[str, Any]] = []
    first_index_by_url: dict[str, int] = {}

    for index, job in enumerate(data, start=1):
        cleaned_job = _require_cleaned_job(job, index)
        source_url = cleaned_job["source_url"]

        if source_url in first_index_by_url:
            duplicate_jobs.append(
                {
                    "index": index,
                    "duplicate_of": first_index_by_url[source_url],
                    "source_url": source_url,
                    "data": cleaned_job,
                }
            )
            continue

        first_index_by_url[source_url] = index
        unique_jobs.append(cleaned_job)

    return DeduplicationResult(
        unique_jobs=unique_jobs,
        duplicate_jobs=duplicate_jobs,
    )


def deduplicate_job_file(
    input_path: Path,
    unique_output_path: Path,
    duplicate_output_path: Path,
) -> DeduplicationResult:
    """读取已清洗岗位文件，完成去重并写出结果。"""
    result = deduplicate_job_records(read_json_file(input_path))
    write_json_file(unique_output_path, result.unique_jobs)
    write_json_file(duplicate_output_path, result.duplicate_jobs)
    return result


def build_parser() -> argparse.ArgumentParser:
    """创建岗位去重命令的参数解析器。"""
    parser = argparse.ArgumentParser(description="按 source_url 对已清洗岗位去重")
    parser.add_argument("input", type=Path, help="已经校验和清洗的岗位 JSON 文件")
    parser.add_argument(
        "--unique-output",
        type=Path,
        default=Path("data/deduplicated_jobs.json"),
        help="去重后的岗位输出路径",
    )
    parser.add_argument(
        "--duplicate-output",
        type=Path,
        default=Path("data/duplicate_jobs.json"),
        help="重复岗位报告输出路径",
    )
    return parser


def main() -> int:
    """执行岗位去重并显示结果摘要。"""
    args = build_parser().parse_args()
    try:
        result = deduplicate_job_file(
            args.input,
            args.unique_output,
            args.duplicate_output,
        )
    except (JobFileError, UncleanedJobError) as exc:
        print(f"去重失败：{exc}", file=sys.stderr)
        return 1

    print(
        f"去重完成：保留 {len(result.unique_jobs)} 条，"
        f"发现重复 {len(result.duplicate_jobs)} 条"
    )
    print(f"去重数据：{args.unique_output}")
    print(f"重复报告：{args.duplicate_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
