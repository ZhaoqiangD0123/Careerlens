"""分页契约：先验证参数，再访问数据源；总数与当前页独立。"""

import json
from unittest.mock import Mock

import psycopg
import pytest
from fastapi.testclient import TestClient

from careerlens import api, job_repository
from careerlens.database import DatabaseConfig
from careerlens.job_repository import JobPage, query_database_jobs
from test_api_database import mock_connection, sample_job


@pytest.mark.parametrize("params", [
    {"limit": "0"}, {"limit": "101"}, {"limit": "abc"}, {"limit": "1.5"},
    {"offset": "-1"}, {"offset": "abc"}, {"offset": "1.5"},
])
def test_invalid_parameters_never_access_database(monkeypatch, params):
    reader = Mock(side_effect=AssertionError("不合法参数不能访问数据库"))
    monkeypatch.setattr(api, "query_database_jobs", reader)
    monkeypatch.delenv("CAREERLENS_DB_PASSWORD", raising=False)
    with TestClient(api.create_app()) as client:
        response = client.get("/jobs", params=params)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][0] == "query"
    reader.assert_not_called()


@pytest.mark.parametrize("limit,offset,length", [(20, 0, 20), (5, 20, 5), (20, 40, 3), (20, 99, 0)])
def test_file_mode_has_same_pagination_contract(tmp_path, limit, offset, length):
    jobs = [{**sample_job(), "source_url": f"https://example.com/{i}"} for i in range(43)]
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps(jobs), encoding="utf-8")
    with TestClient(api.create_app(path)) as client:
        payload = client.get("/jobs", params={"limit": limit, "offset": offset}).json()
    assert payload == {"total": 43, "items": jobs[offset:offset + limit],
                       "limit": limit, "offset": offset}
    assert len(payload["items"]) == length


def test_repository_binds_values_and_uses_one_read_only_snapshot(monkeypatch):
    connection, cursor = mock_connection(monkeypatch, [tuple(sample_job().values())])
    cursor.fetchone.return_value = (7,)
    page = query_database_jobs(DatabaseConfig(password="test"), city=" 杭州 ",
                               keyword=" %_'\\ ", limit=3, offset=4)
    assert page == JobPage(7, [sample_job()], 3, 4)
    count, rows = cursor.execute.call_args_list
    assert count.args[1] == ("杭州", "%_'\\")
    assert rows.args[1] == (*count.args[1], 3, 4)
    count_where = count.args[0].split(" WHERE ")[1]
    assert rows.args[0].split(" WHERE ")[1].split(" ORDER BY ")[0] == count_where
    assert "strpos(" in count_where and "casefold(" in count_where
    assert "%_'\\" not in count.args[0]
    assert "ORDER BY id ASC LIMIT %s OFFSET %s" in rows.args[0]
    connection.rollback.assert_called_once()
    assert connection.isolation_level == psycopg.IsolationLevel.REPEATABLE_READ
    assert connection.read_only is True
    connection.__exit__.assert_called_once()


def test_large_offset_is_empty_not_an_sql_integer_overflow(monkeypatch):
    _, cursor = mock_connection(monkeypatch, [])
    cursor.fetchone.return_value = (7,)
    page = query_database_jobs(DatabaseConfig(password="test"), offset=10 ** 100)
    assert page == JobPage(7, [], 20, 10 ** 100)
    assert cursor.execute.call_args.args[1] == (20, 7)


@pytest.mark.parametrize("limit,offset", [(0, 0), (101, 0), (True, 0), (20, -1), (20, False)])
def test_direct_repository_rejects_bad_page_before_connecting(monkeypatch, limit, offset):
    reader = Mock()
    monkeypatch.setattr(job_repository, "connect_to_database", reader)
    with pytest.raises(ValueError):
        query_database_jobs(DatabaseConfig(password="test"), limit=limit, offset=offset)
    reader.assert_not_called()


@pytest.mark.parametrize("count", [None, (), (1, 2), (-1,), ("1",)])
def test_repository_does_not_disguise_bad_count_as_empty_page(monkeypatch, count):
    _, cursor = mock_connection(monkeypatch, [])
    cursor.fetchone.return_value = count
    with pytest.raises(job_repository.DatabaseReadError):
        query_database_jobs(DatabaseConfig(password="test"))


@pytest.mark.parametrize("error,expected", [
    (psycopg.OperationalError, job_repository.DatabaseUnavailableError),
    (psycopg.errors.QueryCanceled, job_repository.DatabaseUnavailableError),
    (psycopg.errors.UndefinedTable, job_repository.DatabaseReadError),
])
def test_page_query_errors_are_sanitized(monkeypatch, error, expected):
    connection, cursor = mock_connection(monkeypatch, [])
    cursor.execute.side_effect = error("test-secret")
    with pytest.raises(expected) as result:
        query_database_jobs(DatabaseConfig(password="test"))
    assert "test-secret" not in str(result.value)
    connection.__exit__.assert_called_once()
