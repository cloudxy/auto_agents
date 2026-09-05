"""LiteLLM 影子只读对比器（L1 · 零外呼）

对比「自研候选链对某请求的供应商/模型选择」与「生成的 LiteLLM config 将会
提供的路由面」，输出两侧路由决策对照表。**只读对比：不发起任何真实 LLM 调用、
不连接 LiteLLM proxy**——LiteLLM 侧输入就是 exporter 生成的 config dict 本身。

输入两侧：
- SelfSideChoice     自研侧决策快照（capture_self_side_choice 从既有选择逻辑采集：
                     llm_common.resolve_runtime_config + ai_planner._candidate_chain +
                     _cooldown.is_cooled_down；全部可注入，测试零 DB/零 Redis）
- LitellmDeployment  LiteLLM 侧 deployment（load_deployments_from_config 解析
                     exporter 生成的 config；cooled 状态为输入注入——L1 无法从
                     proxy 进程内存采集，缺省恒 False）

已知分层差异（L1 只记录不解决，product-review 任务二 .2）：
自研 cooldown 是 Redis 计数（跨进程共享、键=provider+model）；LiteLLM router
冷却是 proxy 进程内存态（多副本不共享）。两侧冷却态不一致时 diff 行标
known_layering=True（记录维度，不算配置错误）。
"""
from dataclasses import dataclass, field

from platform_core.logger import get_logger

logger = get_logger("service.litellm.shadow")

# 对照行状态（机械可断言）
STATUS_MATCH = "match"
STATUS_MISMATCH = "mismatch"
STATUS_MISSING_IN_LITELLM = "missing_in_litellm"
STATUS_MISSING_IN_SELF = "missing_in_self"


@dataclass(frozen=True)
class SelfSideChoice:
    """自研侧对某次请求的路由决策快照（纯数据，由采集函数组装）"""

    provider_id: int | None
    provider_name: str
    base_url: str
    primary_model: str
    chain: tuple[tuple[str, str], ...] = ()   # (model_id, tier) 优先序（含 primary）
    cooled_models: frozenset[str] = frozenset()  # 自研 cooldown 命中集合
    source: str = "provider"                    # provider:<id> | config（yml/env 兜底）


@dataclass(frozen=True)
class LitellmDeployment:
    """LiteLLM 侧一条 deployment（model_list 条目的脱壳形状）"""

    model_name: str      # 公开名 "{provider-slug}/{model_id}"
    model_id: str        # litellm_params.model 去协议前缀后的实际模型名
    api_base: str
    provider_label: str  # model_name 的 provider 段（对照自研 provider_name）
    cooled: bool = False  # router 侧冷却态（L1 无法采集，缺省 False）


@dataclass(frozen=True)
class ShadowDiffRow:
    """对照表一行：某 model_id 两侧路由/冷却决策对照"""

    model_id: str
    status: str                  # STATUS_* 四态
    self_base_url: str | None
    litellm_api_bases: tuple[str, ...]  # 同模型多 deployment 时全列（聚合路由）
    self_cooled: bool
    litellm_cooled: bool
    cooldown_divergent: bool     # 两侧冷却态不一致
    known_layering: bool         # 不一致且属已知分层差异（自研冷却/LiteLLM 无感知）


@dataclass(frozen=True)
class ShadowSummary:
    match: int = 0
    mismatch: int = 0
    missing_in_litellm: int = 0
    missing_in_self: int = 0
    cooldown_divergent: int = 0


@dataclass(frozen=True)
class ShadowDiff:
    rows: tuple[ShadowDiffRow, ...] = ()
    summary: ShadowSummary = field(default_factory=ShadowSummary)

    @property
    def consistent(self) -> bool:
        """两侧路由面完全一致（无 mismatch / 无单侧缺；冷却差异不阻断——分层共存已知）"""
        s = self.summary
        return s.mismatch == 0 and s.missing_in_litellm == 0 and s.missing_in_self == 0


def load_deployments_from_config(config: dict) -> list[LitellmDeployment]:
    """解析 exporter 生成的 LiteLLM config dict → deployment 列表（零 IO）。

    litellm_params.model 形如 "openai/<model_id>"（协议前缀由 exporter 附加），
    此处剥离前缀还原实际模型名，与自研侧 model_id 同键对照。
    """
    deployments: list[LitellmDeployment] = []
    for entry in (config or {}).get("model_list") or []:
        name = str(entry.get("model_name") or "")
        params = entry.get("litellm_params") or {}
        raw_model = str(params.get("model") or "")
        model_id = raw_model.split("/", 1)[1] if "/" in raw_model else raw_model
        provider_label = name.split("/", 1)[0] if "/" in name else name
        deployments.append(LitellmDeployment(
            model_name=name,
            model_id=model_id,
            api_base=str(params.get("api_base") or "").rstrip("/"),
            provider_label=provider_label,
            cooled=bool(entry.get("_cooled", False)),  # 测试注入位（config 本体不含）
        ))
    return deployments


def compare_routing(
    choice: SelfSideChoice,
    deployments: list[LitellmDeployment],
) -> ShadowDiff:
    """对照表主函数（纯函数）：按 model_id 对齐两侧，产出差异行 + 汇总。

    - 同模型多 deployment（LiteLLM 聚合路由）视为覆盖集合：自研 base_url
      命中集合任一即 match（LiteLLM 可路由到同一上游），否则 mismatch；
    - 冷却差异：known_layering 仅在「自研冷却中而 LiteLLM 侧无感知」时置位
      （已知分层差异，记录不阻断）；反向（仅 LiteLLM 冷却）标 divergent 但
      不标 known_layering（proxy 进程内状态，L1 无法归因）。
    """
    logger.info(
        f"影子对比开始: self_provider={choice.provider_name} "
        f"chain={len(choice.chain)} cooled={sorted(choice.cooled_models)} "
        f"litellm_deployments={len(deployments)}"
    )
    bases_by_model: dict[str, tuple[str, ...]] = {}
    cooled_by_model: dict[str, bool] = {}
    for d in deployments:
        bases_by_model.setdefault(d.model_id, ())
        if d.api_base and d.api_base not in bases_by_model[d.model_id]:
            bases_by_model[d.model_id] = (*bases_by_model[d.model_id], d.api_base)
        cooled_by_model[d.model_id] = cooled_by_model.get(d.model_id, False) or d.cooled

    self_models = [m for m, _tier in choice.chain] or (
        [choice.primary_model] if choice.primary_model else []
    )
    rows: list[ShadowDiffRow] = []
    seen: set[str] = set()
    self_base = choice.base_url.rstrip("/")
    for model_id in self_models:
        if model_id in seen:
            continue
        seen.add(model_id)
        litellm_bases = bases_by_model.get(model_id)
        if litellm_bases is None:
            rows.append(ShadowDiffRow(
                model_id=model_id, status=STATUS_MISSING_IN_LITELLM,
                self_base_url=self_base or None, litellm_api_bases=(),
                self_cooled=model_id in choice.cooled_models, litellm_cooled=False,
                cooldown_divergent=model_id in choice.cooled_models,
                known_layering=model_id in choice.cooled_models,
            ))
            continue
        self_cooled = model_id in choice.cooled_models
        litellm_cooled = cooled_by_model.get(model_id, False)
        covered = bool(self_base) and self_base in litellm_bases
        rows.append(ShadowDiffRow(
            model_id=model_id,
            status=STATUS_MATCH if covered else STATUS_MISMATCH,
            self_base_url=self_base or None,
            litellm_api_bases=litellm_bases,
            self_cooled=self_cooled,
            litellm_cooled=litellm_cooled,
            cooldown_divergent=self_cooled != litellm_cooled,
            known_layering=self_cooled and not litellm_cooled,
        ))
    for model_id, litellm_bases in bases_by_model.items():
        if model_id not in seen:
            rows.append(ShadowDiffRow(
                model_id=model_id, status=STATUS_MISSING_IN_SELF,
                self_base_url=None, litellm_api_bases=litellm_bases,
                self_cooled=False,
                litellm_cooled=cooled_by_model.get(model_id, False),
                cooldown_divergent=cooled_by_model.get(model_id, False),
                known_layering=False,
            ))
    summary = ShadowSummary(
        match=sum(1 for r in rows if r.status == STATUS_MATCH),
        mismatch=sum(1 for r in rows if r.status == STATUS_MISMATCH),
        missing_in_litellm=sum(1 for r in rows if r.status == STATUS_MISSING_IN_LITELLM),
        missing_in_self=sum(1 for r in rows if r.status == STATUS_MISSING_IN_SELF),
        cooldown_divergent=sum(1 for r in rows if r.cooldown_divergent),
    )
    consistent = (
        summary.mismatch == 0 and summary.missing_in_litellm == 0
        and summary.missing_in_self == 0
    )
    logger.info(f"影子对比完成: consistent={consistent} summary={summary}")
    return ShadowDiff(rows=tuple(rows), summary=summary)


async def capture_self_side_choice(
    session,
    *,
    resolve=None,
    chain=None,
    cooled=None,
) -> SelfSideChoice:
    """采集自研侧决策快照：复用既有选择逻辑（读结果，不重复实现）。

    缺省链路：llm_common.resolve_runtime_config（激活供应商三段解析）+
    ai_planner._candidate_chain（enabled/health 过滤 + priority 排序）+
    ai_planner._cooldown.is_cooled_down。三依赖均可注入（测试 stub 零 DB/Redis）；
    ai_planner 延迟 import——本模块加载不拉动业务编排域（子包边界，见 __init__）。
    兜底路径（provider_id=None，yml/env）返回 source="config" 的空链快照。
    """
    if resolve is None:
        from backend.services.llm_common import resolve_runtime_config as resolve
    if chain is None:
        from backend.services.ai_planner.llm_client import _candidate_chain as chain
    if cooled is None:
        from backend.services.ai_planner._cooldown import is_cooled_down as cooled

    logger.info("影子采集自研侧决策: resolve_runtime_config + _candidate_chain + cooldown")
    cfg = await resolve(session)
    if cfg.provider_id is None:
        return SelfSideChoice(
            provider_id=None, provider_name="config-fallback",
            base_url=cfg.base_url, primary_model=cfg.model,
            chain=(), cooled_models=frozenset(), source="config",
        )
    chain_pairs = tuple((m, t) for m, t in await chain(cfg.provider_id, session))
    cooled_hits = []
    for model_id, _tier in chain_pairs:
        if await cooled(cfg.provider_id, model_id):
            cooled_hits.append(model_id)
    cooled_models = frozenset(cooled_hits)
    logger.info(
        f"影子采集完成: provider_id={cfg.provider_id} chain={len(chain_pairs)} "
        f"cooled={sorted(cooled_models)}"
    )
    return SelfSideChoice(
        provider_id=cfg.provider_id,
        provider_name=f"provider:{cfg.provider_id}",
        base_url=cfg.base_url,
        primary_model=cfg.model,
        chain=chain_pairs,
        cooled_models=cooled_models,
        source=cfg.source,
    )
