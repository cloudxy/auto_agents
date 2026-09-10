---
name: check-arch
description: >-
  Runs tools/check/arch.sh (R1–R13 + B1–B3) and reports file:line violations.
  Use when 架构检查, 硬编码密钥, 分层边界, 提交前, PR, or after verify.
---

# 架构合规检查

正则、白名单、R13 豁免以脚本为准。规则：`.claude/rules/project_rule.md`。

## Route

| 观察到 | 先做 |
|--------|------|
| 要证明功能做完（测试/curl/构建） | `verify`（它会再跑本脚本） |
| 只扫红线 / 修分层 | 本 skill |

## Quick start

```bash
bash tools/check/arch.sh
```

退出码 = 违规数（上限 255）。`0` = 通过。

Copy and check off:

```
Arch:
- [ ] 仓库根跑脚本
- [ ] 贴 stdout 原文（✓ / ❌ + file:line），不改写成摘要
- [ ] 有 ❌：按 references/scan-commands.md 修，再跑同一条脚本
- [ ] 直到退出码 0
```

通过时打印：`✓ 架构合规检查通过（13 红线 + 3 边界，全部通过）`。

## 完成时回复

整段脚本 stdout（至少含每条 ❌ 的 `file:line`，或最后的 ✓ 行）。不要只写「过了」。

## Examples

**Input:** 改完 API 准备提交。

**Fail then fix:**

```
❌ R7  API 层禁止 import ORM
   backend/app/api/v1/announcement.py:12
```

把 ORM import 挪到 Service，再跑同一条 `bash tools/check/arch.sh`，直到 ✓。

## Advanced

信条与修法：[references/scan-commands.md](references/scan-commands.md)。
