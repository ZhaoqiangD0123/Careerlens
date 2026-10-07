"""连接配置与凭据不回显测试；这些测试不需要真实数据库。"""

from unittest.mock import Mock

import psycopg
import pytest

from careerlens import database
from careerlens.database import (
    DatabaseConfig, DatabaseConfigurationError, DatabaseOperationError,
    DatabasePasswordRequired, connect_to_database,
)


def test_reads_defaults_and_hides_password_in_repr() -> None:
    config = DatabaseConfig.from_env({"CAREERLENS_DB_PASSWORD": "test-only-secret"})
    assert (config.host, config.port, config.name, config.user) == (
        "127.0.0.1", 5433, "careerlens_learning", "careerlens"
    )
    assert "test-only-secret" not in repr(config)


def test_reads_explicit_environment_and_prompt_password() -> None:
    config = DatabaseConfig.from_env({
        "CAREERLENS_DB_HOST": " localhost ", "CAREERLENS_DB_PORT": "5434",
        "CAREERLENS_DB_NAME": " lesson ", "CAREERLENS_DB_USER": " learner ",
    }, password="test-only-secret")
    assert (config.host, config.port, config.name, config.user) == (
        "localhost", 5434, "lesson", "learner"
    )


@pytest.mark.parametrize("port", ["", "text", "0", "65536", "-1"])
def test_rejects_invalid_ports(port: str) -> None:
    with pytest.raises(DatabaseConfigurationError, match="端口"):
        DatabaseConfig.from_env({"CAREERLENS_DB_PORT": port,
                                 "CAREERLENS_DB_PASSWORD": "test-only-secret"})


@pytest.mark.parametrize("key,value", [
    ("CAREERLENS_DB_HOST", "remote.example.com"),
    ("CAREERLENS_DB_HOST", ""),
    ("CAREERLENS_DB_NAME", " "),
    ("CAREERLENS_DB_USER", " "),
])
def test_rejects_unsafe_or_empty_configuration(key: str, value: str) -> None:
    with pytest.raises(DatabaseConfigurationError):
        DatabaseConfig.from_env({key: value, "CAREERLENS_DB_PASSWORD": "secret"})


def test_requires_password() -> None:
    with pytest.raises(DatabasePasswordRequired):
        DatabaseConfig.from_env({})


def test_checks_identity_and_uses_explicit_connection_parameters(monkeypatch) -> None:
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = (
        "careerlens_learning", "careerlens"
    )
    factory = Mock(return_value=connection)
    monkeypatch.setattr(database.psycopg, "connect", factory)
    assert connect_to_database(DatabaseConfig(password="secret")) is connection
    assert factory.call_args.kwargs["connect_timeout"] == 5
    assert factory.call_args.kwargs["dbname"] == "careerlens_learning"
    connection.close.assert_not_called()


def test_closes_connection_on_identity_mismatch(monkeypatch) -> None:
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = ("other", "other")
    monkeypatch.setattr(database.psycopg, "connect", Mock(return_value=connection))
    with pytest.raises(DatabaseOperationError, match="身份"):
        connect_to_database(DatabaseConfig(password="secret"))
    connection.close.assert_called_once()


def test_does_not_expose_driver_error_or_secret(monkeypatch) -> None:
    monkeypatch.setattr(database.psycopg, "connect", Mock(
        side_effect=psycopg.OperationalError("driver contains test-only-secret")
    ))
    with pytest.raises(DatabaseOperationError) as result:
        connect_to_database(DatabaseConfig(password="test-only-secret"))
    assert "test-only-secret" not in str(result.value)
    assert result.value.__suppress_context__
