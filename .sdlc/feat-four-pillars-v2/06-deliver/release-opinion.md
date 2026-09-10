# 放行意见 · feat-four-pillars-v2 冻结施工集

> 作者：/qc｜日期：2026-09-10｜会话 `01a08997-5477-7662-8182-5112755d4936`
> 决策对象：IdleAutoClose 30s + Register copy + Alembic 039 staged + live 18.1 Then 40.56s + pytest **1336**
> 旧意见（down exit 1 / M=1331）**作废**。不是四柱 GA。六问不代选。不发明 `rotated:` 日期。不写密钥。

## 1. 结论

| 项 | 内容 |
|---|---|
| **结论** | ☐ 放行　☑ **有条件放行**　☐ 不放行 |
| **动工** | **不允许。** 只缺操作者机外轮换证明行。 |

### 条件

| # | 状态 |
|---|---|
| 1 / M | **satisfied**：全量 pytest **1336** passed / 35 skipped；admin+official build **0**；arch **0**；db_migrations **0**（head 039） |
| 2 | **satisfied**：方言 22；NFR-01 P95 1.445s；GWT-18.1 Then **40.56s** completed / export 200 |
| 3–5 / B | **satisfied** |
| 6 | **lock**（FR-50/51/60/61 ➖；六问开放） |
| A down | **PASS** `compose down --remove-orphans` **exit 0** |
| A 轮换 | **not PASS**：仅模板 `rotated: YYYY-MM-DD`，无真实日期 |

### 动工 remaining（仓库做不完）

操作者在 DeepSeek + Moonshot 控制台作废/轮换 `44e9446` 曾明文的凭据后，只写一行真实日期：

`rotated: YYYY-MM-DD`

写入 `.sdlc/feat-four-pillars-v2/06-deliver/rotation-44e9446.md`。禁止密钥。QC 不代勾。无此行禁止 `LLM.ENABLED=true` / litellm `compose up`。

### 合主干仍须（≠动工）

- **039 + untrack** 已在 `b8b5f85`（`git ls-tree HEAD -- deploy/litellm/config.gen.yaml` 空）
- **031–038 与冻结施工产品** 仍在工作树：039 `Revises: 038`，合主干对象必须带上 027→031…→039 全链，否则 Alembic 断代
- merge SHA 再跑四闸
- ENABLED 保持 false；根 compose 无 litellm 服务
- 禁止 downgrade past 037

夹具租户 qc-cond2 / qc181 **已删** remaining 0。

**open_questions：** Q-VOICE / Q-PRICE / Q-RELAY / Q-MARKET-USER / Q-BILL / Q-AGPL / Q-OPS-DUTY / Q-OPS-COLLECT。不代选。
