"""L1 影子只读对比器测试：三态 fixture（一致 / 不一致 / 单侧缺）+ 冷却分层差异

全程零外呼：compare_routing 是纯函数，capture_self_side_choice 的三依赖
（resolve/chain/cooled）以 stub 注入——不连 DB、不连 Redis、不发 LLM 请求。
"""
import pytest

from backend.services.litellm.exporter import build_litellm_config, ModelExportRow, ProviderExportRow
from backend.services.litellm.shadow import (
    LitellmDeployment,
    SelfSideChoice,
    STATUS_MATCH,
    STATUS_MISMATCH,
    STATUS_MISSING_IN_LITELLM,
    STATUS_MISSING_IN_SELF,
    capture_self_side_choice,
    compare_routing,
    load_deployments_from_config,
)


def _self_side(chain=(("gpt-4o-mini", "basic"), ("gpt-4o", "strong")),
               base="https://api.example.com/v1", cooled=frozenset()) -> SelfSideChoice:
    return SelfSideChoice(
        provider_id=1, provider_name="provider:1", base_url=base,
        primary_model=chain[0][0] if chain else "gpt-4o-mini",
        chain=tuple(chain), cooled_models=frozenset(cooled), source="provider:1",
    )


def _deployments(entries) -> list[LitellmDeployment]:
    return [
        LitellmDeployment(
            model_name=f"{label}/{model_id}", model_id=model_id,
            api_base=api_base, provider_label=label, cooled=cooled,
        )
        for label, model_id, api_base, cooled in entries
    ]


class TestLoadDeployments:
    def test_parse_generated_config(self):
        config = build_litellm_config([
            ProviderExportRow(
                provider_id=1, name="OpenAI Main", base_url="https://a.com/v1",
                api_key="sk-x", protocol="openai_compatible", fallback_model="m",
                models=(ModelExportRow("gpt-4o-mini", "basic", 100, True),),
            )
        ])
        ds = load_deployments_from_config(config)
        assert len(ds) == 1
        assert ds[0].model_id == "gpt-4o-mini"          # 协议前缀已剥离
        assert ds[0].provider_label == "openai-main"
        assert ds[0].api_base == "https://a.com/v1"

    def test_empty_config(self):
        assert load_deployments_from_config({}) == []
        assert load_deployments_from_config(None) == []


class TestCompareThreeStates:
    """票面三类：两侧一致 / 不一致 / 单侧缺供应商"""

    def test_all_match(self):
        diff = compare_routing(_self_side(), _deployments([
            ("openai-main", "gpt-4o-mini", "https://api.example.com/v1", False),
            ("openai-main", "gpt-4o", "https://api.example.com/v1", False),
        ]))
        assert diff.consistent
        assert [r.status for r in diff.rows] == [STATUS_MATCH, STATUS_MATCH]
        assert diff.summary.match == 2

    def test_mismatch_on_base_url_divergence(self):
        """同一 model 两侧指向不同上游（model→provider 映射差异）"""
        diff = compare_routing(_self_side(), _deployments([
            ("other", "gpt-4o-mini", "https://elsewhere.com/v1", False),
            ("openai-main", "gpt-4o", "https://api.example.com/v1", False),
        ]))
        assert not diff.consistent
        by_model = {r.model_id: r for r in diff.rows}
        assert by_model["gpt-4o-mini"].status == STATUS_MISMATCH
        assert by_model["gpt-4o"].status == STATUS_MATCH
        assert diff.summary.mismatch == 1

    def test_aggregate_deployments_cover_self_base(self):
        """LiteLLM 多 deployment 聚合路由：自研 base 命中集合任一即 match"""
        diff = compare_routing(
            _self_side(chain=(("gpt-4o-mini", "basic"),)),
            _deployments([
                ("a", "gpt-4o-mini", "https://pool-1.com/v1", False),
                ("b", "gpt-4o-mini", "https://api.example.com/v1", False),
            ]),
        )
        assert diff.rows[0].status == STATUS_MATCH
        assert len(diff.rows[0].litellm_api_bases) == 2

    def test_missing_in_litellm(self):
        """自研候选链有、LiteLLM config 无（导出面缺该模型）"""
        diff = compare_routing(_self_side(), _deployments([
            ("openai-main", "gpt-4o-mini", "https://api.example.com/v1", False),
        ]))
        assert not diff.consistent
        by_model = {r.model_id: r for r in diff.rows}
        assert by_model["gpt-4o"].status == STATUS_MISSING_IN_LITELLM
        assert by_model["gpt-4o"].litellm_api_bases == ()
        assert diff.summary.missing_in_litellm == 1

    def test_missing_in_self(self):
        """LiteLLM config 有、自研候选链无（如 down 模型被自研过滤）"""
        diff = compare_routing(
            _self_side(chain=(("gpt-4o-mini", "basic"),)),
            _deployments([
                ("openai-main", "gpt-4o-mini", "https://api.example.com/v1", False),
                ("openai-main", "gpt-4o", "https://api.example.com/v1", False),
            ]),
        )
        assert not diff.consistent
        by_model = {r.model_id: r for r in diff.rows}
        assert by_model["gpt-4o"].status == STATUS_MISSING_IN_SELF
        assert diff.summary.missing_in_self == 1


class TestCooldownLayering:
    """冷却差异：自研 Redis 冷却 vs LiteLLM 进程内存冷却（已知分层共存）"""

    def test_self_coiled_litellm_unaware_marks_known_layering(self):
        diff = compare_routing(
            _self_side(cooled={"gpt-4o-mini"}),
            _deployments([
                ("openai-main", "gpt-4o-mini", "https://api.example.com/v1", False),
                ("openai-main", "gpt-4o", "https://api.example.com/v1", False),
            ]),
        )
        row = diff.rows[0]
        # 路由面仍一致（consistent 只看路由，冷却差异记录不阻断）
        assert diff.consistent
        assert row.status == STATUS_MATCH
        assert row.self_cooled and not row.litellm_cooled
        assert row.cooldown_divergent and row.known_layering
        assert diff.summary.cooldown_divergent == 1

    def test_both_coiled_consistent(self):
        diff = compare_routing(
            _self_side(cooled={"gpt-4o-mini"}),
            _deployments([("openai-main", "gpt-4o-mini", "https://api.example.com/v1", True)]),
        )
        row = diff.rows[0]
        assert not row.cooldown_divergent and not row.known_layering

    def test_litellm_only_coiled_divergent_but_not_known_layering(self):
        """仅 LiteLLM 冷却（proxy 进程内状态，L1 无法归因）：divergent 但不标 known"""
        diff = compare_routing(
            _self_side(),
            _deployments([("openai-main", "gpt-4o-mini", "https://api.example.com/v1", True)]),
        )
        row = diff.rows[0]
        assert row.cooldown_divergent and not row.known_layering


class TestCapture:
    """capture_self_side_choice：依赖全注入（零 DB/Redis），覆盖兜底与正常分支"""

    @pytest.mark.asyncio
    async def test_config_fallback_branch(self):
        from backend.services.llm_common import LlmRuntimeConfig

        async def fake_resolve(session):
            return LlmRuntimeConfig(
                base_url="https://cfg.example.com/v1", api_key="", model="cfg-model",
                temperature=0.2, timeout=120, max_retries=3, enabled=False, source="config",
            )

        choice = await capture_self_side_choice(session=None, resolve=fake_resolve)
        assert choice.provider_id is None
        assert choice.source == "config"
        assert choice.chain == () and choice.primary_model == "cfg-model"

    @pytest.mark.asyncio
    async def test_provider_branch_with_chain_and_cooldown(self):
        from backend.services.llm_common import LlmRuntimeConfig

        async def fake_resolve(session):
            return LlmRuntimeConfig(
                base_url="https://p.example.com/v1", api_key="k", model="m1",
                temperature=0.2, timeout=120, max_retries=3, enabled=True,
                source="provider:7", provider_id=7,
            )

        async def fake_chain(pid, session=None):
            assert pid == 7
            return [("m1", "strong"), ("m2", "basic")]

        async def fake_cooled(pid, model_id):
            return model_id == "m2"

        choice = await capture_self_side_choice(
            session=None, resolve=fake_resolve, chain=fake_chain, cooled=fake_cooled)
        assert choice.provider_id == 7
        assert choice.chain == (("m1", "strong"), ("m2", "basic"))
        assert choice.cooled_models == frozenset({"m2"})
