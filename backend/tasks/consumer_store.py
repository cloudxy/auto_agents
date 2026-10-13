"""结果回流落库层 - SpiderTaskConsumer 的批量 / 单条落库（从 consumer.py 拆出，行为不变）

批量路径 _flush_batch（单 session、单次 commit）：
  按本批重算计数（m-5）→ 加载任务行（入队企业 + 多存储目标）→ 构建 SpiderResult
  （唯一键批内 / 库内去重，B5 + R2-1）→ 配额按租户旁路 hold 队列 → 批量累加
  result_count → commit → 提交后多存储镜像（R2-1）+ 无主消息死信并置任务失败。
单条路径 _ingest：保留供向后兼容 / 直接调用场景。

宿主约定（由 SpiderTaskConsumer 提供）：self._redis、self._engine()、self._fail_task()。
"""
import hashlib
import json
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.spider_result_repository import SpiderResultRepository
from backend.repositories.spider_task_repository import SpiderTaskRepository
from backend.services.spider_common import extract_store_targets
from config import settings
from platform_core.logger import get_logger
from platform_core.models.spider_result import SpiderResult
from platform_core.queues import DEAD_ITEM_QUEUE, TASK_RESULTS_KEY, item_hold_queue

logger = get_logger("api")


class ResultStoreMixin:
    """结果落库：批量 flush（去重 + 配额旁路 + 计数）、单条 ingest、多存储双写、无主拒收"""

    # ------------------------------------------------------------------
    # 批量落库：bulk insert + 批量 result_count 累加 + 多存储双写
    # ------------------------------------------------------------------
    async def _flush_batch(self, messages: list[dict], counts: dict[int, int]) -> None:
        """批量落库：bulk insert + 批量 result_count 累加 + 多存储双写

        单次 session 完成所有操作，最后统一 commit；
        增量去重（B5）和多存储镜像（4.2）均在此处理。

        counts 入参仅为兼容旧签名保留，实际不使用：flush 入口按本批
        messages 一次性重算计数（m-5 评审修复），保证 flush 失败重试
        幂等（去重扣减不跨轮次累计，详见 _recount_by_task）。
        """
        if not messages:
            return

        # ── 0. 按本批 messages 一次性重算计数（m-5 评审修复）──
        counts = self._recount_by_task(messages)

        async with AsyncSession(self._engine()) as session:
            # ── 1. 加载批次内涉及的任务行（入队企业 + 多存储目标）──
            task_store_cache, task_owner_cache = await self._load_batch_tasks(session, counts)
            # ── 2. 构建 SpiderResult 实例（跳过批内重复 / 库内已存在项）──
            instances, mirror_msgs, orphans = await self._build_batch_results(
                session, messages, counts, task_owner_cache
            )
            # ── 3. 配额按租户旁路，禁止单租户超额冻结全平台批次（归属=入队企业）──
            instances, mirror_msgs = await self._stage_with_quota(
                session, instances, mirror_msgs, counts
            )
            # ── 4. 批量累加 result_count ──
            await SpiderTaskRepository(session).batch_increment_result_counts(counts)
            # ── 5. 单次 commit ──
            await session.commit()

        # ── 6. 提交之后：多存储双写 + 无主消息拒收 ──
        await self._after_batch_commit(mirror_msgs, task_store_cache, orphans)

        logger.debug(
            f"批量落库完成: {len(messages)} 条消息, "
            f"{len(instances)} 条入库, {len(counts)} 个任务"
        )

    @staticmethod
    def _recount_by_task(messages: list[dict]) -> dict[int, int]:
        """按本批 messages 一次性重算 task_id → 条数（m-5 评审修复）

        调用方的 counts 在 flush 失败重试场景下会被上一轮的去重扣减污染
        （失败 → 同一批次连同已扣减的 counts 原样重试），继续在其上扣减
        会让重试轮次重复扣减、唯一未去重结果的计数被错误归零；
        本地按 messages 重算是幂等基准，调用方 dict 保持只读。
        """
        counts: dict[int, int] = {}
        for msg in messages:
            tid = msg["task_id"]
            counts[tid] = counts.get(tid, 0) + 1
        return counts

    async def _load_batch_tasks(
        self, session, counts: dict[int, int]
    ) -> tuple[dict[int, list[str]], dict[int, Optional[int]]]:
        """加载批次内涉及的任务行 → (task_id → 多存储目标, task_id → 入队企业)"""
        task_store_cache: dict[int, list[str]] = {}
        task_owner_cache: dict[int, Optional[int]] = {}
        for tid in counts:
            task = await SpiderTaskRepository(session).get_by_id(tid)
            task_store_cache[tid] = extract_store_targets(
                task.params if task else None
            )
            task_owner_cache[tid] = self._task_owner_id(task)
        return task_store_cache, task_owner_cache

    async def _build_batch_results(
        self, session, messages: list[dict], counts: dict[int, int],
        task_owner_cache: dict[int, Optional[int]],
    ) -> tuple[list[SpiderResult], list[tuple[int, dict]], list[dict]]:
        """构建 SpiderResult 实例 → (instances, mirror_msgs[(task_id, msg)], orphans)

        无主消息（找不到入队企业）收进 orphans；它与重复项一样扣减 counts，不计 result_count。
        """
        existing_cache = await self._batch_existing_hashes(session, messages, task_owner_cache)
        instances: list[SpiderResult] = []
        mirror_msgs: list[tuple[int, dict]] = []  # (task_id, msg)
        orphans: list[dict] = []
        # 唯一键 (tenant_id, spider_name, content_hash) 对全部任务生效（不止 incremental）：
        # 批内重复与库内已存在都必须在 flush 前剔除，否则整批 IntegrityError（审计 R2-1）
        seen_keys: set[tuple[int, str, str]] = set()
        for msg in messages:
            task_id = msg["task_id"]
            owner_id = task_owner_cache.get(task_id)
            if owner_id is None:
                orphans.append(msg)
                counts[task_id] = max(0, counts.get(task_id, 0) - 1)
                continue
            instance = self._admit_result(msg, owner_id, seen_keys, existing_cache, counts)
            if instance is not None:
                instances.append(instance)
                mirror_msgs.append((task_id, msg))
        return instances, mirror_msgs, orphans

    async def _batch_existing_hashes(
        self, session, messages: list[dict], task_owner_cache: dict[int, Optional[int]],
    ) -> dict[tuple[int, str], set[str]]:
        """按 (入队企业, 爬虫) 分组一次查完库内已存在的 content_hash（无主消息不查）"""
        result_repo = SpiderResultRepository(session)
        pending_hashes: dict[tuple[int, str], list[str]] = {}
        for msg in messages:
            owner = task_owner_cache.get(msg["task_id"])
            if owner is None:
                continue
            item0 = msg.get("item") or {}
            pending_hashes.setdefault((owner, msg.get("spider_name", "")), []).append(
                self._content_hash(item0)
            )
        existing_cache: dict[tuple[int, str], set[str]] = {}
        for (owner, spider), hashes in pending_hashes.items():
            existing_cache[(owner, spider)] = await result_repo.existing_hashes(
                owner, spider, hashes
            )
        return existing_cache

    def _admit_result(
        self, msg: dict, owner_id: int, seen_keys: set[tuple[int, str, str]],
        existing_cache: dict[tuple[int, str], set[str]], counts: dict[int, int],
    ) -> Optional[SpiderResult]:
        """单条有主消息 → SpiderResult；批内重复或库内已存在则扣减 counts 并返回 None"""
        task_id = msg["task_id"]
        spider_name = msg.get("spider_name", "")
        item = msg.get("item") or {}

        # B1：数据质量评分（与 _ingest 一致，pop 避免进 extra）
        quality_score = item.pop("_quality_score", None)

        # B5：content_hash = md5(url + title + content)
        url_val = str(item.get("url") or "")[:500]
        content_hash = self._content_hash(item)

        # 去重（B5 + R2-1）：批内重复或库内已存在 → 跳过，不计 result_count
        key = (owner_id, spider_name, content_hash)
        if key in seen_keys or content_hash in existing_cache.get((owner_id, spider_name), set()):
            logger.debug(f"重复内容已跳过: hash={content_hash}, url={url_val}")
            counts[task_id] = max(0, counts[task_id] - 1)
            return None
        seen_keys.add(key)
        return SpiderResult(**self._result_fields(msg, item, owner_id, quality_score, content_hash))

    async def _stage_with_quota(
        self, session, instances: list[SpiderResult],
        mirror_msgs: list[tuple[int, dict]], counts: dict[int, int],
    ) -> tuple[list[SpiderResult], list[tuple[int, dict]]]:
        """配额按租户旁路：通过者 add_all 进会话；超限租户的消息转 hold 队列且不计 result_count

        返回 (保留实例, 保留镜像消息)；instances 为空时无任何副作用（不查配额、不 add_all）。
        """
        quota_ok: set[int] = set()
        quota_blocked: set[int] = set()
        kept_instances: list[SpiderResult] = []
        kept_mirrors: list[tuple[int, dict]] = []
        held: dict[int, list[dict]] = {}
        for inst, (tid, msg) in zip(instances, mirror_msgs):
            t_id = inst.tenant_id
            if not await self._quota_allows(session, t_id, quota_ok, quota_blocked):
                held.setdefault(t_id, []).append(msg)
                counts[tid] = max(0, counts.get(tid, 1) - 1)
                continue
            kept_instances.append(inst)
            kept_mirrors.append((tid, msg))
        if kept_instances:
            session.add_all(kept_instances)
        for t_id, parked in held.items():
            await self._park_messages(item_hold_queue(t_id), parked)
        return kept_instances, kept_mirrors

    @staticmethod
    async def _quota_allows(session, t_id, quota_ok: set[int], quota_blocked: set[int]) -> bool:
        """租户结果存储配额判定：本批内按租户缓存结论；非 int 归属不查配额直接放行"""
        from backend.services.quota_service import QuotaExceededException, QuotaService

        if not isinstance(t_id, int):
            return True
        if t_id in quota_blocked:
            return False
        if t_id in quota_ok:
            return True
        try:
            await QuotaService(session).check_result_storage(t_id)
            quota_ok.add(t_id)
        except QuotaExceededException:
            quota_blocked.add(t_id)
            logger.warning(
                f"结果存储配额超限，消息旁路 hold 队列: tenant={t_id}"
            )
            return False
        return True

    async def _after_batch_commit(
        self, mirror_msgs: list[tuple[int, dict]],
        task_store_cache: dict[int, list[str]], orphans: list[dict],
    ) -> None:
        """提交之后：多存储双写（4.2）+ 无主消息拒收（死信 + 任务失败）

        只镜像已提交的结果（审计 R2-1：原先先镜像后提交，提交失败重放会重复镜像）；
        镜像失败不回滚已落库数据，只记日志。
        """
        try:
            await self._mirror_batch(mirror_msgs, task_store_cache)
        except Exception as e:  # noqa: BLE001
            logger.error(f"多存储镜像失败（结果已落库）: n={len(mirror_msgs)} error={e}")

        for orphan in orphans:
            await self._reject_orphan_item(
                orphan, orphan.get("task_id"), "回流找不到入队企业",
            )

    @staticmethod
    def _result_fields(
        msg: dict, item: dict, owner_id: int, quality_score, content_hash: str,
    ) -> dict:
        """回流消息 → SpiderResult 列值（批量 / 单条同口径；未映射字段进 extra）"""
        url_val = str(item.get("url") or "")[:500]
        # 未映射字段进 extra
        mapped = {"url", "title", "content", "source"}
        extra = {k: v for k, v in item.items() if k not in mapped}
        return {
            "task_id": msg["task_id"],
            "spider_name": msg.get("spider_name", ""),
            "tenant_id": owner_id,
            "item_type": msg.get("item_type", "BaseItem"),
            "url": url_val or None,
            "title": item.get("title"),
            "content": item.get("content"),
            "source": item.get("source"),
            "extra": json.dumps(extra, ensure_ascii=False, default=str) if extra else None,
            "quality_score": quality_score,
            "content_hash": content_hash,
        }

    async def _park_messages(self, queue: str, messages: list[dict]) -> None:
        """把已出队消息写入旁路队列，避免配额/flush 失败时内存无界或丢批。"""
        if not messages or self._redis is None:
            return
        payload = [json.dumps(m, ensure_ascii=False, default=str) for m in messages]
        try:
            await self._redis.rpush(queue, *payload)
        except Exception as e:  # noqa: BLE001
            logger.error(f"旁路入队失败 queue={queue} n={len(payload)}: {e}")

    async def _mirror_batch(
        self,
        mirror_msgs: list[tuple[int, dict]],
        task_store_cache: dict[int, list[str]],
    ) -> None:
        """批量多存储双写：按 task_id 分组 rpush 到对应 TASK_RESULTS_KEY"""
        ttl = int(settings.get("STORAGE.REDIS_RESULT_TTL", 604800))
        # 按 task_id 聚合，减少 Redis 调用次数
        grouped: dict[int, list[str]] = {}
        for task_id, msg in mirror_msgs:
            targets = task_store_cache.get(task_id, [])
            if not targets:
                continue
            key = TASK_RESULTS_KEY.format(task_id=task_id)
            grouped.setdefault(task_id, []).append(
                json.dumps(msg, ensure_ascii=False, default=str)
            )
        for task_id, payloads in grouped.items():
            try:
                key = TASK_RESULTS_KEY.format(task_id=task_id)
                await self._redis.rpush(key, *payloads)
                await self._redis.expire(key, ttl)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"批量结果缓存双写失败: task_id={task_id}, error={e}")

    # ------------------------------------------------------------------
    # 结果归属 / 无主拒收
    # ------------------------------------------------------------------
    @staticmethod
    def _task_owner_id(task) -> Optional[int]:
        """入队企业：只认任务行 tenant_id。工人消息里的 tenant 不是归属。"""
        if task is None:
            return None
        raw = getattr(task, "tenant_id", None)
        if raw is None:
            return None
        try:
            tid = int(raw)
        except (TypeError, ValueError):
            return None
        return tid if tid > 0 else None

    async def _reject_orphan_item(self, msg: dict, task_id, reason: str) -> None:
        """无主回流：不写入「我的结果」；死信留档；任务侧可查失败。"""
        logger.warning(
            f"回流无入队企业，不落结果: task_id={task_id}, reason={reason}"
        )
        dead = dict(msg)
        dead["_reject_reason"] = reason
        try:
            await self._redis.rpush(
                DEAD_ITEM_QUEUE, json.dumps(dead, ensure_ascii=False, default=str)
            )
        except Exception as e:  # noqa: BLE001 死信失败不阻断主路径
            logger.error(f"无主回流死信写入失败: task_id={task_id}, error={e}")
        if task_id:
            await self._fail_task(task_id, reason)

    # ------------------------------------------------------------------
    # 单条结果回流（保留供向后兼容 / 直接调用场景）
    # ------------------------------------------------------------------
    async def _ingest(self, msg: dict) -> None:
        """单条落库：唯一键去重 → 写结果 → 多存储双写；无入队企业转死信并置任务失败"""
        task_id = msg.get("task_id")
        spider_name = msg.get("spider_name", "")
        item = msg.get("item") or {}
        if not task_id:
            logger.warning(f"结果消息缺少 task_id，跳过: spider={spider_name}")
            return

        item_type = msg.get("item_type", "BaseItem")
        # 数据质量评分（B1）：由 Scrapy 侧 QualityCheckPipeline 写入 item
        quality_score = item.pop("_quality_score", None)

        # B5：计算 content_hash（md5 of url+title+content），用于去重
        url_val = str(item.get("url") or "")[:500]
        content_hash = self._content_hash(item)

        async with AsyncSession(self._engine()) as session:
            task = await SpiderTaskRepository(session).get_by_id(task_id)
            owner_id = self._task_owner_id(task)
            if owner_id is not None:
                # 唯一键对全部任务生效：重复内容一律跳过（审计 R2-1，不止 incremental）
                existing = await SpiderResultRepository(session).find_by_content_hash(
                    content_hash, tenant_id=owner_id, spider_name=spider_name or None,
                )
                if existing:
                    logger.debug(f"重复内容已跳过: hash={content_hash}, url={url_val}")
                    return
                await SpiderResultRepository(session).create_for_task(
                    **self._result_fields(msg, item, owner_id, quality_score, content_hash)
                )
                await session.commit()
                # 数据源多存储（4.2）：store_to 命中 redis/csv 时追加任务级结果缓存列表，
                # redis 目标供直读，csv 目标终态后由 Service 落盘（失败不影响落库主路径）
                await self._mirror_result(session, task_id, msg)
        if owner_id is None:
            await self._reject_orphan_item(msg, task_id, "回流找不到入队企业")
            return
        logger.info(f"结果已落库: task_id={task_id}, spider={spider_name}, item={item_type}")

    async def _mirror_result(self, session, task_id: int, msg: dict) -> None:
        """数据源多存储双写（4.2）：查任务 store_to，命中则追加任务级结果缓存列表"""
        logger.debug(f"检查结果缓存双写目标: task_id={task_id}")
        try:
            task = await SpiderTaskRepository(session).get_by_id(task_id)
            targets = extract_store_targets(task.params if task else None)
            if not targets:
                return
            key = TASK_RESULTS_KEY.format(task_id=task_id)
            await self._redis.rpush(key, json.dumps(msg, ensure_ascii=False, default=str))
            ttl = int(settings.get("STORAGE.REDIS_RESULT_TTL", 604800))
            await self._redis.expire(key, ttl)
        except Exception as e:  # noqa: BLE001 双写失败仅告警，不影响落库主路径
            logger.warning(f"结果缓存双写失败: task_id={task_id}, error={e}")

    @staticmethod
    def _content_hash(item: dict) -> str:
        """B5 内容指纹：md5(url[:500] + title + content)，与唯一键 content_hash 同口径"""
        url_val = str(item.get("url") or "")[:500]
        title_val = item.get("title") or ""
        content_val = item.get("content") or ""
        return hashlib.md5(f"{url_val}{title_val}{content_val}".encode()).hexdigest()
