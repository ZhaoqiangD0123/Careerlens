"""CareerLens 的 HTTP 入口：查询岗位及校验提交的数据，不持久保存。"""

import logging
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, StrictStr

from careerlens.catalog import filter_jobs, search_jobs
from careerlens.job_files import load_validated_jobs
from careerlens.validate_file import JobFileError
from careerlens.validator import JobValidationError, validate_job


logger = logging.getLogger(__name__)
DATA_ERROR_DETAIL = "岗位数据暂时不可用，请检查服务端数据文件"


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


def create_app(data_path: Path | None = None) -> FastAPI:
    """创建应用；测试传入临时数据路径，不依赖或改动正式数据。"""
    # 默认路径相对于启动目录，因此应在项目根目录启动服务。
    source_path = data_path if data_path is not None else Path("data/deduplicated_jobs.json")
    jobs_path = source_path.resolve()
    application = FastAPI(title="CareerLens", version="0.1.0")

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
        responses={500: {"description": "服务端岗位文件读取或校验失败"}},
    )
    def list_jobs(
        city: Annotated[str | None, Query(description="城市精确匹配，空白时不限制")] = None,
        keyword: Annotated[
            str | None, Query(description="搜索岗位名称、城市与描述，空白时不限制")
        ] = None,
    ) -> JobListResponse:
        """每次请求读取文件；不写入数据，也不重新执行去重。"""
        # 文件读取是同步操作，普通 def 路由由框架在线程池中执行。
        try:
            jobs = load_validated_jobs(jobs_path)
        except JobFileError as exc:
            # 详细原因只进入服务端日志，响应不泄露本机路径和原始数据。
            logger.exception("岗位数据读取失败")
            raise HTTPException(status_code=500, detail=DATA_ERROR_DETAIL) from exc

        # 复用 CLI 的规则：先按城市筛选，再在结果内搜索，因此是 AND。
        # 两个业务函数会处理首尾空格与英文大小写，不在 HTTP 层重复实现。
        jobs = search_jobs(filter_jobs(jobs, city=city), keyword or "")

        # 数量取最终结果，而不是文件中的原始数量；查询不改写数据源。
        return JobListResponse(
            total=len(jobs), items=[JobResponse(**job) for job in jobs]
        )
    #添加主界面
    @application.get("/")
    def read_root():
        return {"Hello":"world!"}
    
    
    
    return application


# Uvicorn 使用 careerlens.api:app 找到并运行这个应用对象。
app = create_app()
