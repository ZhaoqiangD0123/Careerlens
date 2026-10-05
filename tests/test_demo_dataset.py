"""保证演示原始数据与已提交的清洗、去重结果一致。"""

from pathlib import Path

from careerlens.deduplicate_jobs import deduplicate_job_records
from careerlens.filter_jobs import filter_job_records
from careerlens.validate_file import read_json_file


def test_demo_artifacts_match_raw_dataset() -> None:
    # 从测试文件位置找项目目录，避免依赖执行 pytest 时的工作目录。
    data_directory = Path(__file__).resolve().parents[1] / "data"
    filtered = filter_job_records(read_json_file(data_directory / "jobs.json"))
    deduplicated = deduplicate_job_records(filtered.valid_jobs)

    # 派生文件应由现有流水线产生；扩充原始数据后不能忘记刷新 API 数据源。
    assert read_json_file(data_directory / "valid_jobs.json") == filtered.valid_jobs
    assert read_json_file(data_directory / "invalid_jobs.json") == filtered.invalid_jobs
    assert read_json_file(data_directory / "deduplicated_jobs.json") == deduplicated.unique_jobs
    assert read_json_file(data_directory / "duplicate_jobs.json") == deduplicated.duplicate_jobs

    # 保留混合样例，用于体验正常、清洗失败和重复记录三类情况。
    assert filtered.valid_jobs
    assert filtered.invalid_jobs
    assert deduplicated.duplicate_jobs
