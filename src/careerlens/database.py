"""本机 PostgreSQL 连接配置，不在源码或错误日志中保存密码。"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

import psycopg


class DatabaseConfigurationError(ValueError):
    """数据库连接配置缺失或不符合当前本机练习边界。"""


class DatabasePasswordRequired(DatabaseConfigurationError):
    """需要用户在本机提供数据库密码。"""


class DatabaseOperationError(RuntimeError):
    """数据库操作失败；对外只提供不含凭据的错误说明。"""


@dataclass(frozen=True)
class DatabaseConfig:
    """密码不参与 repr，避免测试报告或调试输出意外回显。"""

    password: str = field(repr=False)
    host: str = "127.0.0.1"
    port: int = 5433
    name: str = "careerlens_learning"
    user: str = "careerlens"

    def __post_init__(self) -> None:
        # 第一遍只连接本机；不允许意外把练习密码发送到远程地址。
        if self.host not in {"127.0.0.1", "localhost", "::1"}:
            raise DatabaseConfigurationError("当前只支持本机数据库地址")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise DatabaseConfigurationError("数据库端口必须为 1—65535 的整数")
        if not self.name.strip() or not self.user.strip():
            raise DatabaseConfigurationError("数据库名称和用户名不能为空")
        if not self.password:
            raise DatabasePasswordRequired("请在本机提供数据库密码")

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        password: str | None = None,
    ) -> "DatabaseConfig":
        """读取进程环境变量；可传入仅保存在内存中的提示框密码。"""
        values = os.environ if environ is None else environ
        try:
            port = int(values.get("CAREERLENS_DB_PORT", "5433"))
        except ValueError:
            raise DatabaseConfigurationError("数据库端口必须为整数") from None
        return cls(
            host=values.get("CAREERLENS_DB_HOST", "127.0.0.1").strip(),
            port=port,
            name=values.get("CAREERLENS_DB_NAME", "careerlens_learning").strip(),
            user=values.get("CAREERLENS_DB_USER", "careerlens").strip(),
            password=(
                values.get("CAREERLENS_DB_PASSWORD", "")
                if password is None else password
            ),
        )


def connect_to_database(config: DatabaseConfig) -> psycopg.Connection:
    """创建有超时的连接并核对身份；调用者负责用 with 管理事务。"""
    try:
        connection = psycopg.connect(
            host=config.host,
            port=config.port,
            dbname=config.name,
            user=config.user,
            password=config.password,
            connect_timeout=5,
            application_name="careerlens-import",
            # 不沿用外部 PGOPTIONS；查询/等待锁也有上限，避免无限挂起。
            options="-c statement_timeout=15000 -c lock_timeout=5000",
        )
        try:
            identity = connection.execute(
                "SELECT current_database(), session_user"
            ).fetchone()
            if identity != (config.name, config.user):
                raise DatabaseOperationError("数据库身份与配置不一致，已停止操作")
        except BaseException:
            # 核对阶段失败也必须关闭连接，不能遗留打开的事务。
            connection.close()
            raise
        return connection
    except psycopg.Error:
        # 原始驱动错误可能带连接细节，不回显它或异常链。
        raise DatabaseOperationError(
            "数据库连接或身份核对失败，请检查 Docker、端口、库名、用户名和密码"
        ) from None
