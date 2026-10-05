"""通过 HTTP 公共接口检查岗位查询契约，不访问真实网络端口。"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from careerlens.api import DATA_ERROR_DETAIL, create_app


def sample_job() -> dict[str, str]:
    """提供合法岗位，避免测试依赖项目中的演示数据。"""
    return {
        "title": "Python 后端工程师",
        "city": "西安",
        "description": "开发 AI 应用",
        "source_url": "https://example.com/jobs/1",
    }


def test_returns_job_list_without_changing_file(tmp_path: Path) -> None:
    file_path = tmp_path / "jobs.json"
    jobs = [sample_job(), {
        **sample_job(),
        "title": "RAG 应用工程师",
        "city": "杭州",
        "source_url": "https://example.com/jobs/2",
    }]
    file_path.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
    original_content = file_path.read_bytes()

    with TestClient(create_app(file_path)) as client:
        response = client.get("/jobs")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"total": 2, "items": jobs}
    assert file_path.read_bytes() == original_content


def test_returns_success_for_empty_data(tmp_path: Path) -> None:
    file_path = tmp_path / "jobs.json"
    file_path.write_text("[]", encoding="utf-8")

    with TestClient(create_app(file_path)) as client:
        response = client.get("/jobs")

    assert response.status_code == 200
    assert response.json() == {"total": 0, "items": []}


def test_uses_default_file_in_startup_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_directory = tmp_path / "data"
    data_directory.mkdir()
    (data_directory / "deduplicated_jobs.json").write_text("[]", encoding="utf-8")
    # 模拟用户在项目根目录启动，确认默认数据源的约定没有写错。
    monkeypatch.chdir(tmp_path)

    with TestClient(create_app()) as client:
        response = client.get("/jobs")

    assert response.status_code == 200
    assert response.json() == {"total": 0, "items": []}


def test_returns_500_for_missing_file(tmp_path: Path) -> None:
    file_path = tmp_path / "missing.json"

    with TestClient(create_app(file_path)) as client:
        response = client.get("/jobs")

    assert response.status_code == 500
    assert response.json() == {"detail": DATA_ERROR_DETAIL}
    assert str(file_path) not in response.text
    assert not file_path.exists()


@pytest.mark.parametrize("content", [
    '{"title":',
    '{}',
    json.dumps([sample_job(), {"title": "缺少字段"}], ensure_ascii=False),
    json.dumps([{**sample_job(), "description": "   "}], ensure_ascii=False),
    json.dumps([{**sample_job(), "source_url": "ftp://example.com/1"}]),
])
def test_returns_500_instead_of_partial_data(tmp_path: Path, content: str) -> None:
    file_path = tmp_path / "jobs.json"
    file_path.write_text(content, encoding="utf-8")

    with TestClient(create_app(file_path)) as client:
        response = client.get("/jobs")

    # 混有坏岗位时不能只返回合法部分并假装查询成功。
    assert response.status_code == 500
    assert response.json() == {"detail": DATA_ERROR_DETAIL}


def test_returns_500_for_invalid_utf8(tmp_path: Path) -> None:
    file_path = tmp_path / "jobs.json"
    file_path.write_bytes(b"\xff\xfe")

    with TestClient(create_app(file_path)) as client:
        response = client.get("/jobs")

    assert response.status_code == 500
    assert response.json() == {"detail": DATA_ERROR_DETAIL}


def test_reads_file_again_on_each_request(tmp_path: Path) -> None:
    file_path = tmp_path / "jobs.json"
    file_path.write_text("[]", encoding="utf-8")

    with TestClient(create_app(file_path)) as client:
        assert client.get("/jobs").json() == {"total": 0, "items": []}
        jobs = [sample_job()]
        # 修改仅限测试的临时文件，用来证明服务没有缓存第一次结果。
        file_path.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
        response = client.get("/jobs")

    assert response.status_code == 200
    assert response.json() == {"total": 1, "items": jobs}


def test_provides_docs_and_handles_wrong_requests(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "jobs.json")) as client:
        assert client.get("/unknown").status_code == 404
        assert client.post("/jobs").status_code == 405
        assert client.get("/docs").status_code == 200
        response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert "get" in schema["paths"]["/jobs"]
    assert "post" not in schema["paths"]["/jobs"]
    assert "500" in schema["paths"]["/jobs"]["get"]["responses"]
    assert set(schema["components"]["schemas"]["JobResponse"]["properties"]) == {
        "title", "city", "description", "source_url"
    }
