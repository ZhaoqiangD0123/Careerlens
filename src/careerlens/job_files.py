"""供命令行和 HTTP 接口共用的岗位文件读取逻辑。"""

from pathlib import Path

from careerlens.catalog import Job
from careerlens.filter_jobs import filter_job_records
from careerlens.validate_file import JobFileError, read_json_file


def load_validated_jobs(file_path: Path) -> list[Job]:
    """读取岗位数组；只接受全部通过校验的数据文件。"""
    result = filter_job_records(read_json_file(file_path))
    # 查询入口不能静默过滤坏数据，否则调用方会误以为取得了完整列表。
    if result.invalid_jobs:
        raise JobFileError(
            f"文件中有 {len(result.invalid_jobs)} 条非法数据，请先运行批量过滤命令"
        )
    return result.valid_jobs
