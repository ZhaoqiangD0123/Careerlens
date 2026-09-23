"""批量岗位过滤测试。"""

import json
from pathlib import Path

import pytest

from careerlens.filter_jobs import filter_job_file, filter_job_records
from careerlens.validate_file import JobFileError


def test_filters_valid_and_invalid_jobs() -> None:
    records = [
        {
            "title": " Python 工程师 ",
            "city": " 西安 ",
            "description": " 开发 API ",
            "source_url": " https://example.com/jobs/1 ",
        },
        {
            "title": "数据工程师",
            "city": 123,
            "description": "处理数据",
            "source_url": "https://example.com/jobs/2",
        },
    ]

    result = filter_job_records(records)

    assert len(result.valid_jobs) == 1
    assert result.valid_jobs[0]["title"] == "Python 工程师"
    assert len(result.invalid_jobs) == 1
    assert result.invalid_jobs[0]["index"] == 2
    assert "city" in result.invalid_jobs[0]["error"]


def test_rejects_non_array_batch_data() -> None:
    with pytest.raises(JobFileError, match="JSON 数组"):
        filter_job_records({"title": "Python 工程师"})


def test_writes_filter_results(tmp_path: Path) -> None:
    input_path = tmp_path / "jobs.json"
    valid_path = tmp_path / "valid.json"
    invalid_path = tmp_path / "invalid.json"
    input_path.write_text(
        json.dumps(
            [
                {
                    "title": "Python 工程师",
                    "city": "西安",
                    "description": "开发 API",
                    "source_url": "https://example.com/jobs/1",
                },
                {
                    "title": "",
                    "city": "西安",
                    "description": "岗位名称为空",
                    "source_url": "https://example.com/jobs/2",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = filter_job_file(input_path, valid_path, invalid_path)

    assert len(result.valid_jobs) == 1
    assert len(result.invalid_jobs) == 1
    assert json.loads(valid_path.read_text(encoding="utf-8"))[0]["city"] == "西安"
    assert json.loads(invalid_path.read_text(encoding="utf-8"))[0]["index"] == 2
