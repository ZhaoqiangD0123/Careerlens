"""Markdown 报告导出测试。"""

import json
from pathlib import Path

import pytest

from careerlens.export_report import export_report
from careerlens.validate_file import JobFileError


def make_job(title: str, city: str, source_url: str) -> dict[str, str]:
    return {
        "title": title,
        "city": city,
        "description": "使用 Python 开发 AI 应用",
        "source_url": source_url,
    }


def test_exports_summary_and_job_table_from_raw_jobs(tmp_path: Path) -> None:
    input_path = tmp_path / "jobs.json"
    output_path = tmp_path / "reports" / "summary.md"
    jobs = [
        make_job(" AI 测试工程师 ", " 杭州 ", " https://example.com/jobs/1 "),
        make_job("AI 测试工程师", "杭州", "https://example.com/jobs/1"),
        make_job("Python 测试工程师", "西安", "https://example.com/jobs/2"),
        {"title": "测试工程师"},
    ]
    input_path.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")

    summary = export_report(input_path, output_path)
    assert (summary.input_count, summary.invalid_count, summary.duplicate_count, summary.kept_count) == (4, 1, 1, 2)
    report = output_path.read_text(encoding="utf-8")
    assert "# AI 岗位观察报告" in report
    assert "岗位总数：2" in report
    assert "- 原始岗位：4" in report
    assert "- 无效岗位：1" in report
    assert "- 重复岗位：1" in report
    assert "- 杭州：1" in report
    assert "- Python：2" in report
    assert "| AI 测试工程师 | 杭州 | https://example.com/jobs/1 |" in report
    # 断言报告中包含常见技能统计部分
    assert "测试：2" in report


def test_does_not_overwrite_raw_input(tmp_path: Path) -> None:
    input_path = tmp_path / "jobs.json"
    original = json.dumps([make_job("第一条", "杭州", "https://example.com/jobs/1")], ensure_ascii=False)
    input_path.write_text(original, encoding="utf-8")

    with pytest.raises(JobFileError, match="不能与原始数据路径相同"):
        export_report(input_path, input_path)
    assert input_path.read_text(encoding="utf-8") == original
