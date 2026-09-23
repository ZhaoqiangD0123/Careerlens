"""岗位查询、筛选与统计测试。"""

from careerlens.catalog import build_job_statistics, filter_jobs, search_jobs


def sample_jobs() -> list[dict[str, str]]:
    return [
        {
            "title": "Python 后端工程师",
            "city": "西安",
            "description": "使用 FastAPI 开发 AI 服务",
            "source_url": "https://example.com/1",
        },
        {
            "title": "RAG 应用工程师",
            "city": "杭州",
            "description": "负责向量检索和大模型应用",
            "source_url": "https://example.com/2",
        },
        {
            "title": "Python 测试工程师",
            "city": "西安",
            "description": "负责接口自动化测试",
            "source_url": "https://example.com/3",
        },
    ]


def test_searches_title_city_and_description() -> None:
    jobs = sample_jobs()

    assert len(search_jobs(jobs, "python")) == 2
    assert len(search_jobs(jobs, "杭州")) == 1
    assert len(search_jobs(jobs, "向量检索")) == 1


def test_filters_by_city_and_title_together() -> None:
    result = filter_jobs(sample_jobs(), city="西安", title_keyword="测试")

    assert len(result) == 1
    assert result[0]["title"] == "Python 测试工程师"


def test_builds_city_role_and_skill_statistics() -> None:
    statistics = build_job_statistics(sample_jobs())

    assert statistics["cities"] == {"西安": 2, "杭州": 1}
    assert statistics["roles"]["Python"] == 2
    assert statistics["skills"]["AI"] == 1
    assert statistics["skills"]["向量检索"] == 1
