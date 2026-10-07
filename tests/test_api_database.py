"""数据库 HTTP 契约与查询边界；普通回归不需要 Docker 或真实数据库。"""

from unittest.mock import MagicMock, Mock

import psycopg
import pytest
from fastapi.testclient import TestClient

from careerlens import api, job_repository
from careerlens.database import DatabaseConfig, DatabaseOperationError
from careerlens.job_repository import (
    DatabaseReadError, DatabaseUnavailableError, JobPage, load_database_jobs,
)


def sample_job() -> dict[str, str]:
    return {"title": "Python 工程师", "city": "杭州", "description": "FastAPI 服务",
            "source_url": "https://example.com/1"}


def test_default_database_source_is_lazy_and_reads_every_request(monkeypatch) -> None:
    factory = Mock(return_value=JobPage(1, [sample_job()], 20, 0))
    monkeypatch.setenv("CAREERLENS_DB_PASSWORD", "test-only-secret")
    monkeypatch.setattr(api, "query_database_jobs", factory)
    monkeypatch.setattr(api, "load_validated_jobs", Mock(side_effect=AssertionError("不能读文件")))
    application = api.create_app()
    factory.assert_not_called()
    with TestClient(application) as client:
        assert client.get("/jobs").json() == {"total": 1, "items": [sample_job()], "limit": 20, "offset": 0}
        factory.return_value = JobPage(0, [], 20, 0)
        assert client.get("/jobs").json() == {"total": 0, "items": [], "limit": 20, "offset": 0}
    assert factory.call_count == 2
    assert factory.call_args.args[0].password == "test-only-secret"


def test_only_list_depends_on_database(monkeypatch) -> None:
    monkeypatch.delenv("CAREERLENS_DB_PASSWORD", raising=False)
    factory = Mock(side_effect=AssertionError("独立路由不应读取数据库"))
    monkeypatch.setattr(api, "query_database_jobs", factory)
    with TestClient(api.create_app()) as client:
        assert client.get("/").json() == {"Hello": "world!"}
        assert client.post("/jobs/validate", json=sample_job()).json() == sample_job()
        assert client.post("/jobs/validate", json={}).status_code == 422
        assert client.get("/docs").status_code == 200
        assert client.get("/unknown").status_code == 404
        assert client.post("/jobs").status_code == 405
        schema = client.get("/openapi.json").json()
    factory.assert_not_called()
    operation = schema["paths"]["/jobs"]["get"]
    assert "503" in operation["responses"]
    assert {item["name"] for item in operation["parameters"]} == {"city", "keyword", "limit", "offset"}


@pytest.mark.parametrize("port", ["bad", "0", "65536"])
def test_invalid_configuration_returns_503(monkeypatch, port) -> None:
    monkeypatch.setenv("CAREERLENS_DB_PORT", port)
    monkeypatch.setenv("CAREERLENS_DB_PASSWORD", "test-only-secret")
    factory = Mock()
    monkeypatch.setattr(api, "query_database_jobs", factory)
    with TestClient(api.create_app()) as client:
        response = client.get("/jobs")
    assert response.status_code == 503
    assert response.json() == {"detail": api.DATABASE_UNAVAILABLE_DETAIL}
    factory.assert_not_called()


@pytest.mark.parametrize("error,status,detail", [
    (DatabaseUnavailableError, 503, api.DATABASE_UNAVAILABLE_DETAIL),
    (DatabaseReadError, 500, api.DATABASE_ERROR_DETAIL),
])
def test_database_failures_are_sanitized_and_do_not_fallback(
    monkeypatch, caplog, error, status, detail
) -> None:
    monkeypatch.setattr(api, "query_database_jobs", Mock(side_effect=error("test-only-secret raw row")))
    file_reader = Mock(side_effect=AssertionError("不能回退文件"))
    monkeypatch.setattr(api, "load_validated_jobs", file_reader)
    with TestClient(api.create_app(database_config=DatabaseConfig(password="test-only-secret"))) as client:
        response = client.get("/jobs", params={"city": "没有的城市"})
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert "test-only-secret" not in response.text + caplog.text
    assert "raw row" not in caplog.text
    file_reader.assert_not_called()


@pytest.mark.parametrize("params", [
    {}, {"city": " 杭州 ", "keyword": " fAsTaPi "},
    {"city": "杭"}, {"keyword": "%"},
    {"city": "西安", "keyword": "FastAPI"},
])
def test_database_query_parameters_are_forwarded_to_repository(monkeypatch, params) -> None:
    monkeypatch.setattr(api, "query_database_jobs", Mock(return_value=JobPage(1, [sample_job()], 20, 0)))
    with TestClient(api.create_app(database_config=DatabaseConfig(password="secret"))) as client:
        response = client.get("/jobs", params=params)
    assert response.status_code == 200
    assert response.json() == {"total": 1, "items": [sample_job()], "limit": 20, "offset": 0}
    call = api.query_database_jobs.call_args
    assert call.kwargs == {"city": params.get("city"), "keyword": params.get("keyword"),
                           "limit": 20, "offset": 0}


def test_source_choices_cannot_be_combined(tmp_path) -> None:
    with pytest.raises(ValueError, match="不能同时"):
        api.create_app(tmp_path / "jobs.json", database_config=DatabaseConfig(password="secret"))


def mock_connection(monkeypatch, rows):
    """模拟连接上下文；真实关闭与 SQL 行为由隔离集成测试验证。"""
    connection = MagicMock()
    connection.__enter__.return_value = connection
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = rows
    monkeypatch.setattr(job_repository, "connect_to_database", Mock(return_value=connection))
    return connection, cursor


def test_repository_selects_four_fields_orders_and_exits_context(monkeypatch) -> None:
    connection, cursor = mock_connection(monkeypatch, [tuple(sample_job().values())])
    assert load_database_jobs(DatabaseConfig(password="secret")) == [sample_job()]
    sql = cursor.execute.call_args.args[0]
    assert "ORDER BY id" in sql and "FROM public.jobs" in sql
    assert "INSERT" not in sql and "UPDATE" not in sql
    connection.__exit__.assert_called_once()


@pytest.mark.parametrize("row", [
    ("Python", "杭州", "   ", "https://example.com/1"),
    (" Python ", "杭州", "服务", "https://example.com/1"),
    ("Python", "杭州", "服务", "ftp://example.com/1"),
    ("Python", "杭州", None, "https://example.com/1"),
    ("Python", "杭州", "服务"),
    ("Python", "杭州", "服务", "https://example.com/1", "extra"),
])
def test_repository_rejects_invalid_rows_instead_of_partial_success(monkeypatch, row) -> None:
    connection, _ = mock_connection(monkeypatch, [tuple(sample_job().values()), row])
    with pytest.raises(DatabaseReadError):
        load_database_jobs(DatabaseConfig(password="secret"))
    connection.__exit__.assert_called_once()


@pytest.mark.parametrize("error,expected", [
    (psycopg.OperationalError, DatabaseUnavailableError),
    (psycopg.InterfaceError, DatabaseUnavailableError),
    (psycopg.errors.QueryCanceled, DatabaseUnavailableError),
    (psycopg.errors.LockNotAvailable, DatabaseUnavailableError),
    (psycopg.errors.UndefinedTable, DatabaseReadError),
    (psycopg.errors.UndefinedColumn, DatabaseReadError),
    (psycopg.ProgrammingError, DatabaseReadError),
])
def test_repository_maps_query_errors_without_raw_details(monkeypatch, error, expected) -> None:
    connection, cursor = mock_connection(monkeypatch, [])
    cursor.execute.side_effect = error("test-only-secret raw row")
    with pytest.raises(expected) as result:
        load_database_jobs(DatabaseConfig(password="secret"))
    assert "test-only-secret" not in str(result.value)
    assert result.value.__suppress_context__
    connection.__exit__.assert_called_once()


def test_repository_maps_connection_failure(monkeypatch) -> None:
    monkeypatch.setattr(job_repository, "connect_to_database",
                        Mock(side_effect=DatabaseOperationError("test-only-secret")))
    with pytest.raises(DatabaseUnavailableError) as result:
        load_database_jobs(DatabaseConfig(password="secret"))
    assert "test-only-secret" not in str(result.value)
