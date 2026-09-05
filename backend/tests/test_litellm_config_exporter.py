"""L1 配置导出器测试：build 纯函数 + fetch 过滤（sqlite）+ 端到端写文件

覆盖：正常导出 / 子表空走父表兜底 / 非支持协议跳过 / 空供应商回退（空
model_list + empty 标记，CLI 非零退出码依据）/ 密钥不落日志与结果对象、
文件权限 0600。
"""
import os
import stat
from datetime import datetime

import pytest
import yaml

from backend.services.litellm.exporter import (
    ModelExportRow,
    ProviderExportRow,
    build_litellm_config,
    export_litellm_config,
    fetch_export_rows,
    render_config_yaml,
)
from platform_core.models.llm_provider import LlmProvider
from platform_core.models.llm_provider_model import LlmProviderModel


def _row(pid=1, name="OpenAI Main", base="https://api.example.com/v1",
         key="sk-plain-key", protocol="openai_compatible",
         models=(), fallback="gpt-4o-mini") -> ProviderExportRow:
    return ProviderExportRow(
        provider_id=pid, name=name, base_url=base, api_key=key,
        protocol=protocol, fallback_model=fallback, models=models,
    )


class TestBuildPure:
    """build_litellm_config 纯函数（零 DB）"""

    def test_two_providers_multi_models(self):
        rows = [
            _row(pid=1, name="OpenAI Main", models=(
                ModelExportRow("gpt-4o-mini", "basic", 100, True),
                ModelExportRow("gpt-4o", "strong", 200, False),
            )),
            _row(pid=2, name="DeepSeek 备", base="https://api.deepseek.com/v1",
                 models=(ModelExportRow("deepseek-chat", "basic", 100, True),)),
        ]
        config = build_litellm_config(rows)
        assert len(config["model_list"]) == 3
        first = config["model_list"][0]
        # 默认行首位（fetch 已按 (not is_default, priority) 排序，build 保序）
        assert first["model_name"] == "openai-main/gpt-4o-mini"
        assert first["litellm_params"]["model"] == "openai/gpt-4o-mini"
        assert first["litellm_params"]["api_base"] == "https://api.example.com/v1"
        assert first["litellm_params"]["api_key"] == "sk-plain-key"
        assert config["model_list"][1]["model_name"] == "openai-main/gpt-4o"
        # 中文名 slug 化（稳定可读，非字母数字 → 连字符）
        assert config["model_list"][2]["model_name"] == "deepseek/deepseek-chat"

    def test_empty_models_fallback_to_parent_default(self):
        config = build_litellm_config([_row(models=(), fallback="qwen-max")])
        assert len(config["model_list"]) == 1
        assert config["model_list"][0]["litellm_params"]["model"] == "openai/qwen-max"

    def test_unsupported_protocol_skipped(self):
        config = build_litellm_config([_row(protocol="some_future_protocol")])
        assert config["model_list"] == []

    def test_missing_key_or_base_skipped(self):
        assert build_litellm_config([_row(key="")])["model_list"] == []
        assert build_litellm_config([_row(base="")])["model_list"] == []
        assert build_litellm_config([_row(models=(), fallback="")])["model_list"] == []

    def test_empty_rows_empty_model_list(self):
        config = build_litellm_config([])
        assert config["model_list"] == []
        assert config["litellm_settings"] == {"drop_params": True}

    def test_render_contains_security_header_not_key_in_log_fields(self):
        text = render_config_yaml(build_litellm_config([_row()]))
        assert "禁止提交版本库" in text
        # 回读一致（yaml 往返）
        loaded = yaml.safe_load(text.split("\n", 2)[2])
        assert loaded["model_list"][0]["litellm_params"]["api_key"] == "sk-plain-key"


class TestFetchDb:
    """fetch_export_rows 过滤口径（sqlite 真表）"""

    @pytest.mark.asyncio
    async def test_filters_disabled_softdeleted_and_down_models(self, db_session):
        async with db_session() as session:
            p1 = LlmProvider(name="active-1", base_url="https://a.com/v1", model="m-default",
                             api_key_encrypted="cipher-1", is_active=True, enabled=True)
            p2 = LlmProvider(name="disabled-2", base_url="https://b.com/v1", model="m",
                             is_active=False, enabled=False)
            p3 = LlmProvider(name="softdel-3", base_url="https://c.com/v1", model="m",
                             deleted_at=datetime(2026, 1, 1))
            session.add_all([p1, p2, p3])
            await session.flush()
            session.add_all([
                LlmProviderModel(provider_id=p1.id, model_id="m-default", is_default=True,
                                 priority=10, model_tier="strong", health_status="healthy"),
                LlmProviderModel(provider_id=p1.id, model_id="m-down", priority=20,
                                 health_status="down"),      # down 过滤
                LlmProviderModel(provider_id=p1.id, model_id="m-off", priority=30,
                                 enabled=False),              # 禁用过滤
                LlmProviderModel(provider_id=p2.id, model_id="x", health_status="healthy"),
            ])
            await session.commit()

            rows = await fetch_export_rows(
                session, decrypt=lambda c: "sk-decrypted" if c == "cipher-1" else "")
        assert [r.provider_id for r in rows] == [p1.id]
        assert rows[0].api_key == "sk-decrypted"
        assert [m.model_id for m in rows[0].models] == ["m-default"]

    @pytest.mark.asyncio
    async def test_no_active_providers_returns_empty(self, db_session):
        async with db_session() as session:
            rows = await fetch_export_rows(session, decrypt=lambda c: "")
        assert rows == []


class TestExportEndToEnd:
    """端到端：写文件 + 权限 + 空回退语义"""

    @pytest.mark.asyncio
    async def test_export_writes_file_with_0600(self, db_session, tmp_path):
        async with db_session() as session:
            session.add(LlmProvider(name="OpenAI Main", base_url="https://a.com/v1/",
                                    model="gpt-4o-mini", api_key_encrypted="cipher-1",
                                    is_active=True, enabled=True))
            await session.commit()
            out = tmp_path / "nested" / "config.gen.yaml"
            result = await export_litellm_config(
                session, out_path=str(out), decrypt=lambda c: "sk-xyz")

        assert result.empty is False
        assert result.provider_count == 1 and result.model_count == 1
        assert out.exists()
        mode = stat.S_IMODE(os.stat(out).st_mode)
        assert mode == 0o600, f"明文 key 文件权限应为 0600，实际 {oct(mode)}"
        loaded = yaml.safe_load(out.read_text(encoding="utf-8").split("\n", 2)[2])
        entry = loaded["model_list"][0]
        # base_url 去尾斜杠 + 父表兜底模型展开
        assert entry["litellm_params"]["api_base"] == "https://a.com/v1"
        assert entry["litellm_params"]["model"] == "openai/gpt-4o-mini"
        # 结果对象不含密钥（可安全打印）
        assert "sk-xyz" not in repr(result)

    @pytest.mark.asyncio
    async def test_export_empty_fallback_marks_empty(self, db_session, tmp_path):
        async with db_session() as session:
            out = tmp_path / "config.gen.yaml"
            result = await export_litellm_config(session, out_path=str(out))
        assert result.empty is True
        loaded = yaml.safe_load(out.read_text(encoding="utf-8").split("\n", 2)[2])
        assert loaded["model_list"] == []
        assert result.provider_count == 0 and result.model_count == 0
