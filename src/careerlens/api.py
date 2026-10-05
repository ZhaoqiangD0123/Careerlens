"""CareerLens 的只读 HTTP 入口：把岗位列表作为 JSON 响应提供。"""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from careerlens.job_files import load_validated_jobs
from careerlens.validate_file import JobFileError


logger = logging.getLogger(__name__)
DATA_ERROR_DETAIL = "岗位数据暂时不可用，请检查服务端数据文件"


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

    @application.get(
        "/jobs",
        response_model=JobListResponse,
        summary="获取已清洗、去重的岗位列表",
        responses={500: {"description": "服务端岗位文件读取或校验失败"}},
    )
    def list_jobs() -> JobListResponse:
        """每次请求读取文件；不写入数据，也不重新执行去重。"""
        # 文件读取是同步操作，普通 def 路由由框架在线程池中执行。
        try:
            jobs = load_validated_jobs(jobs_path)
        except JobFileError as exc:
            # 详细原因只进入服务端日志，响应不泄露本机路径和原始数据。
            logger.exception("岗位数据读取失败")
            raise HTTPException(status_code=500, detail=DATA_ERROR_DETAIL) from exc

        # 响应模型明确字段，FastAPI 将结果序列化为 HTTP JSON 正文。
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
