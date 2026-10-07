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
    assert response.json() == {"total": 2, "items": jobs, "limit": 20, "offset": 0}
    assert file_path.read_bytes() == original_content


def test_returns_success_for_empty_data(tmp_path: Path) -> None:
    file_path = tmp_path / "jobs.json"
    file_path.write_text("[]", encoding="utf-8")

    with TestClient(create_app(file_path)) as client:
        response = client.get("/jobs")

    assert response.status_code == 200
    assert response.json() == {"total": 0, "items": [], "limit": 20, "offset": 0}


def test_does_not_use_default_file_in_startup_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_directory = tmp_path / "data"
    data_directory.mkdir()
    (data_directory / "deduplicated_jobs.json").write_text("[]", encoding="utf-8")
    # 即使旧 JSON 存在，缺少数据库配置也不能静默回退文件。
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CAREERLENS_DB_PASSWORD", raising=False)

    with TestClient(create_app()) as client:
        response = client.get("/jobs")

    assert response.status_code == 503


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
        assert client.get("/jobs").json() == {"total": 0, "items": [], "limit": 20, "offset": 0}
        jobs = [sample_job()]
        # 修改仅限测试的临时文件，用来证明服务没有缓存第一次结果。
        file_path.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
        response = client.get("/jobs")

    assert response.status_code == 200
    assert response.json() == {"total": 1, "items": jobs, "limit": 20, "offset": 0}


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


@pytest.mark.parametrize(("params", "expected_indices"), [
    ({}, [0, 1, 2, 3, 4]),
    ({"city": "杭州"}, [1, 2]),
    ({"city": "杭"}, []),
    ({"city": "SHENZHEN"}, [4]),
    ({"keyword": "python"}, [0, 2]),
    ({"keyword": "FASTAPI"}, [0]),
    ({"keyword": "西安"}, [0, 3]),
    ({"city": "西安", "keyword": "Python"}, [0]),
    ({"city": " 西安 ", "keyword": " pYtHoN "}, [0]),
    ({"city": "", "keyword": ""}, [0, 1, 2, 3, 4]),
    ({"city": "   ", "keyword": "   "}, [0, 1, 2, 3, 4]),
    ({"city": "杭州", "keyword": "   "}, [1, 2]),
    ({"city": "不存在的城市"}, []),
    ({"keyword": "不存在的关键词"}, []),
])
def test_filters_jobs_using_optional_query_parameters(
    tmp_path: Path, params: dict[str, str], expected_indices: list[int]
) -> None:
    # 数据刻意覆盖：同城市不同关键词、同关键词不同城市、描述匹配和英文城市。
    jobs = [
        {**sample_job(), "description": "基于 FastAPI 提供服务"},
        {**sample_job(), "title": "RAG 工程师", "city": "杭州",
         "description": "知识库检索", "source_url": "https://example.com/2"},
        {**sample_job(), "title": "Python 数据工程师", "city": "杭州",
         "description": "数据清洗", "source_url": "https://example.com/3"},
        {**sample_job(), "title": "AI 后端工程师", "city": "西安",
         "description": "部署模型服务", "source_url": "https://example.com/4"},
        {**sample_job(), "title": "NLP 工程师", "city": "Shenzhen",
         "description": "文本分类", "source_url": "https://example.com/5"},
    ]
    file_path = tmp_path / "jobs.json"
    file_path.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
    original_content = file_path.read_bytes()

    with TestClient(create_app(file_path)) as client:
        # params 交给客户端编码，避免把中文和空白手动拼进 URL。
        response = client.get("/jobs", params=params)

    expected = [jobs[index] for index in expected_indices]
    assert response.status_code == 200
    # 同时检查具体岗位、顺序和计数，防止只有数量正确却返回了错误岗位。
    assert response.json() == {"total": len(expected), "items": expected, "limit": 20, "offset": 0}
    assert file_path.read_bytes() == original_content


def test_documents_optional_query_parameters(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "jobs.json")) as client:
        schema = client.get("/openapi.json").json()

    parameters = schema["paths"]["/jobs"]["get"]["parameters"]
    assert {parameter["name"] for parameter in parameters} == {"city", "keyword", "limit", "offset"}
    assert all(parameter["in"] == "query" for parameter in parameters)
    assert all(not parameter["required"] for parameter in parameters)


def test_query_does_not_hide_data_source_errors(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "missing.json")) as client:
        response = client.get("/jobs", params={"city": "不存在的城市"})

    # 无匹配城市不应掩盖数据读取失败：不能提前返回成功的空数组。
    assert response.status_code == 500
    assert response.json() == {"detail": DATA_ERROR_DETAIL}


def test_validates_body_without_reading_or_creating_data_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file_path = tmp_path / "missing.json"

    def fail_if_data_is_read(*args: object, **kwargs: object) -> None:
        pytest.fail("请求体校验不应读取岗位库")

    monkeypatch.setattr("careerlens.api.load_validated_jobs", fail_if_data_is_read)
    submitted_job = {field: f"  {value}  " for field, value in sample_job().items()}
    with TestClient(create_app(file_path)) as client:
        response = client.post("/jobs/validate", json=submitted_job)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == sample_job()
    assert not file_path.exists()


@pytest.mark.parametrize("field", ["title", "city", "description", "source_url"])
def test_rejects_missing_body_field(tmp_path: Path, field: str) -> None:
    job = sample_job()
    del job[field]
    with TestClient(create_app(tmp_path / "missing.json")) as client:
        response = client.post("/jobs/validate", json=job)

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert isinstance(errors, list)
    assert any(error["loc"] == ["body", field] for error in errors)


@pytest.mark.parametrize("field", ["title", "city", "description", "source_url"])
@pytest.mark.parametrize("value", [42, True, None, [], {}])
def test_rejects_non_string_body_field(
    tmp_path: Path, field: str, value: object
) -> None:
    # 错误输入故意不符合 dict[str, str]，用于确认模型不会宽松转换类型。
    job: dict[str, object] = dict(sample_job())
    job[field] = value
    with TestClient(create_app(tmp_path / "missing.json")) as client:
        response = client.post("/jobs/validate", json=job)

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert isinstance(errors, list)
    assert any(error["loc"] == ["body", field] for error in errors)


@pytest.mark.parametrize(("field", "value"), [
    ("title", "   "),
    ("city", "   "),
    ("description", "   "),
    ("source_url", "   "),
    ("source_url", "ftp://example.com/job"),
    ("source_url", "https://"),
    ("source_url", "https://example.com/bad url"),
    ("source_url", "https://[bad"),
])
def test_maps_business_validation_error_to_422(
    tmp_path: Path, field: str, value: str
) -> None:
    job = {**sample_job(), field: value}
    with TestClient(create_app(tmp_path / "missing.json")) as client:
        response = client.post("/jobs/validate", json=job)

    assert response.status_code == 422
    detail = response.json()["detail"]
    # 结构已经通过，失败来自 validate_job；业务错误沿用字符串说明。
    assert isinstance(detail, str)
    assert field in detail


@pytest.mark.parametrize("content", ["", '{"title":', "[]", "null", "42", '"text"'])
def test_rejects_missing_malformed_or_non_object_body(tmp_path: Path, content: str) -> None:
    with TestClient(create_app(tmp_path / "missing.json")) as client:
        response = client.post(
            "/jobs/validate", content=content, headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert isinstance(errors, list)
    assert errors


def test_ignores_extra_fields_in_submitted_job(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "missing.json")) as client:
        response = client.post("/jobs/validate", json={**sample_job(), "company": "演示"})

    assert response.status_code == 200
    assert response.json() == sample_job()


@pytest.mark.parametrize("description", ["有效的新岗位", "   "])
def test_body_validation_does_not_change_stored_jobs(tmp_path: Path, description: str) -> None:
    file_path = tmp_path / "jobs.json"
    file_path.write_text(json.dumps([sample_job()], ensure_ascii=False), encoding="utf-8")
    original_content = file_path.read_bytes()

    with TestClient(create_app(file_path)) as client:
        before = client.get("/jobs").json()
        response = client.post(
            "/jobs/validate",
            json={**sample_job(), "description": description,
                  "source_url": "https://example.com/jobs/new"},
        )
        after = client.get("/jobs").json()

    assert response.status_code == (200 if description.strip() else 422)
    assert before == after == {"total": 1, "items": [sample_job()], "limit": 20, "offset": 0}
    assert file_path.read_bytes() == original_content


def test_documents_required_json_body_and_preserves_existing_routes(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "missing.json")) as client:
        schema = client.get("/openapi.json").json()
        root_response = client.get("/")
        assert client.post("/jobs").status_code == 405

    operation = schema["paths"]["/jobs/validate"]["post"]
    assert operation["requestBody"]["required"] is True
    assert "application/json" in operation["requestBody"]["content"]
    assert "200" in operation["responses"]
    assert "422" in operation["responses"]
    request_schema = schema["components"]["schemas"]["JobValidationRequest"]
    assert set(request_schema["required"]) == {"title", "city", "description", "source_url"}
    assert all(field["type"] == "string" for field in request_schema["properties"].values())
    assert root_response.status_code == 200
    assert root_response.json() == {"Hello": "world!"}
