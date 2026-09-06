# 架构扫描命令

权威入口只有这一条（pre-commit / CI / 本 skill 共用）：

```bash
bash scripts/check-arch.sh
```

- 退出码 `0` = 通过；非 `0` = 违规总数（上限 255）
- 规则定义：`.claude/rules/project_rule.md`
- 规则实现：`scripts/check-arch.sh`（R1–R13 + B1–B3）
- **禁止**在本文件或对话里手搓第二套 grep/awk。R10 的 logger 启发式、R12 白名单、R13 豁免同步都以脚本为准。

把脚本的完整 stdout 贴回对话。通过时最后一行是：

```
✓ 架构合规检查通过（13 红线 + 3 边界，全部通过）
```
