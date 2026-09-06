# ADR-0006: service 层依赖分层与公共下沉层（解三组 service 循环依赖）

- 状态：已采纳（2026-09-05，工单 T6）
- 背景：架构体检（.sdlc/assessment-2026-09-05/architect/findings.md F2）发现三组
  service 循环依赖，靠「文件末尾反向 import + PEP 562 惰性门面 + 函数内延迟
  import」在运行时掩盖，R9（`import backend.app` 不报错即绿）检不出。
- 关联：ADR-0005（SaaS 治理单源）；本 ADR 只治理 backend/services 层内依赖方向，
  不触碰 API/Repository 边界与事务所有权（后者见体检 F3，另行立票）。

## 语境与问题

三组环（改造前，边均有 HEAD 证据）：

```
环1  ai_planner_service（shim）
       │ import（模块级，shim 仅一行）
       ▼
     ai_planner 包 ──(文件末尾 import _facade，×4：llm_client/orchestrator/state/url_guard)──▶ ai_planner_service
     ai_planner.llm_client ──(模块级 import LlmProviderService)──▶ llm_provider_service   ← 包内即含跨域边

环2  skill_service ──(函数内 from skill_import_service import SkillImportService，:441)──▶ skill_import_service
     skill_import_service ──(函数内 from skill_service import SkillService，:287)──▶ skill_service

环3  ai_planner.llm_client ──(模块级 import LlmProviderService/LlmRuntimeConfig)──▶ llm_provider_service
     llm_provider_service ──(函数内 ×4：resolve_config_from_settings :64 / invalidate_client_cache :72 /
                              ai_planner._cooldown.clear :312/:399)──▶ ai_planner 域
```

后果：模块依赖图有环 = 无法独立测试与独立演进；环被语法手段掩盖后 R9 永远报绿；
初始化顺序约束只存在于 20 行 docstring 里。晚绑定读取本身不是债——它是存量单测
patch 路径（`backend.services.ai_planner_service.<name>`）的运行时承重墙；**债在于
晚绑定的实现方式（import 门面）制造了环**。

## 决策

### D1. 分层方向（service 层内）

```
编排服务（skill_import_service / llm_provider_service 的管理面 / ai_planner_service 门面）
   ▼ 单向
能力服务（skill_service / ai_planner 包内各子模块 / llm_provider_service 的解析面）
   ▼ 单向
公共下沉层 backend/services/llm_common/（叶子）
   ▼ 单向
platform_core / config / backend.repositories
```

互调确需反向时用**依赖注入反转**（见 D3），禁止用 import（任何位置：模块级/
文件末尾/函数内）实现反向触达。

### D2. 公共下沉层 `backend/services/llm_common/` 的职责边界

- `runtime.py`：`LlmRuntimeConfig`（运行时配置快照形状）、
  `resolve_config_from_settings`（yml/env 兜底解析）、`resolve_runtime_config`
  （激活供应商三段解析；repo/decrypt 参数化注入，供 LlmProviderService 委托）。
- `seam.py`：晚绑定命名空间缝（见 D4）。
- **允许依赖**：platform_core / config / backend.repositories / 无状态 service 叶子
  （llm_secret_vault）。**禁止依赖**任何带业务编排语义的 service。
- 边界外（刻意不收，理由见 R3 备选）：`llm_chat` 与 client 缓存留在
  `ai_planner/llm_client.py`；cooldown 留在 `ai_planner/_cooldown.py`——二者的
  存量单测以该模块命名为 patch 缝（`lc.record_usage` / `_cooldown.get_async_redis`），
  物理搬迁会使 patch 落在 shim 字典上而运行时读自己的 globals，测试必红。
  方向已单向化（消费者 → ai_planner.llm_client / ai_planner._cooldown → 叶），
  消除的是环，不是文件位置。

### D3. 互调反转（环 2 解法）

skill 域方向固化为 `skill_import_service（编排）→ skill_service（能力）`。
`SkillService.approve_candidate` 需要反向调用导入管线：改为**方法参数注入
importer 类**，由 API 组装点（api/v1/skills.py approve 路由）请求期经
`skill_import_service` 模块属性取值后传入——该取值点同时保住了存量测试
monkeypatch `skill_import_service.SkillImportService` 的生效语义。
skill_service 对 skill_import_service 仅剩 `TYPE_CHECKING` 类型 import（运行时零依赖）。

### D4. 晚绑定测试缝（环 1 解法）：seam 注入替代门面 import

- 门面 `ai_planner_service.py` 改为**纯静态 re-export**（`from package import *`
  尊重包 `__all__`，含私有名），删除 PEP 562 `__getattr__`/`__dir__`。
- 门面初始化**末尾**调用 `llm_common.seam.bind(sys.modules[__name__])` 把自身
  模块对象注入缝（一次性、显式、可 grep）。
- 包内子模块对可 patch 的可变依赖与跨模块符号，一律 `from
  backend.services.llm_common.seam import seam` 后经 `seam().X` 调用期取值；
  **四个文件末尾的 `import ... as _facade` 全部删除**，包内模块不再 import 门面。
- patch 语义不变：`mock.patch` / `monkeypatch.setattr` 直接写门面模块 `__dict__`
  （实例属性查找先于任何转发），`seam()` 的下一次取值即刻可见。
- import 图：业务模块 → llm_common.seam（叶子）← 门面（单向注入），无环；
  门面 → ai_planner 包（唯一方向）。
- seam 未装配（门面从未被 import）时 `seam()` 抛 RuntimeError（fail-loud）。
  正常流程不可达：backend.app 路由聚合（api/v1/ai.py）与一切 patch 门面路径的
  单测都会先装载门面。

### 环 3 解法（配置概念下沉 + 单向化）

- `LlmRuntimeConfig` / 兜底解析 / 三段解析实现 → llm_common（D2）；
  `llm_client._resolve_llm_runtime_config` 改调 `llm_common.resolve_runtime_config`
  （不再 import LlmProviderService）；`LlmProviderService.resolve_runtime_config`
  变为委托（注入自身 repo/decrypt，保住 `svc.repo.get_active` 实例级 patch 语义）。
- `llm_provider_service` 对 ai_planner 域的三处函数内延迟 import 全部转正为
  模块级单向 import（`ai_planner.llm_client` 的缓存失效 / `ai_planner._cooldown`
  的清冷却）；ai_planner 包 `__init__` 撤销对 llm_provider_service 的回引
  （全仓零消费者，已验证），使 llm_provider_service → ai_planner 方向恒安全。

## 被否决备选

| 备选 | 否决理由 |
|---|---|
| **维持惰性门面**（PEP 562 `__getattr__` + 文件末尾 import） | 环被掩盖而非消除：R9 永远检不出，初始化顺序约束不可见，子模块无法独立演进；「兼容」成本永久化 |
| **合并 service**（ai_planner 包合回单文件 / skill 两服务合一） | 回到 617+ 行单文件（期4 拆分前的状态，变更理由不单一）；skill 两服务变更节奏不同（导入管线 vs 治理），合并放大冲突面 |
| **llm_chat / cooldown 物理迁入 llm_common** | 存量单测以 `ai_planner.llm_client` / `ai_planner._cooldown` 模块命名为 patch 缝（patch 写模块 `__dict__`、实现读自身 globals），搬迁 = shim 与实现字典分离 = patch 失效 = 必改测试（本工单红线之外的并行领域）。方向单向化已达成解环目的，物理归位留给测试面迁移后的后续工单 |
| **门面静态 re-export + 子模块顶层 import 门面** | 静态 re-export 要求门面初始化时包符号已定义；「先 llm_client 后门面」入口下门面 from-import 部分初始化的 llm_client 必 AttributeError——只是把文件末尾 import 换个位置，环仍在 |
| **子模块互相直接 import（orchestrator→state→orchestrator）** | 包内本就有 orchestrator ⇄ state 真环（state 后台协程构造 AiPlannerService / orchestrator 触发 state 的 _spawn），直接 import 不解环；seam 晚绑定同时消解了这条包内环 |

## 三组环：前后依赖图（文字版）

```
环1（门面 ⇄ 包）
前：ai_planner_service ─import→ ai_planner{llm_client,orchestrator,state,url_guard}
     └─四人组 文件末尾 import _facade─▶ ai_planner_service        ← 环 + 包内 orchestrator⇄state 隐环
后：ai_planner_service ─import(唯一方向)→ ai_planner ─import→ llm_common.seam（叶子）
     门面初始化完成 ─bind()注入→ seam；包内读 seam().X（调用期），零 import 门面

环2（skill 两服务）
前：skill_service ─函数内import→ skill_import_service ─函数内import→ skill_service
后：skill_import_service ─模块级import(唯一方向)→ skill_service
     skill_service.approve_candidate(result_id, importer=…) ←── API 组装点请求期注入
     （skill_service 对 skill_import_service 仅 TYPE_CHECKING 类型 import）

环3（llm_provider ⇄ ai_planner）
前：ai_planner.llm_client ─模块级import LlmProviderService→ llm_provider_service
     llm_provider_service ─函数内import×4→ ai_planner_service / ai_planner._cooldown  ← 环
后：ai_planner.llm_client ─→ llm_common ←─ llm_provider_service（配置概念共同下沉）
     llm_provider_service ─模块级单向import→ ai_planner.llm_client（缓存失效）/
                                            ai_planner._cooldown（清冷却）
     ai_planner 包 __init__ 撤销对 llm_provider_service 的回引（零消费者）
```

## 后果

- 正面：services 运行时 import 图无环（AST 检查通过）；涉事模块可任意顺序单独
  import；三组环的初始化顺序魔法从 docstring 约定变为结构保证。
- 负面/代价：门面 patch 路径仍是技术债——新测试应优先 patch 定义模块
  （llm_common / ai_planner.llm_client / ai_planner.state…），存量门面路径在
  测试面完成迁移后可退役门面与 seam（届时删除 `ai_planner_service.py` 并把
  API/lifespan 改指包路径）。
- 风险：seam 未装配时 `seam()` 抛 RuntimeError（fail-loud，正常装配流程不可达）；
  ADR 复审时应确认无新增「绕过 seam 直接 import 门面」的代码。
