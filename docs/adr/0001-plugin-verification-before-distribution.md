# ADR-0001：插件分发前必须平台自验（MCP 工具桥为验证基座）

- 状态：已接受（2026-09-02）
- 决策人：项目所有者（P6 能力资产中心拷问 Round 2，Q9）

## 背景

能力资产中心（P6）引入插件资产（skills + MCP servers + hooks + commands 的打包分发单位，对齐 zcode/Claude Code 格式）。平台有两种姿态：只做元数据治理与转发，或亲自执行验证。

## 决策

**平台不能自行验证的插件，不得分发给用户。** 为此平台内置 MCP 工具桥（官方 Python SDK，stdio/HTTP）：分发前跑验证管线——安装 → 连接 → tools/list → 抽样 tools/call → health_status / verify_detail 落库；未通过验证的插件默认不可进入分发面。MCP 工具桥同时是平台 LLM 的工具面（专家/AI 规划器可调插件工具）。

**边界**：hooks / commands 只登记不执行——第三方代码进平台生命周期需要沙箱/签名体系，明确不在本期（未来若做需新 ADR）。

## 理由（所有者原话要旨）

> 自己平台都不能验证插件证伪，如果提供给用户使用，就是不负责任的态度。

与既有模式同构：LLM 供应商的连通探测（probe-test）、中转站渠道的 10 维真伪探针——平台对外分发的能力，平台必须先亲自跑通。

## 后果

- 插件资产多一个 `health_status / last_verified_at / verify_detail` 治理位（复用模式，非新范式）；
- 验证管线是分发的前置闸门（状态机：experimental → verified 才可 stable/recommended）；
- 引入运行时依赖 `mcp`（Python SDK）；stdio 命令白名单 + 全程超时 + 不 shell 的安全边界随之生效。
