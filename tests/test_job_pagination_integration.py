"""在专用临时 PostgreSQL 18 库验证真实 SQL，而非用 mock 替代筛选。"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from careerlens import api, job_repository
from careerlens.catalog import filter_jobs, search_jobs
from careerlens.database import connect_to_database
from careerlens.job_repository import query_database_jobs, store_jobs
from test_api_database_integration import job


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("params,total,length", [
    ({}, 83, 20), ({"offset": 20}, 83, 20), ({"offset": 80}, 83, 3),
    ({"offset": 100}, 83, 0), ({"limit": 100}, 83, 83),
    ({"offset": 10 ** 100}, 83, 0),
    ({"city": "杭州", "limit": 5}, 17, 5),
    ({"keyword": "FastAPI", "limit": 5}, 13, 5),
    ({"city": " 杭州 ", "keyword": " fAsTaPi "}, 3, 3),
    ({"keyword": "不存在的关键词"}, 0, 0),
])
def test_sql_pagination_matches_catalog_on_83_records(test_database, params, total, length):
    records = json.loads((ROOT / "data/deduplicated_jobs.json").read_text(encoding="utf-8"))
    store_jobs(records, test_database)
    expected = search_jobs(filter_jobs(records, city=params.get("city")), params.get("keyword", ""))
    limit, offset = params.get("limit", 20), params.get("offset", 0)
    with TestClient(api.create_app(database_config=test_database)) as client:
        response = client.get("/jobs", params=params)
    assert response.status_code == 200
    assert response.json() == {"total": total, "items": expected[offset:offset + limit],
                               "limit": limit, "offset": offset}
    assert len(response.json()["items"]) == length


@pytest.mark.parametrize("city,keyword", [
    ("", ""), ("   ", "   "), ("STRASSE", None), ("οσ", None),
    (None, "strasse"), (None, "ΟΣ"), (None, "%"), (None, "_"),
    (None, "\\"), (None, "' OR 1=1 --"), (None, "工程师 杭州"),
    (None, "url-only-keyword"), ("杭州", "_"),
])
def test_sql_preserves_literal_casefold_and_cross_field_search(test_database, city, keyword):
    records = [
        job(title="Python 工程师", description="含 % _ \\ ' OR 1=1 -- 字符"),
        job("https://example.com/2", title="Straße", city="Straße", description="德语"),
        job("https://example.com/3", title="ΟΣ", city="ος", description="希腊语"),
        job("https://example.com/url-only-keyword", title="其他", city="西安"),
    ]
    store_jobs(records, test_database)
    expected = search_jobs(filter_jobs(records, city=city), keyword or "")
    page = query_database_jobs(test_database, city=city, keyword=keyword, limit=1)
    assert page.total == len(expected)
    assert page.items == expected[:1]  # 筛选在 LIMIT 之前，即使匹配记录在后面。


def test_pages_follow_id_order_without_overlap(test_database):
    records = [job(f"https://example.com/{i}", title=f"岗位{i}") for i in range(9)]
    store_jobs(records, test_database)
    pages = [query_database_jobs(test_database, limit=3, offset=i) for i in (0, 3, 6)]
    assert all(page.total == 9 for page in pages)
    assert [item for page in pages for item in page.items] == records


def test_count_and_page_share_snapshot_during_concurrent_commit(test_database, monkeypatch):
    store_jobs([job()], test_database)
    original = connect_to_database
    observed = {}

    class CursorProxy:
        """COUNT 读完后，另一连接提交记录，模拟两条 SQL 中间的并发写入。"""

        def __init__(self, cursor):
            self.cursor = cursor

        def __enter__(self):
            self.cursor.__enter__()
            return self

        def __exit__(self, *args):
            return self.cursor.__exit__(*args)

        def execute(self, sql, params):
            self.cursor.execute(sql, params)

        def fetchone(self):
            row = self.cursor.fetchone()
            # 在同一请求连接核对隔离级别和只读属性，不能只测 Python 属性。
            self.cursor.execute("SHOW transaction_isolation")
            observed["isolation"] = self.cursor.fetchone()[0]
            self.cursor.execute("SHOW transaction_read_only")
            observed["read_only"] = self.cursor.fetchone()[0]
            # 使用未包装的独立连接，避免并发写入也触发这段模拟钩子。
            with original(test_database) as writer:
                writer.execute(job_repository.INSERT_JOB_SQL,
                               tuple(job("https://example.com/concurrent").values()))
            return row

        def fetchall(self):
            return self.cursor.fetchall()

    class ConnectionProxy:
        def __init__(self, connection):
            object.__setattr__(self, "connection", connection)

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def __setattr__(self, name, value):
            setattr(self.connection, name, value)

        def __enter__(self):
            self.connection.__enter__()
            return self

        def __exit__(self, *args):
            return self.connection.__exit__(*args)

        def cursor(self):
            return CursorProxy(self.connection.cursor())

    monkeypatch.setattr(job_repository, "connect_to_database",
                        lambda config: ConnectionProxy(original(config)))
    page = query_database_jobs(test_database)
    assert page.total == 1 and page.items == [job()]
    assert observed == {"isolation": "repeatable read", "read_only": "on"}
    with original(test_database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM public.jobs").fetchone() == (2,)


def test_only_current_page_is_validated(test_database):
    store_jobs([job()], test_database)
    with connect_to_database(test_database) as connection:
        connection.execute(
            "INSERT INTO public.jobs (title,city,description,source_url) VALUES (%s,%s,%s,%s)",
            ("坏记录", "西安", "   ", "https://example.com/bad"),
        )
    with TestClient(api.create_app(database_config=test_database)) as client:
        assert client.get("/jobs", params={"limit": 1}).json() == {
            "total": 2, "items": [job()], "limit": 1, "offset": 0}
        assert client.get("/jobs", params={"limit": 1, "offset": 1}).status_code == 500
        assert client.get("/jobs", params={"offset": 2}).json() == {
            "total": 2, "items": [], "limit": 20, "offset": 2}
