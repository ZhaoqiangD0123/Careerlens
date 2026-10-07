"""真实 PostgreSQL 与 HTTP 查询；只使用 conftest 的专用临时测试库。"""

import json
import shutil
import subprocess
import threading
import time
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

import pytest
import uvicorn
from fastapi.testclient import TestClient

from careerlens import api
from careerlens.database import connect_to_database
from careerlens.job_repository import load_database_jobs, store_jobs


ROOT = Path(__file__).resolve().parents[1]


def job(url="https://example.com/1", title="Python 工程师", city="杭州", description="FastAPI 服务"):
    return dict(title=title, city=city, description=description, source_url=url)


def set_database_environment(monkeypatch, config) -> None:
    for key, value in {"HOST": config.host, "PORT": str(config.port), "NAME": config.name,
                       "USER": config.user, "PASSWORD": config.password}.items():
        monkeypatch.setenv(f"CAREERLENS_DB_{key}", value)


def test_default_app_really_reads_database_and_not_file(test_database, monkeypatch) -> None:
    records = [job(), job("https://example.com/2", city="西安")]
    store_jobs(records, test_database)
    set_database_environment(monkeypatch, test_database)
    monkeypatch.setattr(api, "load_validated_jobs", lambda *_: pytest.fail("默认不应读取文件"))
    with TestClient(api.create_app()) as client:
        assert client.get("/jobs").json() == {"total": 2, "items": records, "limit": 20, "offset": 0}
        assert client.get("/jobs", params={"city": "杭州", "keyword": "python"}).json() == {
            "total": 1, "items": [records[0]], "limit": 20, "offset": 0
        }
        new = job("https://example.com/3", "RAG 工程师")
        store_jobs([new], test_database)
        # 第二次请求可看到之后已提交的数据，证明未缓存首次查询结果。
        assert client.get("/jobs").json() == {"total": 3, "items": records + [new], "limit": 20, "offset": 0}


def test_empty_database_and_validation_do_not_write(test_database) -> None:
    with TestClient(api.create_app(database_config=test_database)) as client:
        assert client.get("/jobs").json() == {"total": 0, "items": [], "limit": 20, "offset": 0}
        assert client.post("/jobs/validate", json=job()).status_code == 200
        assert client.get("/jobs").json() == {"total": 0, "items": [], "limit": 20, "offset": 0}


@pytest.mark.parametrize("description", ["   ", " 前后有空格 "])
def test_bad_database_record_fails_whole_response(test_database, description) -> None:
    store_jobs([job()], test_database)
    with connect_to_database(test_database) as connection:
        # 只在隔离表模拟手工 SQL 绕过 Python 规则：NOT NULL 不会拒绝空白。
        connection.execute(
            "INSERT INTO public.jobs (title, city, description, source_url) VALUES (%s,%s,%s,%s)",
            ("坏记录", "西安", description, "https://example.com/bad"),
        )
    with TestClient(api.create_app(database_config=test_database)) as client:
        assert client.get("/jobs", params={"city": "杭州"}).status_code == 200
        assert client.get("/jobs", params={"limit": 1}).status_code == 200
        response = client.get("/jobs")
    assert response.status_code == 500
    assert response.json() == {"detail": api.DATABASE_ERROR_DETAIL}
    with connect_to_database(test_database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM public.jobs").fetchone()[0] == 2


def test_wrong_password_is_503_but_other_routes_still_work(test_database) -> None:
    config = replace(test_database, password="intentionally-wrong-test-password")
    with TestClient(api.create_app(database_config=config)) as client:
        response = client.get("/jobs")
        assert client.get("/").json() == {"Hello": "world!"}
        assert client.post("/jobs/validate", json=job()).status_code == 200
    assert response.status_code == 503
    assert response.json() == {"detail": api.DATABASE_UNAVAILABLE_DETAIL}


def test_missing_table_returns_500(test_database) -> None:
    # 临时改名而非删除，finally 恢复，fixture 仍只清理自己创建的表。
    with connect_to_database(test_database) as connection:
        connection.execute("ALTER TABLE public.jobs RENAME TO jobs_test_hidden")
    try:
        with TestClient(api.create_app(database_config=test_database)) as client:
            assert client.get("/jobs").status_code == 500
    finally:
        with connect_to_database(test_database) as connection:
            connection.execute("ALTER TABLE public.jobs_test_hidden RENAME TO jobs")


def test_query_timeout_is_503_without_sensitive_logs(test_database, monkeypatch, caplog) -> None:
    # 只让隔离数据库执行慢查询，毫秒级超时；不锁住用户练习表。
    monkeypatch.setattr("careerlens.job_repository.COUNT_JOBS_SQL",
                        "SELECT COUNT(*) FROM public.jobs CROSS JOIN pg_sleep(0.1)")
    original = connect_to_database

    def short_timeout(config):
        connection = original(config)
        connection.execute("SET statement_timeout = 10")
        connection.commit()  # 保留会话设置，仓储结束身份事务时不会撤销它。
        return connection

    monkeypatch.setattr("careerlens.job_repository.connect_to_database", short_timeout)
    with TestClient(api.create_app(database_config=test_database)) as client:
        response = client.get("/jobs")
    assert response.status_code == 503
    assert test_database.password not in response.text + caplog.text


def test_uncommitted_record_is_not_visible(test_database) -> None:
    with connect_to_database(test_database) as pending:
        pending.execute(
            "INSERT INTO public.jobs (title, city, description, source_url) VALUES (%s,%s,%s,%s)",
            tuple(job().values()),
        )
        with TestClient(api.create_app(database_config=test_database)) as client:
            assert client.get("/jobs").json() == {"total": 0, "items": [], "limit": 20, "offset": 0}
    assert load_database_jobs(test_database) == [job()]


def test_real_http_port_queries_83_jobs_without_modifying_data(test_database) -> None:
    source = ROOT / "data" / "deduplicated_jobs.json"
    before = source.read_bytes()
    records = json.loads(before)
    store_jobs(records, test_database)
    server = uvicorn.Server(uvicorn.Config(
        api.create_app(database_config=test_database), host="127.0.0.1", port=0,
        log_level="warning", access_log=False,
    ))
    # 端口 0 让系统分配空闲端口，不占用用户的 8000。
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                pytest.fail("临时 HTTP 服务未就绪")
            time.sleep(0.05)
        port = server.servers[0].sockets[0].getsockname()[1]
        opener = build_opener(ProxyHandler({}))
        for params, count in [({}, 83), ({"city": "杭州"}, 17),
                              ({"keyword": "FastAPI"}, 13),
                              ({"city": " 杭州 ", "keyword": " fAsTaPi "}, 3),
                              ({"keyword": "不存在的关键词"}, 0)]:
            with opener.open(f"http://127.0.0.1:{port}/jobs?{urlencode(params)}", timeout=10) as response:
                payload = json.load(response)
                assert response.status == 200
                assert payload["total"] == count
                assert len(payload["items"]) == min(count, 20)
                assert (payload["limit"], payload["offset"]) == (20, 0)
                assert all(set(item) == {"title", "city", "description", "source_url"}
                           for item in payload["items"])
                if not params:
                    assert payload["items"] == records[:20]
        # 真实 HTTP POST 校验仍不保存，库内全部字段保持原样。
        request = Request(f"http://127.0.0.1:{port}/jobs/validate",
                          data=json.dumps(job()).encode("utf-8"),
                          headers={"Content-Type": "application/json"}, method="POST")
        with opener.open(request, timeout=10) as response:
            assert response.status == 200
        # 在真实 TCP 响应上执行集合后置脚本；不声称已完成 Apifox 界面导入。
        node = shutil.which("node")
        if node:
            cases = []
            for filename in ("careerlens.postman_collection.json",
                             "careerlens.query.postman_collection.json",
                             "careerlens.validation.postman_collection.json",
                             "careerlens.pagination.postman_collection.json"):
                collection = json.loads((ROOT / "docs" / filename).read_text(encoding="utf-8"))
                for item in collection["item"]:
                    config = item["request"]
                    url = config["url"]["raw"].replace("{{baseUrl}}", f"http://127.0.0.1:{port}")
                    body = config.get("body", {}).get("raw")
                    request = Request(url, method=config["method"],
                                      headers={h["key"]: h["value"] for h in config.get("header", [])},
                                      data=body.encode("utf-8") if body is not None else None)
                    try:
                        response = opener.open(request, timeout=10)
                    except HTTPError as error:
                        response = error  # 404/405/422 也是需要检查的真实响应。
                    with response:
                        cases.append({"name": item["name"], "status": response.code,
                                      "headers": {k.lower(): v for k, v in response.headers.items()},
                                      "body": response.read().decode("utf-8"),
                                      "script": "\n".join(event["script"]["exec"][i]
                                          for event in item["event"] if event["listen"] == "test"
                                          for i in range(len(event["script"]["exec"])))})
            result = subprocess.run([node, str(ROOT / "scripts/check_postman_scripts.cjs")],
                                    input=json.dumps(cases), text=True, encoding="utf-8",
                                    capture_output=True, timeout=15)
            assert result.returncode == 0, result.stderr
            counts = json.loads(result.stdout)
            assert counts["requests"] == 30
            print(f"真实 HTTP 集合验证：{counts['requests']} 请求，{counts['assertions']} 后置断言")
        else:
            import warnings
            warnings.warn("未找到 Node.js；真实 HTTP 已测，集合 JavaScript 断言尚未执行")
        assert load_database_jobs(test_database) == records
        assert source.read_bytes() == before
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        if thread.is_alive():
            server.force_exit = True
            thread.join(timeout=5)
        assert not thread.is_alive(), "临时 HTTP 服务未停止"
