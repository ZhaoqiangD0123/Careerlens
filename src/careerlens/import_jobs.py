"""把已经清洗并去重的岗位 JSON 导入本机 PostgreSQL。"""

import argparse
import getpass
import sys
import warnings
from pathlib import Path

from careerlens.database import (
    DatabaseConfig,
    DatabaseConfigurationError,
    DatabaseOperationError,
    DatabasePasswordRequired,
)
from careerlens.deduplicate_jobs import UncleanedJobError, deduplicate_job_records
from careerlens.job_repository import ImportSummary, store_jobs
from careerlens.validate_file import JobFileError, read_json_file


class ImportInputError(ValueError):
    """文件含重复来源，不满足已经完成上游去重的约定。"""


def load_import_jobs(input_path: Path) -> list[dict[str, str]]:
    """连接数据库之前检查整个文件，不静默过滤、清洗或去重。"""
    # 复用去重模块对数组、类型、岗位规则与清洗状态的逐条检查。
    result = deduplicate_job_records(read_json_file(input_path))
    if result.duplicate_jobs:
        raise ImportInputError("文件内存在重复 source_url，请先完成上游去重")
    return result.unique_jobs


def import_job_file(
    input_path: Path, config: DatabaseConfig | None = None
) -> ImportSummary:
    """供测试及其他 Python 模块调用；不提示密码、不改变原文件。"""
    jobs = load_import_jobs(input_path)
    # 只有整个文件合格后，才读取配置、创建连接并开始事务。
    return store_jobs(jobs, config if config is not None else DatabaseConfig.from_env())


def build_parser() -> argparse.ArgumentParser:
    """命令行只接收文件地址，密码不能通过命令行参数传入。"""
    parser = argparse.ArgumentParser(description="导入已清洗去重的岗位到 PostgreSQL")
    parser.add_argument("input", type=Path, help="已清洗、去重的岗位 JSON 数组")
    return parser


def main() -> int:
    """前置检查 → 本机配置/隐藏密码提示 → 写入 → 成功摘要。"""
    args = build_parser().parse_args()
    try:
        jobs = load_import_jobs(args.input)
        try:
            config = DatabaseConfig.from_env()
        except DatabasePasswordRequired:
            if not sys.stdin.isatty():
                raise DatabasePasswordRequired(
                    "非交互执行需在本机安全设置 CAREERLENS_DB_PASSWORD；"
                    "也可在普通终端运行，按隐藏提示输入密码"
                ) from None
            # getpass 不显示输入；强制将无法隐藏输入的警告当作失败处理。
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                password = getpass.getpass("数据库密码（仅本机输入，不回显）：")
            config = DatabaseConfig.from_env(password=password)
        summary = store_jobs(jobs, config)
    except (JobFileError, UncleanedJobError, ImportInputError,
            DatabaseConfigurationError, DatabaseOperationError) as exc:
        print(f"导入失败：{exc}", file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        print("导入取消或终端无法安全读取密码，未报告成功", file=sys.stderr)
        return 1

    print(
        f"导入完成：文件岗位 {summary.input_count} 条，"
        f"本次新增 {summary.inserted_count} 条，已有来源跳过 {summary.skipped_count} 条，"
        f"数据库总数 {summary.total_count} 条"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
