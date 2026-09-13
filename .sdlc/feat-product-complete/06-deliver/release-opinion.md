# 放行意见 · feat-product-complete（四柱收口 + 不好用）spec v1.6 / contract v2.1

> 作者：/qc（无记忆独立上下文）｜日期：2026-09-12｜阶段：L4 发布终判（implement / verify / review 三关全 pass 后）
> 决策对象：`.sdlc/feat-product-complete` 全工件树 + 管理窗给定门禁指纹（commit sha 待 sre 在 06-deliver 钉死，见条件 C1）

## 1. 结论

| 项 | 内容 |
|---|---|
| **结论** | **有条件放行（ship-with-conditions）** |
| 一句话理由 | 三关证据链完整、确定性门禁全绿有指纹、覆盖 152/152 无未标注洞、findings 零悬空；剩余风险全部已知且有主，条件是交付侧执行项（环境验证 + 发布 commit 钉版重跑），不需要任何代码改动 |
| 阻塞项数量 | **0**（blocker 0 / major 0 / minor 4 全闭合 + 2 处措辞残余豁免） |

### 放行条件（全部是交付执行项，具体可验收）

| # | 条件 | 责任人 | 验证方式 |
|---|---|---|---|
| C1 | 发布 commit 钉 sha 后原样重跑五闸（pytest / arch / 迁移 / jest / 双 build），命令+退出码+时间戳落 06-deliver | /sre | 五闸退出码全 0，与本次指纹一致；不一致即停，上抛人工 |
| C2 | deferred-live **B-2+B-3 合并真网关轮**在向租户开放渠道组/令牌前执行：LLM.ENABLED + 上游 key（机外），按 T-09 口径（Bearer=签发明文 → chat → used_tokens≥1 → 恰 1 条 relay_token_call_succeeded），随后打出站钥匙验拒绝形态+用量基线不变 | /sre + /qa | coverage §5.B-2/B-3 命令；失败=环境闸未过，**QC 不豁免**，上抛人工 |
| C3 | 迁移链在 staging/生产克隆完整 apply（含 041–044，up→down→up 可逆性现场复证）；alembic 039/040 环境漂移先对齐（已裁 /sre） | /sre | 迁移门禁 0 + staging apply 成功；顺带跑 B-6 真库轮（注意 `auto_agents` 用户 1044 无 CREATE 权限，用 root 或预授权） |
| C4 | B-5 队列/工人环部署冒烟：Redis+worker 起后走「AI 方案 → 试采 → 轮询 completed」（coverage §5.B-5 模板） | /sre | 任务终态 completed |
| C5 | B-1(b) curl P95 冒烟（≥50 样本）上线当日跑；B-1(a) Playwright 全量 P95 排入上线后 3 天内，P95≥2s 告警 | /qa + /sre | coverage §5.B-1 双口径命令 |

若 sre 把 C1–C4 当作标准部署动作执行且全绿，本意见即等效无条件放行，无需再次进场；任一条件失败走人工豁免流程（第 6 节），QC 无权改判。

## 2. 门禁指纹

| 闸门 | 命令（口径） | 退出码 | 结果 | 状态 |
|---|---|---|---|---|
| 后端单测 | `uv run pytest backend/tests`（全仓） | 0 | 1546 passed / 38 skipped | 绿 |
| 架构红线 | `bash tools/check/arch.sh` | 0 | 0 违规 | 绿 |
| DB 迁移门禁 | 迁移链校验（041–044 可逆） | 0 | — | 绿 |
| 前端构建 | admin / official build | 0 | — | 绿 |
| admin 单测 | jest 35 套件 | 0 | 224+ 全过 | 绿 |
| 覆盖矩阵 | `python3 check-matrix.py coverage.md spec.md` | 0 | 54 条 FR/NFR 全覆盖 | 绿 |
| verify 定向轮 | 4 文件定向 pytest | 0 | 28 passed / 1 skipped（skip=真库轮文件 sqlite 态按设计跳） | 绿 |
| 真库保真轮 | `MYSQL_FIDELITY=1 … test_t42_fidelity_queue_depth.py` | 0 | 1 passed（原样命令块在 coverage §3） | 绿 |

- 证据为命令+退出码原样口径（管理窗给定 + coverage §0/§3 落盘），非「测试都过了」声称。
- 38 skipped 的类别已解释：环境门控的保真/E2E 半在 sqlite/CI 态按设计跳过，其中真库半已由 MYSQL_FIDELITY=1 轮单独执行 PASS——skip 不是隐藏红。
- E2E 闸未配置的显式理由：本仓无 E2E 套件；其角色由 deferred-live B-1/B-2/B-5 人工轮承接（本意见条件 C2/C4/C5）。
- commit 一致性：无 sha 钉版是唯一指纹缺口 → 不是阻塞（review 轮 4 项 minor 全为文档/工件层），但转化为条件 C1。

## 3. 覆盖完整性核对（五点）

1. **FR↔矩阵**：spec 29 个 FR 标题 = 28 冻结 + FR-91 合同豁免（spec §3/§9.1 明文「不施工不验收」，review 核实零施工）；矩阵 §1.0 索引含 spec 全部 FR 字面；脚本指纹 54/54 exit 0；NFR-01…10 全处置（01 deferred-live 有测法，09 N/A，其余绿）。**缺失 0**。
2. **FR↔设计工件**：edge-states、contract v2.1、db-spec、schema.dbml、sitemap、ADR-0019…0023 全部在盘。
3. **FR↔票据**：contract 内嵌票表 T-01…T-42 每票带 FR 映射与 GWT 锚；03-impl/ 42 件 evidence 全在盘。v1.2 stale 票已归档不混用。
4. **findings 状态**：见第 4 节，零悬空。
5. **门禁指纹**：见第 2 节。

已知坑位对照（PIT-QC-01…04）：矩阵对账以脚本输出为准；coverage.md 存在且非默认 skip 混过；空心绿由 verify §1.1 抽读排除；本特征覆盖是 FR↔用例新映射（17+17 回仓核实），不是「现网套件绿」冒充。

## 4. findings 处置

| 编号 | 严重度 | 一句话 | 状态 |
|---|---|---|---|
| REV-QA-1 | minor | coverage 103.4 格滞后 | fixed（qa 微修刷 152/152） |
| REV-QA-2 | minor | spec 文头版本号未升 | fixed（v1.6） |
| REV-QA-3 | minor | IMPL-QA-1/3 豁免 spec 侧未注记 | fixed（GWT-60.6/93.6 行尾回指） |
| REV-QA-4 | minor | B-1/4/5 缺命令模板 | fixed（模板齐，责任面 /sre+/qa） |
| 残余两处措辞失谐 | minor | spec §8 行未提 REV-QA-2/3、coverage §6 旧措辞 | waived（纯措辞无语义影响；出处 findings.md） |

blocker 0（waived 0）/ major 0（waived 0）/ minor 4 fixed + 2 waived（有理由有出处）。IMPL-QA-1/2/3/4/5 全部闭合或裁决注记。

## 5. 剩余风险与 deferred-live 分级

| # | 风险 | 能否及时发现 | 恢复成本 | 判定 |
|---|---|---|---|---|
| R-1 | 渠道组令牌→真网关链路未经真实环境端到端 | 是（首次调用即显形；60.5 优雅失败；事件面可观察） | 低 | **转条件 C2，开放租户前必跑** |
| R-2 | 平台超管 AI 采集端到端依赖真队列/工人 | 是（任务停 pending 可见） | 低 | **转条件 C4** |
| R-3 | 迁移 041–044 生产 apply + 039/040 漂移 | 是（apply 即知） | 中（可逆链已验） | **转条件 C3** |
| R-4 | 市场列表 P95 未实测 | 是（访问日志/APM） | 低 | C5 |
| R-5 | T-32 三处数据降级 | 是（tooltip 明示，无编造） | 低（后续票补端点） | 可接受，账本承接 |
| R-6 | 探针真引擎轮（B-4）、真网关拒绝半（B-3） | 是 | 低 | B-3 并入 C2；B-4 随 C2 顺跑 |
| R-7 | WACT/PC 四周窗（B-7） | 定义即上线后 | — | 上线日起算，中途不下成败 |

**分级**：上线前必须人工跑 = C2（含 B-3）、C3（含 B-6）、C4、C1；建议当日 = C5 curl 半、B-4 顺跑；上线后可 = B-1(a) 全量、B-7 四周窗。

## 6. 人工豁免记录

本次无人工豁免。C1–C5 若有失败：批准人必须是能承担后果的人（非 /qc），记录于 06-deliver。

## 7. 账本与豁免对发布面的影响（确认）

- 账本四组全部脱离阻断面：T-32 降级端点=后续票；IMPL-QA-3 维持既有+contract 注记；IM 测试债=spec §5 转账本；alembic 漂移+分支 ahead=交付清单（C3 覆盖）。
- **六问豁免对发布面影响 = 零，确认**：FR-91 零施工零验收；官网动词维持预告形态、零「当前可买」（测试+review 独立 grep）；¥299 保留；渠道组对外互否移出冻结 Then；个人注册未开且无依赖。
- 宪法红线：review 独立复核全过。

## 8. 不可逆面操作者须知（随上线交付 ops）

1. **收款确认是单向门**（GWT-50.10）：超管确认=paid+专业档三数字配额，无撤销路径。必须先见线下付款凭证再确认；存疑留 pending。防呆已内建（50.11 no-op / 50.16 不叠档 / 50.15 唯一约束）。
2. **令牌/钥匙明文只显示一次**（51.1/51.8、60.1/60.11）：丢失无找回，恢复=吊销+重签（吊销即时断流）。事件与日志零明文。签发对网关失败=诚实失败，无本地假成功。
3. **基座守卫不是碍事**：种子 admin 不可删（94.1）、平台租户不可改名/停用/删（94.2–94.4）——不要试图绕过，绕过本身即缺陷信号。

## 9. 上线前检查清单（给 sre deliver 帽的输入）

1. 钉 release commit sha；C1 五闸原样重跑，指纹落 06-deliver（命令+退出码+时间戳）。
2. C3：staging/克隆 apply 迁移链（含 041–044，复证 up→down→up）；039/040 漂移对齐；B-6 真库轮（root 或预授权）。
3. C2：LLM.ENABLED+上游 key 机外配置 → T-09 口径真网关轮（用量走+恰 1 事件）→ B-3 不变量 →（顺跑 B-4 一枪）。
4. C4：Redis+worker 起链 → AI 方案→试采→轮询 completed。
5. 环境密钥三件套：`AUTO_AGENTS_MYSQL_DEFAULT_PASSWORD` / `AUTO_AGENTS_REDIS_DEFAULT_PASSWORD` / `AUTO_AGENTS_JWT__SECRET_KEY`（双下划线；.env 不做 ${} 展开）；仓库保持零 DSN/零明文。
6. 上线后红线抽检：`/skills` 零种子；官网零「当前可买」；租户直打 `/platform-ops` `/newapi` 404 同形；平台租户改名/停用被拒。
7. C5：当日 curl P95 冒烟；3 日内 Playwright 全量；P95≥2s 告警。
8. 向 ops 交第 8 节须知 + B-7 四周窗起算。
9. 回滚预案：回退上一构建 + 041–044 down 路径（可逆已验）；本特征以增量为主。

## 10. 我做了 / 没做

做的：五点覆盖机械核对、deferred-live 风险分级、账本与豁免确认、终判。没做：不重做 reviewer 逐八维审查、不改代码、不改判门禁、不替操作者决定六问。本帽非本轮任何工件的产出者（独立无记忆上下文）。

**ship/block 一行：ship-with-conditions（有条件放行）——0 阻塞项；条件 C1–C5 全部为 sre/qa 交付执行项，任一失败上抛人工、QC 不豁免。**
