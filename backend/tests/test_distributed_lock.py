"""共享分布式锁设施单测 - platform_core.queues.distributed_lock

覆盖（任务 #25 验收项）：
- 获取成功：yield 句柄 + Redis 值为唯一 token（uuid hex，非旧实现的固定值 "1"）
- 竞争失败：同 key 二次抢占 yield None（调用方早退跳过语义），原值不被覆盖
- 释放原子性：token 不匹配（锁已易主）时不删除他人的锁；早退/异常路径同样释放
- 续期：成功续期 / 失败感知（renew() 返回 False + lost=True，调用方主动退出）
- 后台续期任务（renewal 参数）：异常安全、release 收尾无悬挂任务
- 异常安全：Redis set/eval 抛异常时不向上传播（保守跳过 / TTL 兑底）

约定：不连真实 Redis，用内存 Fake（SET NX / GET / Lua eval 语义）。
"""
import asyncio

import pytest

from platform_core.queues import distributed_lock
from stubs import FakeRedis  # 共享桩（唯一定义处见 stubs.py，语义并集）

LOCK_KEY = "test:lock:key"


# ---------------- 获取：成功 / 竞争失败 / 故障保守跳过 ----------------
class TestAcquire:
    @pytest.mark.asyncio
    async def test_acquire_yields_handle_with_unique_token(self):
        """获取成功：yield 句柄，Redis 值 = 唯一 token（非旧实现的固定值 "1"）"""
        redis = FakeRedis()
        async with distributed_lock(redis, LOCK_KEY, ttl=60) as lock:
            assert lock is not None
            assert len(lock.token) == 32  # uuid4 hex
            assert redis.strings[LOCK_KEY] == lock.token

    @pytest.mark.asyncio
    async def test_acquire_contended_yields_none(self):
        """竞争失败：锁被他人持有时 yield None（跳过本轮），且不覆盖他人锁值"""
        redis = FakeRedis()
        redis.strings[LOCK_KEY] = "holder-token"
        async with distributed_lock(redis, LOCK_KEY, ttl=60) as lock:
            assert lock is None
        assert redis.strings[LOCK_KEY] == "holder-token"

    @pytest.mark.asyncio
    async def test_acquire_redis_error_skips_conservatively(self):
        """Redis 故障：获取异常按未抢到处理（保守跳过，不向上抛）"""
        redis = FakeRedis()

        async def boom(*args, **kwargs):
            raise RuntimeError("redis down")

        redis.set = boom
        async with distributed_lock(redis, LOCK_KEY, ttl=60) as lock:
            assert lock is None

    @pytest.mark.asyncio
    async def test_mutual_exclusion_between_two_holders(self):
        """互斥：持锁期间他人抢占失败；释放后他人可正常获取"""
        redis = FakeRedis()
        async with distributed_lock(redis, LOCK_KEY, ttl=60) as first:
            assert first is not None
            async with distributed_lock(redis, LOCK_KEY, ttl=60) as second:
                assert second is None  # 互斥
        async with distributed_lock(redis, LOCK_KEY, ttl=60) as third:
            assert third is not None  # 释放后可重新抢占


# ---------------- 释放：主动释放 / 原子性 / 异常兜底 ----------------
class TestRelease:
    @pytest.mark.asyncio
    async def test_release_removes_own_lock_on_exit(self):
        """with 正常退出即主动释放（不等 TTL 过期）"""
        redis = FakeRedis()
        async with distributed_lock(redis, LOCK_KEY, ttl=60):
            assert LOCK_KEY in redis.strings
        assert LOCK_KEY not in redis.strings

    @pytest.mark.asyncio
    async def test_release_atomic_token_mismatch_keeps_others(self):
        """释放原子性：锁已易主（token 不匹配）时不删除他人的锁"""
        redis = FakeRedis()
        async with distributed_lock(redis, LOCK_KEY, ttl=1) as lock:
            assert lock is not None
            redis.strings[LOCK_KEY] = "thief-token"  # 模拟 TTL 过期后被他人抢占
        assert redis.strings[LOCK_KEY] == "thief-token"  # 他人锁未被误删

    @pytest.mark.asyncio
    async def test_release_on_exception_path(self):
        """临界区异常路径同样释放（对齐原评审 m-1 语义）"""
        redis = FakeRedis()
        with pytest.raises(RuntimeError, match="boom"):
            async with distributed_lock(redis, LOCK_KEY, ttl=60) as lock:
                assert lock is not None
                raise RuntimeError("boom")
        assert LOCK_KEY not in redis.strings

    @pytest.mark.asyncio
    async def test_release_eval_error_swallowed(self):
        """释放时 Redis 故障不向上抛（交由 TTL 兑底）"""
        redis = FakeRedis()

        async def boom(*args, **kwargs):
            raise RuntimeError("redis down")

        redis.eval = boom
        async with distributed_lock(redis, LOCK_KEY, ttl=60) as lock:
            assert lock is not None  # 获取用 set，不受影响
        # with 退出时 release 内部 eval 异常被吞掉，不传播


# ---------------- 续期：手动感知 / 后台任务 / 异常安全 ----------------
class TestRenewal:
    @pytest.mark.asyncio
    async def test_renew_success(self):
        """持锁期间原子续期成功，lost 保持 False"""
        redis = FakeRedis()
        async with distributed_lock(redis, LOCK_KEY, ttl=60) as lock:
            assert await lock.renew() is True
            assert lock.lost is False

    @pytest.mark.asyncio
    async def test_renew_failure_signals_lost(self):
        """续期失败感知：锁易主后 renew() 返回 False 且 lost=True"""
        redis = FakeRedis()
        async with distributed_lock(redis, LOCK_KEY, ttl=60) as lock:
            redis.strings[LOCK_KEY] = "thief-token"
            assert await lock.renew() is False
            assert lock.lost is True

    @pytest.mark.asyncio
    async def test_renew_redis_error_signals_lost(self):
        """续期遇 Redis 故障：保守按丢失处理（False + lost=True）"""
        redis = FakeRedis()

        async def boom(*args, **kwargs):
            raise RuntimeError("redis down")

        async with distributed_lock(redis, LOCK_KEY, ttl=60) as lock:
            redis.eval = boom
            assert await lock.renew() is False
            assert lock.lost is True

    @pytest.mark.asyncio
    async def test_auto_renewal_keeps_lock_alive(self):
        """renewal 后台续期：持续持有期间锁不丢、值仍归属自己"""
        redis = FakeRedis()
        async with distributed_lock(redis, LOCK_KEY, ttl=1, renewal=0.02) as lock:
            await asyncio.sleep(0.06)  # 足够跑 2 轮续期
            assert lock.lost is False
            assert redis.strings[LOCK_KEY] == lock.token
        assert lock._renewal_task is None  # release 已收尾，无悬挂任务

    @pytest.mark.asyncio
    async def test_auto_renewal_failure_marks_lost_and_task_exits(self):
        """后台续期失败：lost=True 感知 + 续期任务自行退出（异常安全）"""
        redis = FakeRedis()
        async with distributed_lock(redis, LOCK_KEY, ttl=1, renewal=0.02) as lock:
            redis.strings[LOCK_KEY] = "thief-token"
            await asyncio.sleep(0.06)
            assert lock.lost is True
            task = lock._renewal_task
        assert task is not None and task.done()  # 续期任务已退出
