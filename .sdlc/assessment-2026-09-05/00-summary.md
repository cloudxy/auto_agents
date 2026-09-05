# auto_agents 项目体检 · 整合报告（编排器仲裁版）

> 2026-09-05 · `/sdlc` 多角色并行评估（非功能票，无泳道）· 5 角色子代理 + 5 道确定性门禁
> 原始 findings：architect/ reviewer/ qa/ dba/ sre/ 各自 findings.md · 门禁原始输出：gates/*.log
> 所有问题均为 open 状态（本次只评估不修复）

## 门禁结果（确定性证据）——名义全绿，实际两处判决器失真

| 门禁 | 命令 | 结果 | 备注 |
|---|---|---|---|
| 架构红线 | check-arch.sh | ✅ 13红线+3边界 exit 0 | ⚠️ R7 正则假阴性（见 P0-2） |
| 后端测试 | pytest -q backend/tests | ✅ 773 passed / 11 skipped (47.7s) | skip 均有 MYSQL_FIDELITY 说明 |
| 前端 lint | check-frontend.sh | ✅ exit 0 | |
| 迁移检查 | check-db-ir + check-db-migrations | ✅ exit 0 | ⚠️ 管道丢计数假绿（见 P0-2） |
| 双前端构建 | npm build -w admin/official | ✅ exit 0 | |

**结论：门禁全绿不可作为放行依据，直到 P0-2 修复。**

## P0 — 必须马上处理（数据正确性 / 安全 / 可用性）

### P0-1 多租户「用户层隔离」三连缺（dba × reviewer 双源收敛，最高风险域）
- **登录无租户维度**：`user_repository.py:18` get_by_username 裸查 + `auth_service.py:53` scalar_one_or_none——同 username 多行即 MultipleResultsFound → 登录 500。
- **NULL 租户绕过唯一键**：users/llm_providers/tags/workflow_definitions 唯一键首列 tenant_id 可空，NULL≠NULL 使同名记录可重复存在（触发上一条的开关）。
- **User 未挂隔离钩子**：`user.py:8` 未继承 TenantMixin，`tenant_context.py:136` 对 User 不生效——全靠手写 tenant_id 过滤，且 R13 套件不含 members，无回归防线。
- 修法：登录查询带租户维度；唯一键改 `(tenant_id, username)` 并带软删标记；User 接入隔离机制或纳入 R13 登记清单；补跨租户/404/403 回归用例。

### P0-2 门禁可信度崩塌（architect + reviewer + sre 三方独立发现）
- `check-arch.sh:71` R7 正则匹配不到 `from platform_core.models.<子模块> import` 形式——API 直连 ORM 实际 8+ 处（rbac.py:17、skills.py:21、deps.py:21、members.py:115、auth.py:126 等）而报绿。
- `check-db-migrations.sh:66,104` 管道子 shell 丢失违规计数——SM-1/SM-5（数据兼容杀手规则）实测违规仍 exit 0；且该门禁未进 `.github/workflows/ci.yml`。
- 修法：两处正则/管道修复后全量重跑取证；迁移门禁纳入 CI。修好前，任何「全绿」陈述都要打折。

### P0-3 未提交 members 票（9 文件 +149 行）不满足交票条件
- DELETE /members/{id} 零跨租户/404/403 用例（破坏性端点）。
- 「删除后审计保留」承诺（member_service.py:115、Members.tsx:130）与 `members.py:120` INNER JOIN users 矛盾——被删成员的 operation_logs 从租户审计视图消失。
- 次级：并发删除 rows==0 未处理（StaleDataError→500）；members.py:4 注释归因失实；收件箱清理与审计写入无用例。

### P0-4 --reload 启动路径已坏（sre 复现：uvicorn app 对象 + reload → exit 1）
未提交的 run_backend.py 变更（uvicorn→loguru 接管，方向正确的冻结事故修复）与 --reload 不兼容；reviewer 另证 reload 子进程不继承日志接管。修复成本预计很低（工厂字符串 vs app 对象），但当前是「已复现的 broken 路径」。

## P1 — 结构债（近期治理，建议各开一票）

1. **service 循环依赖三组**：ai_planner ⇄ ai_planner 包（4 文件末尾反向 import + PEP 562 惰性门面）、skill_service ⇄ skill_import_service、llm_provider_service ⇄ ai_planner。R9 检不出（architect）。修法：抽 cooldown/llm_chat 公共下沉层 + ADR 留痕。
2. **事务所有权分裂**：18 个 service 内 commit vs 4+ API 文件路由层 commit（skills/rbac/llm_providers/members），`deps.py:34` 自认 ORM 属性过期坑（architect）。修法：ADR 定死唯一所有权（建议 service 层），API 层 commit 全部收口。
3. **API 跳层直连 repository**：skills.py:16、public_skills.py:17、external_api/v1/public.py:15-16（architect）。
4. **基建穿透业务**：platform_core/tenant_context.py 的 TENANT_EXEMPT_TABLES 硬编码 skills 等业务表名——B1 语义穿透（architect）。修法：豁免清单外移至配置或注册机制。
5. **迁移健康三件**（dba）：023 downgrade 不回滚 roles.permissions 的 JSON 追加（幽灵权限）；6 张软删表唯一键不带删除标记（删后无法重建同名）；019 down 实际跑不通（String→Integer）+ 孤儿物理销毁。修法：补一次「up→down→up 全链真演练」票据。
6. **测试三大盲区**（qa）：① 151 业务路由 ≥55 个（36%）无 HTTP 层测试——spiders 31/34 缺（含核心入口 POST /spiders/run）、audit-logs/notify-config/rbac departments/configs/webhook 全裸；② conftest.py:75-93 无凭据全局兜底 admin，RBAC 缺守卫的端点测试必然全绿（789165e 越权缺陷无回归佐证）；③ CI MySQL 保真通道仅 3/87 文件，约 96% 用例只过 SQLite。附：37/784 弱断言、fix 回归沉淀率 3/6（方言/越权/侧边栏三类高危恰好缺席）、无时间冻结设施、零浏览器 E2E（admin 25 页仅 3 页有测试）。
7. **交付成熟度**（sre）：监控四类全无外部落地、告警 0 条；compose 无 restart/资源限制/日志卷、健康检查浅探测；镜像 APP_ENV=prod + HOST=127.0.0.1 直跑陷阱；回滚从未实测、无镜像 tag 策略；冻结事故无复盘、无僵死看门狗。**现形态仅支持本地/内网试运行。**

## P2 — 打磨池（minor 择要）

- dba：约 8 处冗余索引 + 13 个无访问模式支撑的低基数索引（12 表 deleted_at 单列、priority 单列）——写放大；roles.permissions JSON 数组承载 RBAC 判定；spider_tasks.status 用 MySQL ENUM 且无流转图；时区语义混用。
- architect：run_backend.py 的日志接管落位编排脚本而非 platform_core/logger（换启动方式静默失效、不可单测）。
- qa：admin 25 页面仅 3 页有 jest 测试；E2E 豁免仅在特性级成立。
- reviewer：members.py:4 注释失实（已列 P0-3）。

## 正面确认（各角色独立给出）

- 分层主干 api→service→repository 宏观单向成立；spider_service 是 98 行薄门面非大杂烩；B2/B3 实测干净；docs/adr 已有 5 份留痕（architect）
- 迁移链 001→023 单线完整、头部无破坏性操作，017/019 有 expand-contract 意识；Redis 键治理（LLM cooldown）是三件套齐全的正面样板（dba）
- test_saas_members.py 是含真实 JWT/越权 403/副作用断言的范本级用例；spider/ai_planner 状态机与幂等用例充分；无 assert True（qa）
- request_id 全链贯穿；CI 有真实 MySQL 迁移保真通道；密钥 fail-fast；run.py 排水防僵死 + 日志接管是对历史冻结事故的正确修复（sre）
- 未提交 members 票的测试非空心、8 passed 实证（reviewer）

## 仲裁记录

- R7 正则假阴性：architect 主报 + reviewer F-06 独立复现 → 定为真实（确定性证据：8+ 处违规清单）
- 用户层隔离：dba（登录/唯一键）与 reviewer（TenantMixin 缺席）视角不同、互相印证 → 合并为 P0-1
- --reload：sre（复现 exit 1）与 reviewer（子进程不继承接管）→ 合并为 P0-4
- 「审计保留 vs INNER JOIN」矛盾：reviewer 单源但证据三处对齐（service/前端/视图实现）→ 采信
- dba 全部结论为静态分析（本机无 MySQL），EXPLAIN 待真库——列 4 条 Top 查询在其报告尾部

## 度量（编排器记录）

- 角色派发 5 次（architect 3.4min / reviewer 10.9min / qa 5.9min / dba 5.5min / sre 5.8min），门禁 5 道（全绿但 2 道判决器失真）
- 原始 findings ≈ 45 条 → 去重仲裁后 17 个独立问题（P0×4 / P1×7 / P2×3簇）
- 闸门拦截贡献：门禁 0（全绿）vs 新上下文角色审查 45——**本次体检本身就是「G-脚本需要 G-新上下文补位」的又一实证**
