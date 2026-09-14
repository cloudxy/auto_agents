"""告警规则服务 - 规则 CRUD + 规则匹配引擎

职责：
- 告警规则的增删改查
- 任务终态后评估所有活跃规则（consecutive_failures / result_drop / task_timeout）
- 调度器周期评估 queue_depth 规则（T-42 / FR-105 接通：通知 + notifications 命中行）
- 触发时通过 NotifyService 发送告警

约束：
- 告警评估失败不影响主流程（吞异常）
- 静默窗口内不重复触发
"""
import json
from datetime import datetime, timedelta
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.alert_rule_repository import AlertRuleRepository
from backend.repositories.spider_task_repository import SpiderTaskRepository
from backend.repositories.user_repository import UserRepository
from backend.services.notify_service import NotifyService
from platform_core.exceptions import NotFoundException
from platform_core.logger import get_logger
from platform_core.models.alert_rule import AlertRule
from platform_core.models.notification import Notification
from platform_core.models.spider_task import SpiderTask

logger = get_logger("api")


class AlertService:
    """告警规则 CRUD + 规则匹配引擎"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AlertRuleRepository(session)
        self._tasks = SpiderTaskRepository(session)
        self._users = UserRepository(session)
        self._notify = NotifyService()

    # --- CRUD ---
    async def list_rules(self) -> List[dict]:
        """获取所有告警规则"""
        rules = await self.repo.list_all()
        return [self._rule_to_dict(r) for r in rules]

    async def create_rule(self, payload: dict) -> dict:
        """创建告警规则"""
        # channels 序列化为 JSON 字符串存储
        channels = payload.pop("channels", None)
        if channels is not None:
            payload["channels"] = json.dumps(channels)
        rule = await self.repo.create(**payload)
        await self.session.commit()
        await self.session.refresh(rule)
        return self._rule_to_dict(rule)

    async def update_rule(self, rule_id: int, payload: dict) -> dict:
        """更新告警规则"""
        # channels 序列化为 JSON 字符串存储
        if "channels" in payload:
            channels = payload.pop("channels")
            if channels is not None:
                payload["channels"] = json.dumps(channels)
        rule = await self.repo.update(rule_id, **payload)
        if rule is None:
            raise NotFoundException(f"告警规则 {rule_id}")
        await self.session.commit()
        await self.session.refresh(rule)
        return self._rule_to_dict(rule)

    async def delete_rule(self, rule_id: int) -> dict:
        """删除告警规则"""
        deleted = await self.repo.delete(rule_id)
        if not deleted:
            raise NotFoundException(f"告警规则 {rule_id}")
        await self.session.commit()
        return {"rule_id": rule_id, "deleted": True}

    # --- 规则评估（任务终态路径）---
    async def evaluate(self, task_info: dict) -> None:
        """任务终态后评估所有活跃规则

        task_info: {"task_id": int, "spider_name": str, "status": str,
                    "result_count": int, "duration_seconds": float}
        """
        try:
            rules = await self.repo.list_active()
            for rule in rules:
                # 跳过不匹配的规则（spider_name 为 NULL 表示全局规则）
                if rule.spider_name and rule.spider_name != task_info.get("spider_name"):
                    continue
                # 跳过 queue_depth 类型（非任务终态口径；由调度器周期评估
                # —— evaluate_queue_depth，GWT-105.1 触发路径）
                if rule.rule_type == "queue_depth":
                    continue
                # 检查静默窗口
                if await self._is_in_silence(rule):
                    continue
                # 根据规则类型检查是否触发
                triggered = False
                message = ""
                if rule.rule_type == "consecutive_failures":
                    triggered = await self._check_consecutive_failures(rule, task_info)
                    if triggered:
                        message = f"连续失败次数达到 {int(rule.threshold)}"
                elif rule.rule_type == "result_drop":
                    triggered = await self._check_result_drop(rule, task_info)
                    if triggered:
                        message = f"结果数下降超过 {rule.threshold}%"
                elif rule.rule_type == "task_timeout":
                    triggered = await self._check_task_timeout(rule, task_info)
                    if triggered:
                        message = f"任务时长超过 {rule.threshold} 分钟"
                if triggered:
                    await self._send_alert(rule, task_info, message)
                    # 更新 last_triggered_at
                    rule.last_triggered_at = datetime.now()
                    await self.session.commit()
        except Exception as e:  # noqa: BLE001 告警评估失败不影响主流程
            logger.warning(f"告警评估失败（不影响主流程）: {e}")

    async def evaluate_queue_depth(self) -> int:
        """调度器周期评估 queue_depth 规则（FR-105 接通，GWT-105.1/105.3；db-spec §16.6）

        逐条评估全部租户启用的 queue_depth 规则（静默窗→深度→命中落库见
        _trigger_queue_depth_rule）；命中记录写面仅本调度器路径。任何失败只记
        日志不挡调度循环，返回本轮触发条数。
        """
        triggered = 0
        try:
            rules = await self.repo.list_queue_depth_rules()
            for rule in rules:
                if await self._trigger_queue_depth_rule(rule):
                    triggered += 1
        except Exception as e:  # noqa: BLE001 评估失败不挡调度循环
            logger.warning(f"queue_depth 规则评估失败（不影响调度循环）: {e}")
        return triggered

    async def _trigger_queue_depth_rule(self, rule: AlertRule) -> bool:
        """单条 queue_depth 规则评估：规则所属租户的排队任务深度超阈值则触发

        口径（db-spec §16.6）：经 NotifyService 已配置渠道发送 + notifications
        落命中行（type='alert'，resource_type='alert_rule'，user_id=规则创建者，
        content 含深度数字）+ last_triggered_at 推进（静默窗判据，与命中行同
        事务提交）。创建者软删/解析不出在册行 → 不落命中行、不发送、不静默
        改投（改投口径归 /pm）。
        """
        if await self._is_in_silence(rule):
            return False
        depth = await self._tasks.count_pending_by_tenant(rule.tenant_id)
        if depth <= rule.threshold:
            return False
        recipient_id = await self._users.get_active_id_by_username_in_tenant(
            rule.tenant_id, rule.created_by
        )
        if recipient_id is None:
            logger.warning(
                f"queue_depth 命中但创建者不可解析，跳过（不落命中行、不改投）: "
                f"rule_id={rule.id}, tenant_id={rule.tenant_id}, "
                f"created_by={rule.created_by}, depth={depth}"
            )
            return False
        severity = rule.severity or "warning"
        message = f"本企业排队任务数 {depth} 已超过阈值 {int(rule.threshold)}"
        # 渠道发送：NotifyService 内部逐渠道吞异常，失败不挡命中记录
        await self._notify.notify_text(
            event="alert.queue_depth",
            text=f"[告警:{severity}] {rule.name}: {message}",
        )
        self.session.add(Notification(
            tenant_id=rule.tenant_id,
            user_id=recipient_id,
            type="alert",
            title=f"[告警:{severity}] {rule.name}",
            content=(
                f"{message}（规则 #{rule.id}，类型 queue_depth，"
                f"静默窗 {rule.window_minutes or 60} 分钟）"
            ),
            resource_type="alert_rule",
            resource_id=rule.id,
        ))
        rule.last_triggered_at = datetime.now()
        await self.session.commit()
        logger.info(
            f"queue_depth 告警已触发: rule_id={rule.id}, "
            f"tenant_id={rule.tenant_id}, depth={depth}, "
            f"threshold={rule.threshold}, recipient={recipient_id}"
        )
        return True

    async def _check_consecutive_failures(self, rule: AlertRule, task_info: dict) -> bool:
        """查询该 spider 最近 N 条任务，连续失败次数 >= threshold 则触发"""
        spider_name = task_info.get("spider_name")
        threshold = int(rule.threshold)
        stmt = (
            select(SpiderTask.status)
            .where(SpiderTask.spider_name == spider_name)
            .order_by(SpiderTask.created_at.desc())
            .limit(threshold)
        )
        result = await self.session.execute(stmt)
        statuses = [row[0] for row in result.all()]
        # 如果最近 N 条全是 failed 则触发
        return len(statuses) >= threshold and all(s == "failed" for s in statuses)

    async def _check_result_drop(self, rule: AlertRule, task_info: dict) -> bool:
        """对比上一次 completed 任务的结果数，下降超过 threshold% 则触发"""
        spider_name = task_info.get("spider_name")
        current_count = task_info.get("result_count", 0)
        # 查询上一次 completed 任务（排除当前任务）
        stmt = (
            select(SpiderTask.result_count)
            .where(
                SpiderTask.spider_name == spider_name,
                SpiderTask.status == "completed",
                SpiderTask.id != task_info.get("task_id"),
            )
            .order_by(SpiderTask.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        prev_count = result.scalar()
        if prev_count is None or prev_count == 0:
            return False
        drop_percent = (prev_count - current_count) / prev_count * 100
        return drop_percent >= rule.threshold

    async def _check_task_timeout(self, rule: AlertRule, task_info: dict) -> bool:
        """任务时长超阈值（threshold 单位为分钟）"""
        duration_seconds = task_info.get("duration_seconds", 0)
        return duration_seconds > rule.threshold * 60

    async def _is_in_silence(self, rule: AlertRule) -> bool:
        """检查静默窗口（last_triggered_at + window_minutes > now → 跳过）"""
        if not rule.last_triggered_at:
            return False
        return datetime.now() < rule.last_triggered_at + timedelta(minutes=rule.window_minutes)

    async def _send_alert(self, rule: AlertRule, task_info: dict, message: str) -> None:
        """通过 NotifyService 发送告警"""
        try:
            await self._notify.notify_task_finished(
                task_id=task_info.get("task_id", 0),
                spider_name=task_info.get("spider_name", ""),
                status="alert",  # 特殊状态标识
                error_message=f"[告警:{rule.severity}] {rule.name}: {message}",
            )
            logger.info(f"告警已发送: rule={rule.name}, severity={rule.severity}, message={message}")
        except Exception as e:  # noqa: BLE001
            logger.error(f"告警发送失败: rule={rule.name}, error={e}")

    @staticmethod
    def _rule_to_dict(rule: AlertRule) -> dict:
        """ORM 实体转字典"""
        channels = None
        if rule.channels:
            try:
                channels = json.loads(rule.channels)
            except (json.JSONDecodeError, TypeError):
                channels = None
        return {
            "id": rule.id,
            "name": rule.name,
            "spider_name": rule.spider_name,
            "rule_type": rule.rule_type,
            "threshold": rule.threshold,
            "window_minutes": rule.window_minutes or 60,
            "severity": rule.severity or "warning",
            "channels": channels,
            "enabled": rule.enabled,
            "last_triggered_at": rule.last_triggered_at.isoformat() if rule.last_triggered_at else None,
            "created_at": rule.created_at.isoformat() if rule.created_at else None,
        }
