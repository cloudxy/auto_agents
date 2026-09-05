---
name: verify
description: 交付自检 - 声称"已完成"前强制跑 build/test/curl 并贴输出，消除空口完成反模式
trigger: >-
  即将声称"已完成/搞定了/修好了"、准备 commit 或提交 PR、
  用户要求"验证一下/跑下测试"、PUA L1+ 压力升级触发
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

详细命令矩阵见 [references/verify-commands.md](references/verify-commands.md)（含 10 种改动路径的必跑命令与通过标准）。

**并行原则**：独立命令在一次 Bash 里 `&` 并行或者一条消息里多个 Bash tool call，禁止串行等待。

### Step 2b: 生成类 Skill 完成后的附加验证

当改动由生成类 Skill 产生时，除 Step 2 外还需执行产出物完整性检查，详见 [references/verify-commands.md](references/verify-commands.md)。

**判定规则**：产出物缺一个 = 未完成，禁止说"已完成"。

### Step 3: 贴输出 + 判定

把**实际 stdout/stderr 最后 20-50 行**贴回对话，禁止总结、禁止"大致通过"。输出格式示例、判定规则与反模式清单见 [references/verify-commands.md](references/verify-commands.md)。

### Step 4: 联动 check-arch

验证跑绿之后，再调 `/check-arch` 做一次架构合规扫描。交付闭环 = `/verify`（能跑）+ `/check-arch`（合规）。

## 相关 Rule / Skill

| 依赖 | 用途 |
|------|------|
| `answer_rule.md` “空口完成”红线 | 本 skill 的根本依据 |
| `pua.md` 能动性等级“交付验证”行 | 被动 vs 主动的分水岭 |
| `/check-arch` | Step 4 的联动 |
| `/new-svc` `/new-spider` `/new-model` `/deploy` | Step 2b 产出物验证的场景来源 |
