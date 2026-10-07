"""启动本机临时 PostgreSQL 测试容器，结束后仅移除自己创建的容器。"""

import os
import re
import secrets
import subprocess
import sys
import time
import uuid
from pathlib import Path


def main() -> int:
    """真实 TCP 测试与用户练习库隔离，密码不打印、不写入文件。"""
    root = Path(__file__).resolve().parents[1]
    tag = uuid.uuid4().hex[:12]
    container_name = f"careerlens-test-{tag}"
    db_name = f"careerlens_test_{tag}"
    password = secrets.token_urlsafe(32)
    container_id = None
    exit_code = 1
    env = {**os.environ, "POSTGRES_PASSWORD": password}

    def docker(*args: str) -> str:
        result = subprocess.run(
            ["docker", *args], env=env, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        if result.returncode:
            # 只给出经过脱敏的工具错误，不打印完整容器配置。
            raise RuntimeError(result.stderr.replace(password, "[已隐藏]").strip())
        return result.stdout.strip()

    try:
        if docker("info", "--format", "{{.OSType}}") != "linux":
            raise RuntimeError("需先启动 Docker Desktop 的 Linux 引擎")
        container_id = docker(
            "run", "--detach", "--name", container_name,
            "--env", "POSTGRES_PASSWORD", "--env", "POSTGRES_USER=careerlens_test",
            "--env", f"POSTGRES_DB={db_name}",
            "--publish", "127.0.0.1::5432",
            # 测试文件放内存，不创建持久数据卷，不挂载用户目录。
            "--tmpfs", "/var/lib/postgresql:rw", "postgres:18",
        )
        if not re.fullmatch(r"[0-9a-f]{64}", container_id):
            raise RuntimeError("创建结果不是可核对的容器 ID，停止测试")
        port = docker(
            "inspect", "--format",
            '{{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostPort}}',
            container_id,
        )
        test_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        for key, value in {
            "HOST": "127.0.0.1", "PORT": port, "NAME": db_name,
            "USER": "careerlens_test", "PASSWORD": password,
        }.items():
            test_env[f"CAREERLENS_TEST_DB_{key}"] = value
        # 直接检查 TCP 连接，而不是把本地 socket 就绪当成认证成功。
        import psycopg

        deadline = time.monotonic() + 45
        while True:
            try:
                with psycopg.connect(
                    host="127.0.0.1", port=int(port), dbname=db_name,
                    user="careerlens_test", password=password, connect_timeout=2,
                ) as connection:
                    connection.execute("SELECT 1")
                break
            except psycopg.OperationalError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("临时测试数据库未能就绪，请核对 Docker") from None
                time.sleep(0.5)
        print("临时数据库已通过本机 TCP 认证；开始隔离集成测试", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q",
             "tests/test_import_jobs_integration.py", "tests/test_api_database_integration.py",
             "tests/test_job_pagination_integration.py"],
            cwd=root, env=test_env, timeout=180,
        )
        exit_code = result.returncode
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"数据库测试未完成：{str(exc).replace(password, '[已隐藏]')}", file=sys.stderr)
    finally:
        # 必须使用本次创建且格式已核对的准确 ID，不按模糊名称批量删除。
        if container_id and re.fullmatch(r"[0-9a-f]{64}", container_id):
            try:
                docker("rm", "--force", container_id)
                print("本次临时测试容器已移除；练习容器与数据未改动", flush=True)
            except (RuntimeError, OSError, subprocess.TimeoutExpired):
                print(f"临时容器清理失败，请核对 {container_name}", file=sys.stderr)
                exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
