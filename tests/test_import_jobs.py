"""文件前置检查和 CLI 行为；数据库事务另由真实集成测试验证。"""

import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from careerlens import import_jobs
from careerlens.database import DatabaseConfig, DatabaseOperationError
from careerlens.deduplicate_jobs import UncleanedJobError
from careerlens.import_jobs import ImportInputError, import_job_file
from careerlens.job_repository import ImportSummary
from careerlens.validate_file import JobFileError


@pytest.fixture(autouse=True)
def isolate_connection_environment(monkeypatch):
    """普通 CLI 测试不依赖运行者已有数据库配置。"""
    for key in list(os.environ):
        if key.startswith("CAREERLENS_DB_"):
            monkeypatch.delenv(key)


def make_job() -> dict[str, str]:
    return {"title": "Python 工程师", "city": "合肥",
            "description": "编写后端服务", "source_url": "https://example.com/jobs/1"}


def write_jobs(tmp_path: Path, data) -> Path:
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.mark.parametrize("data,error", [
    ({"title": "not-array"}, JobFileError),
    (None, JobFileError),
    ([None], UncleanedJobError),
    ([{"title": "missing-fields"}], UncleanedJobError),
    ([{**make_job(), "title": " Python 工程师 "}], UncleanedJobError),
    ([{**make_job(), "city": " "}], UncleanedJobError),
    ([{**make_job(), "description": 3}], UncleanedJobError),
    ([{**make_job(), "source_url": "ftp://example.com"}], UncleanedJobError),
    ([{**make_job(), "extra": "not-normalized"}], UncleanedJobError),
    ([make_job(), make_job()], ImportInputError),
])
def test_rejects_whole_input_before_configuration_or_connection(
    tmp_path: Path, monkeypatch, data, error
) -> None:
    path = write_jobs(tmp_path, data)
    before = path.read_bytes()
    store = Mock(side_effect=AssertionError("不应到达数据库"))
    config = Mock(side_effect=AssertionError("不应读取连接配置"))
    monkeypatch.setattr(import_jobs, "store_jobs", store)
    monkeypatch.setattr(import_jobs.DatabaseConfig, "from_env", config)
    with pytest.raises(error):
        import_job_file(path)
    store.assert_not_called()
    config.assert_not_called()
    assert path.read_bytes() == before


@pytest.mark.parametrize("text", ["{broken", "\xff"])
def test_rejects_invalid_json_or_encoding(tmp_path: Path, monkeypatch, text: str) -> None:
    path = tmp_path / "broken.json"
    path.write_bytes(text.encode("latin-1"))
    store = Mock()
    monkeypatch.setattr(import_jobs, "store_jobs", store)
    with pytest.raises(JobFileError):
        import_job_file(path)
    store.assert_not_called()


def test_rejects_missing_file(tmp_path: Path, monkeypatch) -> None:
    store = Mock()
    monkeypatch.setattr(import_jobs, "store_jobs", store)
    with pytest.raises(JobFileError, match="不存在"):
        import_job_file(tmp_path / "missing.json")
    store.assert_not_called()


@pytest.mark.parametrize("jobs", [[], [make_job()]])
def test_passes_valid_input_and_preserves_file(tmp_path: Path, monkeypatch, jobs) -> None:
    path = write_jobs(tmp_path, jobs)
    before = path.read_bytes()
    config = DatabaseConfig(password="test-only-secret")
    expected = ImportSummary(len(jobs), len(jobs), 0, len(jobs) + 3)
    store = Mock(return_value=expected)
    monkeypatch.setattr(import_jobs, "store_jobs", store)
    assert import_job_file(path, config) == expected
    store.assert_called_once_with(jobs, config)
    assert path.read_bytes() == before


def test_cli_prompts_privately_and_prints_committed_summary(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    path = write_jobs(tmp_path, [make_job()])
    monkeypatch.setattr("sys.argv", ["import_jobs", str(path)])
    monkeypatch.setattr(import_jobs.sys.stdin, "isatty", lambda: True)
    prompt = Mock(return_value="test-only-secret")
    monkeypatch.setattr(import_jobs.getpass, "getpass", prompt)
    monkeypatch.setattr(import_jobs, "store_jobs", Mock(return_value=ImportSummary(1, 1, 0, 4)))
    assert import_jobs.main() == 0
    output = capsys.readouterr()
    assert "本次新增 1 条" in output.out and "数据库总数 4 条" in output.out
    assert "test-only-secret" not in output.out + output.err
    prompt.assert_called_once()


def test_cli_noninteractive_missing_password_fails_without_prompt(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    path = write_jobs(tmp_path, [])
    monkeypatch.setattr("sys.argv", ["import_jobs", str(path)])
    monkeypatch.delenv("CAREERLENS_DB_PASSWORD", raising=False)
    monkeypatch.setattr(import_jobs.sys.stdin, "isatty", lambda: False)
    prompt = Mock()
    store = Mock()
    monkeypatch.setattr(import_jobs.getpass, "getpass", prompt)
    monkeypatch.setattr(import_jobs, "store_jobs", store)
    assert import_jobs.main() == 1
    assert "非交互" in capsys.readouterr().err
    prompt.assert_not_called()
    store.assert_not_called()


def test_cli_database_failure_never_prints_success(tmp_path: Path, monkeypatch, capsys) -> None:
    path = write_jobs(tmp_path, [make_job()])
    monkeypatch.setattr("sys.argv", ["import_jobs", str(path)])
    monkeypatch.setenv("CAREERLENS_DB_PASSWORD", "test-only-secret")
    monkeypatch.setattr(import_jobs, "store_jobs", Mock(side_effect=DatabaseOperationError("事务失败")))
    assert import_jobs.main() == 1
    output = capsys.readouterr()
    assert "导入完成" not in output.out and "事务失败" in output.err
