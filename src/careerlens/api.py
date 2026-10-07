"""CareerLens 的 HTTP 入口：查询岗位及校验提交的数据，不持久保存。"""

import logging
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, StrictStr

from careerlens.catalog import filter_jobs, search_jobs
from careerlens.database import DatabaseConfig, DatabaseConfigurationError
from careerlens.job_files import load_validated_jobs
from careerlens.job_repository import (
    DatabaseReadError, DatabaseUnavailableError, JobPage, query_database_jobs,
)
from careerlens.validate_file import JobFileError
from careerlens.validator import JobValidationError, validate_job


logger = logging.getLogger(__name__)
DATA_ERROR_DETAIL = "岗位数据暂时不可用，请检查服务端数据文件"
DATABASE_ERROR_DETAIL = "岗位数据异常，请检查服务端数据库"
DATABASE_UNAVAILABLE_DETAIL = "岗位数据库暂时不可用，请检查服务端配置与数据库连接"


class JobValidationRequest(BaseModel):
    """接口输入结构；岗位内容是否合法仍交给已有业务函数判断。"""

    # 与 validate_job 保持一致：额外字段忽略，只处理四个必填字段。
    model_config = ConfigDict(extra="ignore")

    # 严格字符串拒绝数字、布尔值、数组等，避免转换后掩盖输入错误。
    title: StrictStr
    city: StrictStr
    description: StrictStr
    source_url: StrictStr


class JobResponse(BaseModel):
    """声明岗位响应的四个字段，让接口文档也能展示这个约定。"""

    title: str
    city: str
    description: str
    source_url: str


class JobListResponse(BaseModel):
    """一次岗位列表请求返回的结构；不负责清洗或去重。"""

    total: int
    items: list[JobResponse]
    limit: int
    offset: int


def create_app(
    data_path: Path | None = None, *, database_config: DatabaseConfig | None = None
) -> FastAPI:
    """默认读数据库；测试可显式指定文件或数据库配置，不自动回退。"""
    if data_path is not None and database_config is not None:
        raise ValueError("文件与数据库数据源不能同时指定")
    jobs_path = data_path.resolve() if data_path is not None else None
    application = FastAPI(title="CareerLens", version="0.1.0")

    def get_job_page(
        city: Annotated[str | None, Query(description="城市精确匹配，空白时不限制")] = None,
        keyword: Annotated[
            str | None, Query(description="搜索岗位名称、城市与描述，空白时不限制")
        ] = None,
        limit: Annotated[int, Query(ge=1, le=100, description="每页最多条数")] = 20,
        offset: Annotated[int, Query(ge=0, description="跳过匹配记录的条数，不是 id")] = 0,
    ) -> JobPage:
        """参数在本依赖执行前校验；不合法时返回 422，不连接数据库。"""
        if jobs_path is not None:
            # 显式文件模式保留旧用例；不是数据库故障时的隐式备用数据。
            try:
                jobs = load_validated_jobs(jobs_path)
                jobs = search_jobs(filter_jobs(jobs, city=city), keyword or "")
                return JobPage(len(jobs), jobs[offset:offset + limit], limit, offset)
            except JobFileError:
                logger.error("岗位文件读取失败")
                raise HTTPException(status_code=500, detail=DATA_ERROR_DETAIL) from None
        try:
            config = database_config or DatabaseConfig.from_env()
            return query_database_jobs(config, city=city, keyword=keyword,
                                       limit=limit, offset=offset)
        except (DatabaseConfigurationError, DatabaseUnavailableError):
            # 只记录固定类别，不使用 logger.exception 暴露原始异常链。
            logger.warning("岗位数据库配置或连接不可用")
            raise HTTPException(
                status_code=503, detail=DATABASE_UNAVAILABLE_DETAIL
            ) from None
        except DatabaseReadError:
            logger.error("岗位数据库结构或数据错误")
            raise HTTPException(status_code=500, detail=DATABASE_ERROR_DETAIL) from None

    @application.post(
        "/jobs/validate",
        response_model=JobResponse,
        summary="校验并清洗一条岗位，不保存",
        responses={422: {"description": "输入结构或岗位内容不符合规则"}},
    )
    def validate_submitted_job(job: JobValidationRequest) -> JobResponse:
        """只处理请求体，不读取岗位库，也不把校验成功当作入库成功。"""
        # 能进入这里，表示框架已完成 JSON、必填字段与字符串类型检查。
        # model_dump 把输入模型转换成字典，复用 CLI 的同一套岗位规则。
        try:
            cleaned_job = validate_job(job.model_dump())
        except JobValidationError as exc:
            # 用户填错内容属于客户端输入问题，不应误报成服务端 500。
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        # 成功只返回清洗结果；没有文件写入、去重或创建岗位的动作。
        return JobResponse(**cleaned_job)

    @application.get(
        "/jobs",
        response_model=JobListResponse,
        summary="获取已清洗、去重的岗位列表",
        responses={
            422: {"description": "查询参数类型或范围不合法"},
            500: {"description": "服务端岗位结构或数据错误"},
            503: {"description": "数据库配置、连接不可用或查询超时"},
        },
    )
    def list_jobs(
        page: Annotated[JobPage, Depends(get_job_page)],
    ) -> JobListResponse:
        """仓储负责 SQL 查询，本路由只将分页结果映射为 HTTP 响应。"""
        return JobListResponse(
            total=page.total, items=[JobResponse(**job) for job in page.items],
            limit=page.limit, offset=page.offset,
        )
    #添加主界面
    @application.get("/")
    def read_root():
        return {"Hello":"world!"}
    
    
    
    return application


# Uvicorn 使用 careerlens.api:app 找到并运行这个应用对象。
app = create_app()
