"""岗位去重功能测试。"""

import json
from pathlib import Path

import pytest

from careerlens.deduplicate_jobs import (
    UncleanedJobError,
    deduplicate_job_file,
    deduplicate_job_records,
)


def make_job(title: str, source_url: str) -> dict[str, str]:
    return {
        "title": title,
        "city": "西安",
        "description": "开发 AI 应用",
        "source_url": source_url,
    }


def test_deduplicates_by_source_url_and_keeps_first_job() -> None:
    jobs = [
        make_job("第一条岗位", "https://example.com/jobs/1"),
        make_job("相同链接的另一条岗位", "https://example.com/jobs/1"),
        make_job("不同岗位", "https://example.com/jobs/2"),
    ]

    result = deduplicate_job_records(jobs)

    assert [job["title"] for job in result.unique_jobs] == ["第一条岗位", "不同岗位"]
    assert result.duplicate_jobs[0]["index"] == 2
    assert result.duplicate_jobs[0]["duplicate_of"] == 1


def test_rejects_job_that_has_not_been_cleaned() -> None:
    job = make_job(" Python 工程师 ", "https://example.com/jobs/1")

    with pytest.raises(UncleanedJobError, match="尚未完成清洗"):
        deduplicate_job_records([job])


def test_rejects_invalid_job_before_deduplication() -> None:
    job = make_job("Python 工程师", "https://example.com/jobs/1")
    job["city"] = ""

    with pytest.raises(UncleanedJobError, match="未通过校验"):
        deduplicate_job_records([job])


def test_writes_unique_jobs_and_duplicate_report(tmp_path: Path) -> None:
    input_path = tmp_path / "valid_jobs.json"
    unique_path = tmp_path / "unique.json"
    duplicate_path = tmp_path / "duplicates.json"
    jobs = [
        make_job("Python 工程师", "https://example.com/jobs/1"),
        make_job("重复岗位", "https://example.com/jobs/1"),
    ]
    input_path.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")

    result = deduplicate_job_file(input_path, unique_path, duplicate_path)

    assert len(result.unique_jobs) == 1
    assert len(result.duplicate_jobs) == 1
    assert len(json.loads(unique_path.read_text(encoding="utf-8"))) == 1
    assert json.loads(duplicate_path.read_text(encoding="utf-8"))[0]["duplicate_of"] == 1
