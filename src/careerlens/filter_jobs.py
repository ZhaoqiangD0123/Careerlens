"""批量校验岗位数据，并分别保存合法数据与错误报告。"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from careerlens.validate_file import JobFileError, read_json_file
from careerlens.validator import JobValidationError, validate_job


@dataclass
class FilterResult:
    """一次批量过滤的结果。"""

    valid_jobs: list[dict[str, str]]
    invalid_jobs: list[dict[str, Any]]


def filter_job_records(data: Any) -> FilterResult:
    """逐条校验 JSON 数组中的岗位，并保留错误原因。"""
    if not isinstance(data, list):
        raise JobFileError("批量岗位文件的最外层必须是 JSON 数组")

    valid_jobs: list[dict[str, str]] = []
    invalid_jobs: list[dict[str, Any]] = []

    for index, job in enumerate(data, start=1):
        try:
            valid_jobs.append(validate_job(job))
        except JobValidationError as exc:
            invalid_jobs.append(
                {
                    "index": index,
                    "error": str(exc),
                    "data": job,
                }
            )

    return FilterResult(valid_jobs=valid_jobs, invalid_jobs=invalid_jobs)


def write_json_file(file_path: Path, data: Any) -> None:
    """以 UTF-8 格式写入便于阅读的 JSON。"""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        file_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise JobFileError(f"无法写入文件：{file_path}") from exc


def filter_job_file(
    input_path: Path,
    valid_output_path: Path,
    invalid_output_path: Path,
) -> FilterResult:
    """读取岗位数组、完成过滤并写出两个结果文件。"""
    result = filter_job_records(read_json_file(input_path))
    write_json_file(valid_output_path, result.valid_jobs)
    write_json_file(invalid_output_path, result.invalid_jobs)
    return result


def build_parser() -> argparse.ArgumentParser:
    """创建批量过滤命令的参数解析器。"""
    parser = argparse.ArgumentParser(description="过滤 CareerLens 批量岗位 JSON 数据")
    parser.add_argument("input", type=Path, help="包含岗位数组的 JSON 文件")
    parser.add_argument(
        "--valid-output",
        type=Path,
        default=Path("data/valid_jobs.json"),
        help="合法岗位输出路径",
    )
    parser.add_argument(
        "--invalid-output",
        type=Path,
        default=Path("data/invalid_jobs.json"),
        help="非法岗位与错误原因输出路径",
    )
    return parser


def main() -> int:
    """执行批量过滤并打印统计结果。"""
    args = build_parser().parse_args()
    try:
        result = filter_job_file(
            args.input,
            args.valid_output,
            args.invalid_output,
        )
    except JobFileError as exc:
        print(f"过滤失败：{exc}", file=sys.stderr)
        return 1

    print(f"过滤完成：合法 {len(result.valid_jobs)} 条，非法 {len(result.invalid_jobs)} 条")
    print(f"合法数据：{args.valid_output}")
    print(f"错误报告：{args.invalid_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
