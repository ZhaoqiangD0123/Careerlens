"""岗位列表查询、筛选和词频统计。"""

from collections import Counter
from collections.abc import Iterable


Job = dict[str, str]

# V0 使用显式关键词表，统计规则容易解释、修改和测试。
ROLE_KEYWORDS = (
    "AI",
    "Python",
    "后端",
    "机器学习",
    "数据",
    "RAG",
    "LLM",
    "测试",
    "搜索",
    "NLP",
    "FastAPI",
    "运维",
)

SKILL_KEYWORDS = (
    "AI",
    "Python",
    "API",
    "FastAPI",
    "RAG",
    "LLM",
    "NLP",
    "大模型",
    "数据清洗",
    "模型训练",
    "模型部署",
    "向量检索",
    "关键词检索",
    "自动化",
    "监控",
)


def search_jobs(jobs: Iterable[Job], keyword: str) -> list[Job]:
    """在岗位名称、城市和描述中进行不区分英文大小写的搜索。"""
    normalized_keyword = keyword.strip().casefold()
    if not normalized_keyword:
        return list(jobs)

    return [
        job
        for job in jobs
        if normalized_keyword
        in " ".join((job["title"], job["city"], job["description"])).casefold()
    ]


def filter_jobs(
    jobs: Iterable[Job],
    *,
    city: str | None = None,
    title_keyword: str | None = None,
) -> list[Job]:
    """按城市精确匹配，并按岗位名称关键词进行包含匹配。"""
    normalized_city = city.strip().casefold() if city else None
    normalized_title = title_keyword.strip().casefold() if title_keyword else None

    result: list[Job] = []
    for job in jobs:
        if normalized_city and job["city"].casefold() != normalized_city:
            continue
        if normalized_title and normalized_title not in job["title"].casefold():
            continue
        result.append(job)
    return result


def _count_keywords(jobs: Iterable[Job], keywords: Iterable[str], fields: tuple[str, ...]) -> dict[str, int]:
    """统计每个关键词出现在多少条岗位中，同一岗位最多计数一次。"""
    counter: Counter[str] = Counter()
    for job in jobs:
        text = " ".join(job[field] for field in fields).casefold()
        for keyword in keywords:
            if keyword.casefold() in text:
                counter[keyword] += 1
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0].casefold())))


def build_job_statistics(jobs: Iterable[Job]) -> dict[str, dict[str, int]]:
    """生成城市、岗位关键词和技能关键词三类统计。"""
    job_list = list(jobs)
    city_counter = Counter(job["city"] for job in job_list)
    city_counts = dict(
        sorted(city_counter.items(), key=lambda item: (-item[1], item[0].casefold()))
    )

    return {
        "cities": city_counts,
        "roles": _count_keywords(job_list, ROLE_KEYWORDS, ("title",)),
        "skills": _count_keywords(
            job_list,
            SKILL_KEYWORDS,
            ("title", "description"),
        ),
    }
