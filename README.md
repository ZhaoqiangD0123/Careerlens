# Careerlens
The start of python!

测试远程连接

测试本地上传

添加.gitignore

## 第一个功能：校验岗位数据

`validate_job(job)` 接收一条映射形式的岗位数据，要求包含 `title`、`city`、`description`、`source_url` 四个非空字符串，且链接使用 HTTP 或 HTTPS。成功时返回去除首尾空格的新字典；失败时抛出 `JobValidationError`，说明有问题的字段。链接只检查基本格式，不保证网页可访问。

在项目根目录运行测试：

```powershell
uv run pytest
```
