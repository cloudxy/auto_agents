# 验证命令参考

## 验证命令矩阵

| 改动路径 | 类型 | 必跑命令 | 通过标准 |
|---------|------|---------|---------|
| `backend/services/**`、`backend/utils/**`、`backend/repositories/**` | 后端代码 | `uv run pytest -x -q backend/tests` | 退出码 0 |
| `backend/app/api/**`、`backend/app/external_api/**` | API 层 | `uv run python run_backend.py --no-reload &` + `sleep 3 && curl -sS localhost:9111/api/v1/health \| jq` | HTTP 200 + JSON |
| `platform_core/models/**`、`platform_core/schemas/**` | 数据契约 | `uv run pytest -x -q platform_core/tests` + 调用 `/check-arch` R7/R8 | 红线 0 违规 |
| `platform_core/{logger,db,storage,exceptions,repository}.py` | 基建层 | `uv run python -c "from platform_core import init_log, init_db, init_storage; init_log(); init_db(); init_storage()"` | 无异常 |
| `scrapy/**` | 爬虫 | `uv run python run_spider.py --list` + `cd scrapy && uv run scrapy check {spider_name}` | 列出爬虫 + 无 error |
| `config/**`、`.env*`、`scrapy/settings.py` | 配置 | 重启对应服务 + 跑健康检查 curl | 服务启动 + 健康 OK |
| `**Dockerfile`、`**docker-compose**` | 容器 | `docker build -t _verify . && docker run --rm _verify echo ok` | build + run 退出 0 |
| `.github/workflows/**` | CI | 推分支观察 GitHub Actions 或 `act -j {job}` | job 变绿 |
| `frontend/{admin,official}/**` | 前端 | `cd frontend/admin && npm run build` 和 `cd frontend/official && npm run build` | 退出码 0 |
| `pyproject.toml`、`uv.lock` | 依赖 / workspace | `uv sync --check` 或 `uv lock --check` | 锁文件与 pyproject 一致 |

## 生成类 Skill 产出物检查

当改动由生成类 Skill 产生时，除路径验证外还需执行产出物完整性检查：

| 触发 Skill | 产出物检查 | 附加验证命令 |
|------------|---------|----------|
| `/new-svc` | 确认 5 个文件全部存在（ORM / Schema / Service / Repository / Router）+ 路由已注册 | `ls platform_core/models/{m}.py platform_core/schemas/{m}.py backend/services/{m}_service.py backend/repositories/{m}_repository.py backend/app/api/v1/{m}.py` + 导入测试 |
| `/new-spider` | 确认 spider 文件存在 + items/pipelines 已更新 + settings 已注册 | `uv run python run_spider.py --list` 包含新爬虫 + `uv run scrapy check {name}` |
| `/new-model` | 确认 ORM + Schema 配对存在 + `__init__.py` 已注册 | R7/R8 grep 为空 + 导入测试 `from platform_core.models.{m} import {M}; from platform_core.schemas.{m} import {M}Out` |
| `/deploy` | 确认 Dockerfile + docker-compose.yml + .env.example 存在 | `docker-compose config` 无报错 + 无硬编码密钥 |

**判定规则**：产出物缺一个 = 未完成，禁止说"已完成"。

**并行原则**：独立命令在一次 Bash 里 `&` 并行或者一条消息里多个 Bash tool call，禁止串行等待。

## 输出格式示例

把**实际 stdout/stderr 最后 20-50 行**贴回对话，禁止总结、禁止"大致通过"：

```
=== pytest -x -q ===
<实际输出最后若干行>
========= 42 passed in 3.1s =========

=== curl /api/v1/health ===
{"status":"healthy"}

=== uv run python run_spider.py --list ===
🕷️  可用爬虫列表
  • example
  • zhihu_feed
  ...
```

## 反模式自检

禁止出现（对齐 `answer_rule.md` 回答红线）：

- ❌ "应该没问题" / "大概能跑" / "可能通过"
- ❌ "测试了，通过了"（不贴输出）
- ❌ "本地没装环境，跳过" —— 先想办法装，再说别的
- ❌ "功能代码写完了，测试后面补" —— 无测试无交付

正例：

- ✓ 直接贴 stdout，让证据说话
- ✓ 命令失败时贴报错+stacktrace，而不是"失败了，可能是环境问题"
