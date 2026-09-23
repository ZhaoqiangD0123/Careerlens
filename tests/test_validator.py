"""岗位数据校验的基础行为测试。"""

import pytest

from careerlens.validator import JobValidationError, validate_job


def sample_job() -> dict[str, object]:
    """每个测试都获取独立输入，避免测试之间相互影响。"""
    return {
        "title": " Python 开发工程师 ",
        "city": " 西安 ",
        "description": " 开发 AI 应用 ",
        "source_url": " https://example.com/jobs/1 ",
    }


def test_returns_trimmed_new_dict_without_changing_input() -> None:
    job = sample_job()

    result = validate_job(job)

    assert result == {
        "title": "Python 开发工程师",
        "city": "西安",
        "description": "开发 AI 应用",
        "source_url": "https://example.com/jobs/1",
    }
    assert result is not job
    assert job["title"] == " Python 开发工程师 "


def test_rejects_missing_field() -> None:
    job = sample_job()
    del job["description"]

    with pytest.raises(JobValidationError, match="description"):
        validate_job(job)


def test_rejects_non_string_field() -> None:
    job = sample_job()
    job["city"] = 123

    with pytest.raises(JobValidationError, match="city"):
        validate_job(job)


def test_rejects_empty_field() -> None:
    job = sample_job()
    job["title"] = ""

    with pytest.raises(JobValidationError, match="title"):
        validate_job(job)


def test_rejects_non_http_url() -> None:
    job = sample_job()
    job["source_url"] = "ftp://example.com/jobs/1"

    with pytest.raises(JobValidationError, match="source_url"):
        validate_job(job)

# 添加注释：用于验证 `validate_job` 函数是否正确处理包含仅有空白字符的字段。
def test_rejects_empty_field_with_whitespace() -> None:
    job = sample_job()
    job["description"] = "   "

    with pytest.raises(JobValidationError, match="description"):
        validate_job(job)