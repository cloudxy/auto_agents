"""系统配置服务单测 - ConfigService 网站基础信息（盲区补测）

约定：不连真实 MySQL，session 用 stubs.fake_async_session（execute 预设返回），
SystemConfig ORM 实例直接构造（无 DB 副作用）。

覆盖（核心公开方法直测）：
- get_config：命中返回值 / 未命中返回空串
- set_config：已存在更新值 / 不存在新增（session.add）+ commit
- get_all_configs：实体列表转 key→value 字典
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.config_service import ConfigService
from platform_core.models.system_config import SystemConfig
from stubs import fake_async_session


def _service(execute_return):
    session = fake_async_session()
    session.execute = AsyncMock(return_value=execute_return)
    return ConfigService(session), session


# ---------------- get_config ----------------
@pytest.mark.asyncio
async def test_get_config_returns_value_when_exists():
    """命中配置项：返回 config_value"""
    result = MagicMock()
    result.scalar_one_or_none.return_value = SystemConfig(
        config_key="site_name", config_value="Auto Agents")
    svc, _session = _service(result)

    assert await svc.get_config("site_name") == "Auto Agents"


@pytest.mark.asyncio
async def test_get_config_returns_empty_when_missing():
    """未命中配置项：返回空串（不抛异常）"""
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    svc, _session = _service(result)

    assert await svc.get_config("nope") == ""


# ---------------- set_config ----------------
@pytest.mark.asyncio
async def test_set_config_updates_existing_without_add():
    """已存在的 key：仅更新 config_value，不新增实体"""
    config = SystemConfig(config_key="site_name", config_value="old")
    result = MagicMock()
    result.scalar_one_or_none.return_value = config
    svc, session = _service(result)

    await svc.set_config("site_name", "new-value")

    assert config.config_value == "new-value"
    session.add.assert_not_called()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_config_creates_when_missing():
    """不存在的 key：构造新实体 add 进会话并 commit"""
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    svc, session = _service(result)

    await svc.set_config("site_name", "Auto Agents", description="站点名")

    session.add.assert_called_once()
    created = session.add.call_args.args[0]
    assert isinstance(created, SystemConfig)
    assert created.config_key == "site_name"
    assert created.config_value == "Auto Agents"
    session.commit.assert_awaited_once()


# ---------------- get_all_configs ----------------
@pytest.mark.asyncio
async def test_get_all_configs_maps_entities_to_dict():
    """全量配置转 key→value 字典（走 repo.get_all → session.execute 链）"""
    rows = [
        SystemConfig(config_key="site_name", config_value="Auto Agents"),
        SystemConfig(config_key="site_url", config_value="https://example.com"),
    ]
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    svc, _session = _service(result)

    got = await svc.get_all_configs()

    assert got == {"site_name": "Auto Agents", "site_url": "https://example.com"}
