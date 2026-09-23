"""在命令行中展示、搜索、筛选和统计岗位。"""

import argparse
import sys
from pathlib import Path

from careerlens.catalog import Job, build_job_statistics, filter_jobs, search_jobs
from careerlens.filter_jobs import filter_job_records
from careerlens.validate_file import JobFileError, read_json_file


def load_validated_jobs(file_path: Path) -> list[Job]:
    """读取岗位数组；只接受全部通过校验的数据文件。"""
    result = filter_job_records(read_json_file(file_path))
    if result.invalid_jobs:
        raise JobFileError(
            f"文件中有 {len(result.invalid_jobs)} 条非法数据，请先运行批量过滤命令"
        )
    return result.valid_jobs


def print_jobs(jobs: list[Job]) -> None:
    """以便于阅读的形式显示岗位列表。"""
    if not jobs:
        print("没有找到符合条件的岗位")
        return

    for index, job in enumerate(jobs, start=1):
        print(f"{index}. [{job['city']}] {job['title']}")
        print(f"   {job['description']}")
        print(f"   {job['source_url']}")
    print(f"共 {len(jobs)} 条")


def print_counts(title: str, counts: dict[str, int]) -> None:
    """显示一组按频次排序的统计结果。"""
    print(f"\n{title}")
    if not counts:
        print("  暂无匹配项")
        return
    for name, count in counts.items():
        print(f"  {name}: {count}")


def print_statistics(jobs: list[Job]) -> None:
    """显示城市、岗位和技能词频。"""
    statistics = build_job_statistics(jobs)
    print(f"岗位总数：{len(jobs)}")
    print_counts("城市分布", statistics["cities"])
    print_counts("岗位关键词频次", statistics["roles"])
    print_counts("技能关键词频次", statistics["skills"])


def build_parser() -> argparse.ArgumentParser:
    """创建岗位浏览命令的参数解析器。"""
    parser = argparse.ArgumentParser(description="浏览和分析 CareerLens 岗位数据")
    parser.add_argument("file", type=Path, help="全部通过校验的岗位 JSON 文件")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("list", help="展示全部岗位")

    search_parser = commands.add_parser("search", help="搜索岗位名称、城市和描述")
    search_parser.add_argument("keyword", help="搜索关键词")

    filter_parser = commands.add_parser("filter", help="按城市或岗位名称筛选")
    filter_parser.add_argument("--city", help="城市，使用精确匹配")
    filter_parser.add_argument("--title", help="岗位名称关键词，使用包含匹配")

    commands.add_parser("stats", help="统计城市、岗位和技能关键词频次")
    return parser


def main() -> int:
    """执行用户选择的岗位浏览命令。"""
    args = build_parser().parse_args()
    try:
        jobs = load_validated_jobs(args.file)
    except JobFileError as exc:
        print(f"读取失败：{exc}", file=sys.stderr)
        return 1

    if args.command == "list":
        print_jobs(jobs)
    elif args.command == "search":
        print_jobs(search_jobs(jobs, args.keyword))
    elif args.command == "filter":
        print_jobs(filter_jobs(jobs, city=args.city, title_keyword=args.title))
    elif args.command == "stats":
        print_statistics(jobs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
