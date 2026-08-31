---
name: example-pdf-extractor
description: "示例 skill：从 PDF 中提取表格和正文文本。用于验证 skills-library 骨架（symlink 分发、meta.yaml 治理字段、索引、后台）是否跑通，非真实生产 skill。"
---

# Example PDF Extractor（示例）

这是 skills-library 骨架搭建阶段用的占位示例，用来验证：

1. `sync.sh` 能把它 symlink 到 `~/.claude/skills/example-pdf-extractor`
2. `meta.yaml` 的治理字段（分类/行业/评分）能被索引脚本读到
3. 后台能展示它并支持编辑评分

实际使用时替换成真实的 SKILL.md 内容即可，meta.yaml/SOURCE.md/CHANGELOG.md 结构保持不变。
