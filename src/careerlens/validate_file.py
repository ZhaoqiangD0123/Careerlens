"""从 JSON 文件读取并校验一条招聘岗位数据。"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from careerlens.validator import JobValidationError, validate_job


class JobFileError(ValueError):
    """岗位文件无法读取或不是合法 JSON 时抛出的异常。"""


def read_json_file(file_path: Path) -> Any:
    """读取 UTF-8 JSON 文件并返回解析后的 Python 对象。"""
    try:
        with file_path.open(encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError as exc:
        raise JobFileError(f"文件不存在：{file_path}") from exc
    except UnicodeDecodeError as exc:
        raise JobFileError(f"文件不是有效的 UTF-8 文本：{file_path}") from exc
    except json.JSONDecodeError as exc:
        raise JobFileError(
            f"JSON 格式错误：第 {exc.lineno} 行，第 {exc.colno} 列"
        ) from exc
    except OSError as exc:
        raise JobFileError(f"无法读取文件：{file_path}") from exc


def load_and_validate_job(file_path: Path) -> dict[str, str]:
    """读取一条岗位 JSON，并交给统一的岗位校验函数处理。"""
    job = read_json_file(file_path)
    return validate_job(job)


def build_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="校验一条 CareerLens 岗位 JSON 数据")
    parser.add_argument("file", type=Path, help="需要校验的 JSON 文件路径")
    return parser


def main() -> int:
    """运行命令行校验，并用退出码表示成功或失败。"""
    args = build_parser().parse_args()

    try:
        cleaned_job = load_and_validate_job(args.file)
    except (JobFileError, JobValidationError) as exc:
        print(f"校验失败：{exc}", file=sys.stderr)
        return 1

    print("校验成功：岗位数据格式正确")
    print(json.dumps(cleaned_job, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
