"""T-42 / FR-105 真库保真轮（IMPL-QA-5 处置；仅 MYSQL_FIDELITY=1 执行）

背景：test_alert_queue_depth.py（sqlite 轮）对 session 用 fake_async_session 全桩，
queue_depth 命中行（notifications INSERT）与 user_id 外键从未打到真库。审查
IMPL-QA-5 裁定：qa 真库轮直验 notifications 行 + user_id FK。

本文件在 MYSQL_FIDELITY=1 时于真实 MySQL 8 独立 schema 上执行完整服务路径：
种子（租户/在册创建者/queue_depth 规则/3 条 pending 任务）→ AlertService 真
session（仅 notify_text 桩，避免外部渠道发送）→ evaluate_queue_depth → 断言
命中行字段 + last_triggered_at 落库 + 静默窗二连不重复 + user_id 外键负向探针
（伪造接收人必须被 MySQL FK 拒绝）。

未开 MYSQL_FIDELITY 时整文件 skip（sqlite create_all 无 FK 强制 / 方言差异，
跑不出本文件要证明的事——ESC-2 教训）。
"""
import os
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.services.alert_service import AlertService
from platform_core.models.alert_rule import AlertRule
from platform_core.models.notification import Notification
from platform_core.models.spider_task import SpiderTask
from platform_core.models.tenant import Tenant
from platform_core.models.user import User

_FIDELITY = os.environ.get("MYSQL_FIDELITY", "").strip().lower() in ("1", "true", "yes")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not _FIDELITY, reason="IMPL-QA-5 真库轮：需 MYSQL_FIDELITY=1（真 MySQL schema）"),
]


async def test_queue_depth_hit_row_real_mysql_with_fk_probe(db_session):
    """GWT-105.1 真库半：命中行 INSERT 落库 + user_id 外键真实生效

    覆盖 IMPL-QA-5 两个点名项：notifications 行字段（tenant/user/type/
    resource_type/resource_id/content 深度数字）、user_id FK（正例=创建者
    在册 id；负例=伪造 id 必被 FK 拒绝）。顺带真库复证静默窗不重复。
    """
    async with db_session() as session:
        # ---- 种子：租户 + 在册创建者 + queue_depth 规则（阈值 2）+ 3 条 pending ----
        tenant = Tenant(slug="fid-t42", name="真库轮租户")
        session.add(tenant)
        await session.flush()
        creator = User(
            tenant_id=tenant.id,
            username="alice",
            email="alice@fid-t42.local",
            password_hash="x-not-a-real-hash",
            is_active=True,
        )
        session.add(creator)
        rule = AlertRule(
            tenant_id=tenant.id,
            name="队列堆积告警",
            rule_type="queue_depth",
            threshold=2,
            window_minutes=60,
            severity="warning",
            enabled=True,
            created_by="alice",
        )
        session.add(rule)
        for _ in range(3):
            session.add(
                SpiderTask(
                    tenant_id=tenant.id,
                    spider_name="fid_spider",
                    status="pending",
                    created_by="alice",
                )
            )
        await session.commit()

        # ---- 服务路径：真 session / 真 repo（仅外部渠道发送桩掉）----
        svc = AlertService(session)
        svc._notify.notify_text = AsyncMock()

        triggered = await svc.evaluate_queue_depth()
        assert triggered == 1

        hits = (
            (
                await session.execute(
                    select(Notification).where(Notification.tenant_id == tenant.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(hits) == 1, "真库命中行必须恰好一条"
        hit = hits[0]
        assert hit.user_id == creator.id, "接收人=规则创建者（同租户在册解析）"
        assert hit.type == "alert"
        assert hit.resource_type == "alert_rule"
        assert hit.resource_id == rule.id
        assert "3" in (hit.content or ""), "内容含队列深度数字"

        await session.refresh(rule)
        assert rule.last_triggered_at is not None
        assert isinstance(rule.last_triggered_at, datetime)

        # ---- 静默窗（真库二连）：60 分钟内重复评估不重复落行 ----
        assert await svc.evaluate_queue_depth() == 0
        count_after_second = len(
            (
                await session.execute(
                    select(Notification).where(Notification.tenant_id == tenant.id)
                )
            )
            .scalars()
            .all()
        )
        assert count_after_second == 1

        # ---- user_id 外键负向探针：伪造接收人必须被 MySQL FK（1452）拒绝 ----
        session.add(
            Notification(
                tenant_id=tenant.id,
                user_id=999_999,  # 不存在的用户
                type="alert",
                title="fk-probe",
                resource_type="alert_rule",
                resource_id=rule.id,
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()
