"""真实 PostgreSQL 集成测试，只允许使用专用临时测试库。"""

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from careerlens.database import DatabaseConfig, DatabaseOperationError, connect_to_database
from careerlens.import_jobs import import_job_file


ROOT = Path(__file__).resolve().parents[1]
def job(url: str, title: str = "Python 工程师") -> dict[str, str]:
    return {"title": title, "city": "合肥", "description": "开发服务", "source_url": url}


def input_file(tmp_path: Path, jobs) -> Path:
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
    return path


def count_rows(config: DatabaseConfig) -> int:
    with connect_to_database(config) as connection:
        return connection.execute("SELECT COUNT(*) FROM public.jobs").fetchone()[0]


def test_real_cli_imports_83_jobs_and_safely_reruns(test_database, tmp_path: Path) -> None:
    # 在隔离库里模拟三条已有教学记录；不使用用户实际练习表。
    existing = [job(f"https://example.com/learning/sql-{i}") for i in (1, 2, 3)]
    import_job_file(input_file(tmp_path, existing), test_database)
    source = ROOT / "data" / "deduplicated_jobs.json"
    before = source.read_bytes()
    jobs = json.loads(before)
    assert len(jobs) == 83
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    for key, value in {
        "HOST": test_database.host, "PORT": str(test_database.port),
        "NAME": test_database.name, "USER": test_database.user,
        "PASSWORD": test_database.password,
    }.items():
        env[f"CAREERLENS_DB_{key}"] = value
    for expected in ("本次新增 83 条，已有来源跳过 0 条", "本次新增 0 条，已有来源跳过 83 条"):
        result = subprocess.run(
            [sys.executable, "-m", "careerlens.import_jobs", str(source)],
            env=env, capture_output=True, text=True, encoding="utf-8",
            timeout=30,
        )
        # 子进程按 UTF-8 输出，避免 Windows 默认编码影响中文断言。
        assert result.returncode == 0, result.stderr
        assert expected in result.stdout
        assert "数据库总数 86 条" in result.stdout
    assert count_rows(test_database) == 86
    assert source.read_bytes() == before
    with connect_to_database(test_database) as connection:
        rows = connection.execute(
            "SELECT title, city, description, source_url FROM public.jobs"
        ).fetchall()
    # 不只核对行数：83 条文件数据加三条种子记录的每个字段都必须保持一致。
    expected_jobs = jobs + existing
    assert {row[3]: row[:3] for row in rows} == {
        record["source_url"]: (record["title"], record["city"], record["description"])
        for record in expected_jobs
    }


def test_existing_record_is_not_overwritten_and_quotes_are_data(test_database, tmp_path: Path) -> None:
    # 看起来像 SQL 的标题也只能成为数据，不能执行 DROP 等语句。
    original = job("https://example.com/quoted", "O'Reilly'); DROP TABLE public.jobs; --")
    import_job_file(input_file(tmp_path, [original]), test_database)
    changed = {**original, "title": "新标题", "description": "新描述"}
    result = import_job_file(input_file(tmp_path, [changed]), test_database)
    assert (result.inserted_count, result.skipped_count, result.total_count) == (0, 1, 1)
    with connect_to_database(test_database) as connection:
        row = connection.execute("SELECT title, description FROM public.jobs").fetchone()
    assert row == (original["title"], original["description"])


def test_mid_batch_failure_rolls_back_new_rows_only(test_database, tmp_path: Path) -> None:
    import_job_file(input_file(tmp_path, [job("https://example.com/existing")]), test_database)
    with connect_to_database(test_database) as connection:
        # 仅在临时测试库增加故障约束，模拟第二条写入发生数据库错误。
        connection.execute("ALTER TABLE public.jobs ADD CHECK (title <> 'force-failure')")
    path = input_file(tmp_path, [
        job("https://example.com/first-new"),
        job("https://example.com/second-new", "force-failure"),
    ])
    with pytest.raises(DatabaseOperationError):
        import_job_file(path, test_database)
    assert count_rows(test_database) == 1


def test_commit_failure_does_not_return_success(test_database, tmp_path: Path) -> None:
    with connect_to_database(test_database) as connection:
        # 延迟到 COMMIT 才检查，验证摘要不能在退出事务前返回。
        connection.execute(
            "ALTER TABLE public.jobs ADD UNIQUE (city) DEFERRABLE INITIALLY DEFERRED"
        )
    path = input_file(tmp_path, [job("https://example.com/1"), job("https://example.com/2")])
    with pytest.raises(DatabaseOperationError):
        import_job_file(path, test_database)
    assert count_rows(test_database) == 0


def test_empty_input_queries_existing_total(test_database, tmp_path: Path) -> None:
    import_job_file(input_file(tmp_path, [job("https://example.com/existing")]), test_database)
    result = import_job_file(input_file(tmp_path, []), test_database)
    assert (result.input_count, result.inserted_count, result.skipped_count, result.total_count) == (0, 0, 0, 1)


def test_tcp_password_authentication_is_enforced(test_database) -> None:
    with pytest.raises(DatabaseOperationError):
        connect_to_database(replace(test_database, password="intentionally-wrong-test-password"))
