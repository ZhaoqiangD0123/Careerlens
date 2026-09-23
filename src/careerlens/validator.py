"""校验并清理单条招聘岗位数据。"""

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit


REQUIRED_FIELDS = ("title", "city", "description", "source_url")


class JobValidationError(ValueError):
    """岗位数据不符合约定时抛出的异常。"""


def validate_job(job: Mapping[str, Any]) -> dict[str, str]:
    """返回清理过的岗位字段；无效数据抛出 JobValidationError。"""
    if not isinstance(job, Mapping):
        raise JobValidationError("岗位数据必须是字典或类似映射的对象")

    cleaned: dict[str, str] = {}
    for field in REQUIRED_FIELDS:
        if field not in job:
            raise JobValidationError(f"缺少必填字段：{field}")

        value = job[field]
        # 先检查类型，再调用字符串方法，避免数字等输入引发难懂的 AttributeError。
        if not isinstance(value, str):
            raise JobValidationError(f"字段 {field} 必须是字符串")

        value = value.strip()
        if not value:
            raise JobValidationError(f"字段 {field} 不能为空")
        cleaned[field] = value

    url = cleaned["source_url"]
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
    except ValueError as exc:
        raise JobValidationError("字段 source_url 不是有效的 HTTP/HTTPS 地址") from exc

    # 只判断链接的基本结构；这里不会访问网络，也不能保证页面真实存在。
    if parsed.scheme.lower() not in {"http", "https"} or not hostname or any(
        character.isspace() for character in url
    ):
        raise JobValidationError("字段 source_url 不是有效的 HTTP/HTTPS 地址")

    # 返回独立对象，避免校验过程改变调用者持有的原始数据。
    return cleaned
