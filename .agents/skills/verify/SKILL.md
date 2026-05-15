---
name: verify
description: 交付自检 - 声称"已完成"前强制跑 build/test/curl 并贴输出，消除空口完成反模式
---

# 交付自检

对齐 `answer_rule.md` 的"回答红线 - 空口完成"：任何"已完成"陈述必须伴随可观测证据。本 skill 把"改动类型 → 必跑验证命令"机械化。

## 触发场景

- 即将在对话中说"已完成"、"搞定了"、"修好了"、"应该没问题"
- 准备 commit 或提交 PR
- 用户明确说"验证一下"、"跑下测试"
- PUA L1+ 触发时（见 `pua.md` 的压力升级）

## 执行流程

### Step 1: 识别改动范围

```bash
git status --short
git diff --stat HEAD
```

按路径归类（可能同时命中多个类型，全部要跑）：

| 改动路径 | 类型 |
|---------|------|
| `backend/services/**`、`backend/utils/**`、`backend/repositories/**` | 后端代码 |
| `backend/app/api/**`、`backend/app/external_api/**` | API 层 |
| `platform_core/models/**`、`platform_core/schemas/**` | 数据契约 |
| `platform_core/{logger,db,storage,exceptions,repository}.py` | 基建层 |
| `scrapy/**` | 爬虫 |
| `config/**`、`.env*`、`scrapy/settings.py` | 配置 |
| `**Dockerfile`、`**docker-compose**` | 容器 |
| `.github/workflows/**` | CI |
| `frontend/{admin,official}/**` | 前端 |
| `pyproject.toml`、`uv.lock` | 依赖 / workspace |

### Step 2: 按类型跑验证（并行）

| 类型 | 必跑命令 | 通过标准 |
|------|---------|---------|
| 后端代码 | `uv run pytest -x -q backend/tests` | 退出码 0 |
| API 层 | `uv run python run_backend.py --no-reload &` + `sleep 3 && curl -sS localhost:9111/api/v1/health \| jq` | HTTP 200 + JSON |
| 数据契约 | `uv run pytest -x -q platform_core/tests` + 调用 `/check-arch` R7/R8 | 红线 0 违规 |
| 基建层 | `uv run python -c "from platform_core import init_log, init_db, init_storage; init_log(); init_db(); init_storage()"` | 无异常 |
| 爬虫 | `uv run python run_spider.py --list` + `cd scrapy && uv run scrapy check {spider_name}` | 列出爬虫 + 无 error |
| 配置 | 重启对应服务 + 跑健康检查 curl | 服务启动 + 健康 OK |
| 容器 | `docker build -t _verify . && docker run --rm _verify echo ok` | build + run 退出 0 |
| CI | 推分支观察 GitHub Actions 或 `act -j {job}` | job 变绿 |
| 前端 | `cd frontend/admin && npm run build` 和 `cd frontend/official && npm run build` | 退出码 0 |
| 依赖 | `uv sync --check` 或 `uv lock --check` | 锁文件与 pyproject 一致 |

**并行原则**：独立命令在一次 Bash 里 `&` 并行或者一条消息里多个 Bash tool call，禁止串行等待。

### Step 3: 贴输出 + 判定

把**实际 stdout/stderr 最后 20-50 行**贴回对话，禁止总结、禁止"大致通过"。格式：

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

判定规则：

| 全部通过 | 任一失败 |
|---------|---------|
| 可以说"已完成，验证输出如下" | **禁止**说"已完成"，进入 `pua.md` 的 L1 压力升级 |

### Step 4: 联动 check-arch

验证跑绿之后，再调 `/check-arch` 做一次架构合规扫描。交付闭环 = `/verify`（能跑）+ `/check-arch`（合规）。

## 输出约定（反模式自检）

禁止出现（对齐 `answer_rule.md` 回答红线）：

- ❌ "应该没问题" / "大概能跑" / "可能通过"
- ❌ "测试了，通过了"（不贴输出）
- ❌ "本地没装环境，跳过" —— 先想办法装，再说别的
- ❌ "功能代码写完了，测试后面补" —— 无测试无交付

正例：

- ✓ 直接贴 stdout，让证据说话
- ✓ 命令失败时贴报错+stacktrace，而不是"失败了，可能是环境问题"

## 相关 Rule / Skill

| 依赖 | 用途 |
|------|------|
| `answer_rule.md` "空口完成"红线 | 本 skill 的根本依据 |
| `pua.md` 能动性等级"交付验证"行 | 被动 vs 主动的分水岭 |
| `/check-arch` | Step 4 的联动 |
