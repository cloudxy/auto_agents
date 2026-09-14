# ADR-0007: 事务所有权唯一归属 Service 层

- 状态：已采纳（2026-09-05，工单 T7）
- 背景：架构体检（.sdlc/assessment-2026-09-05/architect/findings.md F3/F4）发现
  事务所有权分裂——18 个 service 内 commit 与 8 个 API 文件 38 处路由层 commit
  并存；`backend/app/api/deps.py` 的注释自认「路由 commit → ORM 属性过期」坑。
  同批发现 API 层 3 个文件直连 repository（跳层，skills/public_skills/external
  public）。
- 关联：ADR-0006（service 依赖分层，本 ADR 不触碰其分层方向）；ADR-0004（软删
  口径不变）；审计独立短事务口径沿用 P1-11 决策（见 D4）。

## 语境与问题

同一仓库两套事务口径：

```
口径 A（service 内 commit）：workflow/spider_task/schedule/llm_provider(管理面)…
    路由 → service 方法（方法尾部 await session.commit()）
口径 B（路由层 commit）：rbac/members/skills/llm_providers(2处)/admin/users/
    capabilities/tenant_signup…
    路由 → service 方法（只 add/flush）→ 路由 await session.commit() → record_audit
```

具体代价（均有 HEAD 证据）：

1. **每个新端点都要猜口径**。rbac_service.py 模块 docstring 明文约定「commit 由
   调用方（路由层）统一执行」，而同期 llm_provider_service 在方法内 commit——
   两种约定并存，review 无法机械把关。
2. **deps.py:34 的属性过期坑就是口径 B 造成的实际返工**：生产 session 工厂
   `AsyncSession(engine)` 默认 `expire_on_commit=True`，路由 commit 后再读 ORM
   属性触发同步惰性加载，异步上下文抛 MissingGreenlet（测试不暴露——conftest
   的 db_session 显式 `expire_on_commit=False`，掩盖了该类缺陷）。
   expert 团队路由读 `team.name` 于路由 commit 之后，是同型潜在线上缺陷。
3. **审计与业务的事务关系无统一答案**：审计若与业务同事务，业务回滚则审计丢
   失；若独立短事务（P1-11 现行），则审计写自身的 session 开启/提交逻辑落在
   API 层 `_helpers.py`——API 层仍在管理 session 生命周期。

## 决策

### D1. 事务边界唯一归属 Service 层，API 层只读结果

- **API 层（含 external_api）禁止调用 `session.commit()/rollback()/flush()`，
  禁止开启/关闭 session**。路由只做：参数校验、调用 service、错误映射、
  审计钩子（D4）、响应组装。
- **Service 方法边界 = 业务不可分割操作**（/dba 方法论口径）。方法完成一
  个完整业务写操作时，在方法尾部 commit——事务内禁外部调用、大批量分批等
  既有纪律不变。
- Repository 维持「只做数据访问，不 commit」——事务边界是业务概念，不是
  数据访问概念；Repository 拥有 commit 会使跨 repo 的组合写无法原子。

### D2. expire_on_commit 陷阱的处置：快照先于提交（snapshot-before-commit）

生产 session 保持 `expire_on_commit=True`（默认）——过期即失效是防脏读的
正确默认。由此产生的属性访问陷阱用**固定代码形态**消除，而非改 session 配置：

```python
row = ...                  # 写操作
await self.session.flush()  # 主键/默认列回填
snapshot = {...}            # 返回值所需的一切 ORM 属性，先固化为普通值
await self.session.commit()
return snapshot             #（或 commit 后经 get_*/list_* 重查，llm_provider 同型）
```

该形态在 llm_provider_service（`new_id = int(item.id)` 注释）与 rbac_service
（「先固化返回值再提交」）已是事实约定，本 ADR 将其升格为全仓 service 唯一
口径。**测试侧 conftest 的 `expire_on_commit=False` 保持不变**（测试隔离需要），
正因此，凡「commit 后读 ORM 属性」的缺陷测试抓不到——快照形态是唯一防线。

### D3. 组合即事务：内层方法以 `commit=False` 交出事务权

一个 service 方法既可能是完整业务操作（API 直调），也可能被另一个业务操作
组合（外层拥有更大不可分割边界）。用**关键字参数**显式表达：

```python
async def import_url(self, url, ..., *, commit: bool = True) -> dict:
    ...  # 业务步骤
    if commit:
        await self.session.commit()
    return result
```

- 默认 `commit=True`：API 直调即业务操作，service 自持事务。
- 外层组合方传 `commit=False` 并在自己的方法尾部统一 commit——组合写原子。
- 本票落地的两个组合点：
  - `SkillImportService._ingest_and_enqueue` → `SkillService.scan_library(..., commit=False)`
  - `SkillService.approve_candidate` → `importer(...).import_url(url, commit=False)`
    （importer 经 API 组装点注入，T6 seam 语义不变，仅调用实参增加关键字）
  - `LlmHealthPatrol` 循环 → `LlmProviderService.test_model(..., commit=False)`
    （巡检整轮一个事务；且中途 commit 会 expire 循环内 provider 行 →
    MissingGreenlet）
- 禁止用「方法尾部无条件 commit + 外层接受两段事务」替代——那会把组合写的
  原子性静默降级。

### D4. 审计：独立短事务（沿用 P1-11），写入口径归 Service

- 审计与业务**不同事务**（P1-11 既定）：审计失败绝不影响业务事务与响应码；
  业务回滚不连带丢审计（拒绝/失败操作的留痕价值）。
- 独立 session 的开启 + 提交从 `backend/app/api/_helpers.py` 下沉为
  `backend/services/audit_service.record_audit_standalone(...)`——API 层审计
  钩子变为纯委托，不再触碰任何 session 生命周期。`record_audit(session, ...)`
  的 session 形参保留（兼容 ~15 个路由调用点与既有测试 patch 面），实际不
  使用，后续机械工单可移除。
- 若未来某域要求「审计与业务同事务」，该域 service 在**同一 session、commit
  之前**调用 `AuditService.record(...)`（record 只插不提交的既有语义保留），
  同样不出 service 层。

### D5. API 跳层直连 repository 一并收口

`api/v1/skills.py`、`api/v1/public_skills.py`、`external_api/v1/public.py`
的 repository 直连全部改走 service（新增薄读方法：`SkillService.list_skills/
get_by_name/list_reviews`、`SpiderQueryService.get_task/query_public_results`）。
读方法不 commit（无事务可言）；public.py 的 SpiderService 过渡门面消费点
（R12 白名单内）顺手迁至 SpiderQueryService，消除同文件两种调用风格。

## 被否决备选

| 备选 | 否决理由 |
|---|---|
| **事务归 API 层**（路由 commit 为唯一口径，service 全部只 flush） | 业务不可分割性只有 service 知道（哪些写必须同生共死）；路由层 commit 会把「组合 service 调用」全部拆成跨事务；且该口径已被 deps.py:34 的实际返工证伪 |
| **装饰器声明式事务**（`@transactional` 包路由或 service 方法） | 声明式边界对 D3 的组合场景无解（装饰器无法知道自己在组合内层）；隐式开启事务使「事务内外部调用」纪律不可 grep；本仓 service 均为 session 注入形态，装饰器需另造 session 管理机制，平行造第二套基建 |
| **Unit-of-Work 对象**（显式 `uow = UnitOfWork(); async with uow:`） | 是更完整的形态，但要求全仓 service 构造方式与调用链整体改造（18+ service、90+ 测试文件的 patch 面），收益与现状 idiom（session 注入 + D3 kwarg）重叠——本仓组合点仅 3 处，kwarg 足以表达；若未来组合点增长到两位数，可按本 ADR 的边界语义平滑升级为 UoW（决策不变：所有权在 service 层） |
| **事务归 Repository / BaseRepository 提供 commit** | 事务边界是业务概念：跨 repository 的组合写（删除成员 = delete Notification + update User）无法在单 repo 内原子；且 repository 有了 commit 权限后分层约束退化为约定 |
| **生产 session 改 `expire_on_commit=False` 以消陷阱** | 掩盖而非消除：过期机制防的是 commit 后继续读陈旧属性；关掉后「commit 后继续改 ORM 对象」这类错误静默通过。快照形态（D2）同时解决陷阱与返回值固化，成本更低 |
| **审计与业务同事务**（随业务 commit 一起落） | 业务回滚即丢拒绝/失败留痕，审计价值减半；且审计 flush 失败曾把 session 打入 PendingRollback 导致业务 500（P1-11 修复的实际事故），独立短事务是已验证口径 |

## 后果

- 正面：API 层 commit 点 38 → 0（tenant 域 3 处例外见下）；「事务从哪开始到哪
  结束」有了唯一答案（service 方法签名+尾部）；deps.py:34 类陷阱被 D2 形态
  结构性消除；跳层 3 文件清零，租户过滤/审计等 service 横切策略对全部端点生效。
- 负面/代价：service 方法尾部 commit 使「调用方想自定义更大的事务」必须显式
  走 D3 kwarg——新增组合点时需人工识别（check-arch 暂无对应机械检查，靠
  review 把关）；`record_audit` 的 session 形参成为待清尾巴。
- 范围例外：`api/v1/tenant_signup.py`（1 处）与 `api/v1/admin.py` 的
  `/tenants` 两端点（2 处）的路由层 commit 本票不动——落点文件
  （tenant_signup_service.py / tenant_admin_service.py）属 tenant 域，本票
  红线禁改；遗留 3 处按本 ADR 语义由 tenant 域后续工单收口。
- 风险：commit 时点从「路由尾」提前到「service 尾」——路由在 service 返回后
  仍有代码（audit/响应组装），这些代码不再处于事务内。这正是期望行为（审计
  本就不该在业务事务内，D4），但要求新路由遵循「service 返回后只做协议层
  工作」的既定分工。
