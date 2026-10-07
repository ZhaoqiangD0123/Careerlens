"""隔离数据库 fixture；必须显式提供专用测试配置，不能连接默认练习库。"""

import os

import pytest

from careerlens.database import DatabaseConfig, connect_to_database


@pytest.fixture
def test_database():
    """每个用例只拥有自己创建的表；未知已存在表不会被自动删除。"""
    keys = ("HOST", "PORT", "NAME", "USER", "PASSWORD")
    if not all(os.environ.get(f"CAREERLENS_TEST_DB_{key}") for key in keys):
        pytest.skip("需通过 scripts/run_database_tests.py 提供独立测试库")
    if not os.environ["CAREERLENS_TEST_DB_NAME"].startswith("careerlens_test_"):
        pytest.fail("只允许 careerlens_test_ 前缀的专用测试库")
    config = DatabaseConfig.from_env({
        f"CAREERLENS_DB_{key}": os.environ[f"CAREERLENS_TEST_DB_{key}"] for key in keys
    })
    with connect_to_database(config) as connection:
        connection.execute("""
            CREATE TABLE public.jobs (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                title TEXT NOT NULL, city TEXT NOT NULL, description TEXT NOT NULL,
                source_url TEXT NOT NULL UNIQUE
            )
        """)
    try:
        yield config
    finally:
        with connect_to_database(config) as connection:
            connection.execute("DROP TABLE public.jobs")
