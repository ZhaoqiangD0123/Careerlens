"""岗位数据库读写；这里处理 SQL，不处理 HTTP 参数或响应。"""

from collections.abc import Sequence
from dataclasses import dataclass

import psycopg

from careerlens.database import (
    DatabaseConfig,
    DatabaseOperationError,
    connect_to_database,
)
from careerlens.validator import REQUIRED_FIELDS, JobValidationError, validate_job


class DatabaseUnavailableError(DatabaseOperationError):
    """连接、认证或超时问题；HTTP 层将其映射为依赖不可用。"""


class DatabaseReadError(DatabaseOperationError):
    """表结构或库内岗位错误；不能当作正常空结果。"""


SELECT_JOBS_SQL = """
    SELECT title, city, description, source_url
    FROM public.jobs
    ORDER BY id
"""

COUNT_JOBS_SQL = "SELECT COUNT(*) FROM public.jobs"
PAGE_JOBS_SQL = "SELECT title, city, description, source_url FROM public.jobs"


@dataclass(frozen=True)
class JobPage:
    """总匹配数与当前页分开保存；total 不是本页长度。"""

    total: int
    items: list[dict[str, str]]
    limit: int
    offset: int


def query_database_jobs(
    config: DatabaseConfig, *, city: str | None = None,
    keyword: str | None = None, limit: int = 20, offset: int = 0,
) -> JobPage:
    """先在 SQL 中筛选，再稳定排序、分页；只校验当前页的内容。"""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit 必须是 1—100 的整数")
    if type(offset) is not int or offset < 0:
        raise ValueError("offset 必须是非负整数")
    conditions: list[str] = []
    parameters: list[str] = []
    if city and city.strip():
        conditions.append(
            "casefold(city COLLATE pg_catalog.pg_unicode_fast) = "
            "casefold(%s::text COLLATE pg_catalog.pg_unicode_fast)"
        )
        parameters.append(city.strip())
    if keyword and keyword.strip():
        # strpos 是字面包含匹配：百分号、下划线和反斜线不是通配符。
        # PostgreSQL 18 的 Unicode 排序规则支持 casefold，而非仅 lower。
        conditions.append(
            "strpos(casefold((title || ' ' || city || ' ' || description) "
            "COLLATE pg_catalog.pg_unicode_fast), "
            "casefold(%s::text COLLATE pg_catalog.pg_unicode_fast)) > 0"
        )
        parameters.append(keyword.strip())
    # 只拼程序定义的 SQL 片段，用户输入始终单独交给驱动绑定。
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    try:
        connection = connect_to_database(config)
    except DatabaseOperationError:
        raise DatabaseUnavailableError("数据库连接不可用") from None
    try:
        with connection:
            # 身份检查的 SELECT 已开启事务。先结束它，再设置新事务属性。
            connection.rollback()
            connection.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
            connection.read_only = True
            with connection.cursor() as cursor:
                # 同一只读快照让 COUNT 与本页不会因中途写入而自相矛盾。
                cursor.execute(COUNT_JOBS_SQL + where, tuple(parameters))
                count_row = cursor.fetchone()
                if count_row is None or len(count_row) != 1:
                    raise DatabaseReadError("岗位总数结构错误")
                total = count_row[0]
                if type(total) is not int or total < 0:
                    raise DatabaseReadError("岗位总数格式错误")
                # 超过总数已经确定为空页。限制传给 SQL 的偏移，避免极大
                # Python 整数溢出 PostgreSQL bigint；响应仍回显原始 offset。
                sql_offset = min(offset, total)
                cursor.execute(
                    PAGE_JOBS_SQL + where + " ORDER BY id ASC LIMIT %s OFFSET %s",
                    (*parameters, limit, sql_offset),
                )
                rows = cursor.fetchall()
        items = []
        for row in rows:
            job = dict(zip(REQUIRED_FIELDS, row, strict=True))
            cleaned = validate_job(job)
            if cleaned != job:
                raise DatabaseReadError("库内岗位尚未完成清洗")
            items.append(cleaned)
        return JobPage(total, items, limit, offset)
    except (psycopg.OperationalError, psycopg.InterfaceError,
            psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
        raise DatabaseUnavailableError("数据库查询暂不可用") from None
    except psycopg.Error:
        raise DatabaseReadError("数据库表结构或查询错误") from None
    except (JobValidationError, TypeError, ValueError):
        raise DatabaseReadError("库内岗位不符合格式") from None


def load_database_jobs(config: DatabaseConfig) -> list[dict[str, str]]:
    """读取全部规范岗位，连接在返回之前关闭；不修改或静默过滤记录。"""
    try:
        connection = connect_to_database(config)
    except DatabaseOperationError:
        # 复用连接层的身份核对与超时，不向 HTTP 层暴露驱动原文。
        raise DatabaseUnavailableError("数据库连接不可用") from None

    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(SELECT_JOBS_SQL)
                rows = cursor.fetchall()
        # 上下文已关闭连接，再将行转换成业务字典；不共享全局连接。
        jobs = []
        for row in rows:
            # strict=True 防止结构变化时悄悄漏字段；id 只用于 SQL 排序。
            job = dict(zip(REQUIRED_FIELDS, row, strict=True))
            cleaned = validate_job(job)
            if cleaned != job:
                raise DatabaseReadError("库内岗位尚未完成清洗")
            jobs.append(cleaned)
        return jobs
    except (psycopg.OperationalError, psycopg.InterfaceError,
            psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
        raise DatabaseUnavailableError("数据库查询暂不可用") from None
    except psycopg.Error:
        # 缺表、错误列名、SQL 错误等属于服务端错误，不伪装成无匹配。
        raise DatabaseReadError("数据库表结构或查询错误") from None
    except (JobValidationError, TypeError, ValueError):
        raise DatabaseReadError("库内岗位不符合格式") from None


@dataclass(frozen=True)
class ImportSummary:
    """提交成功后才能交付给调用者的导入结果。"""

    input_count: int
    inserted_count: int
    skipped_count: int
    total_count: int


INSERT_JOB_SQL = """
    INSERT INTO public.jobs (title, city, description, source_url)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (source_url) DO NOTHING
    RETURNING id
"""


def store_jobs(
    jobs: Sequence[dict[str, str]], config: DatabaseConfig
) -> ImportSummary:
    """仅接收已完成前置检查的记录，不自动建表、不修改已有记录。"""
    inserted = 0
    try:
        # 整个循环共用一个事务：正常退出提交，任意异常则回滚并关闭。
        with connect_to_database(config) as connection:
            with connection.cursor() as cursor:
                for job in jobs:
                    # 数据单独传给驱动；标题里的引号不是 SQL 语法。
                    cursor.execute(
                        INSERT_JOB_SQL,
                        tuple(job[field] for field in REQUIRED_FIELDS),
                    )
                    # 新增时 RETURNING 返回 id；冲突跳过时不返回任何行。
                    if cursor.fetchone() is not None:
                        inserted += 1
                cursor.execute("SELECT COUNT(*) FROM public.jobs")
                total = cursor.fetchone()[0]
        # 必须等外层 with 完成提交后才返回，不能提前报告成功。
        return ImportSummary(len(jobs), inserted, len(jobs) - inserted, total)
    except psycopg.Error as exc:
        if exc.sqlstate == "42P01":
            message = "岗位表不存在，请先在目标练习库创建 public.jobs"
        elif exc.sqlstate == "42P10":
            message = "岗位表缺少 source_url 唯一约束，请核对表结构"
        else:
            message = (
                "数据库导入未确认成功，本批事务发生错误；"
                "若连接在提交时中断，请先核对数据库状态再安全重跑"
            )
        raise DatabaseOperationError(message) from None
