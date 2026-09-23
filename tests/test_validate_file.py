"""岗位 JSON 文件读取与校验测试。"""

import json
from pathlib import Path

import pytest

from careerlens.validate_file import JobFileError, load_and_validate_job
from careerlens.validator import JobValidationError


def test_loads_and_validates_job_json(tmp_path: Path) -> None:
    file_path = tmp_path / "job.json"
    file_path.write_text(
        json.dumps(
            {
                "title": " Python 开发工程师 ",
                "city": " 西安 ",
                "description": " 负责 AI 应用后端开发 ",
                "source_url": " https://example.com/jobs/1 ",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = load_and_validate_job(file_path)

    assert result["title"] == "Python 开发工程师"
    assert result["city"] == "西安"


def test_rejects_invalid_json(tmp_path: Path) -> None:
    file_path = tmp_path / "job.json"
    file_path.write_text('{"title":', encoding="utf-8")

    with pytest.raises(JobFileError, match="JSON 格式错误"):
        load_and_validate_job(file_path)


def test_rejects_job_with_missing_field(tmp_path: Path) -> None:
    file_path = tmp_path / "job.json"
    file_path.write_text(json.dumps({"title": "Python 开发工程师"}), encoding="utf-8")

    with pytest.raises(JobValidationError, match="city"):
        load_and_validate_job(file_path)
