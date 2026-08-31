"""共享测试桩设施 - 高频桩的唯一定义处

背景（任务 #31 测试体系重组）：
- _fake_settings 曾在 test_llm_provider / test_newapi_api / test_newapi_services /
  test_ai_planner 四处重复定义；FakeRedis 在 test_distributed_lock /
  test_newapi_services 两处重复定义。本模块为其唯一权威版本。

选型说明：
- 命名为 stubs.py：pytest 默认 python_files 只收集 test_*.py，本文件不会被收集为
  测试模块；backend/tests 无 __init__.py，pytest prepend 导入模式自动将本目录
  加入 sys.path，各测试文件直接 `from stubs import ...`。
- 禁止命名为 utils.py：scrapy 项目自身存在顶层 `utils` 包
  （scrapy/utils，爬虫代码 `from utils.selector_engine import ...`），
  同名会令 sys.modules['utils'] 被绑定为非包模块，爬虫导入冲突。
- conftest.py 另有显式 sys.path 插入作为双保险。

约定：
- 各测试文件以别名导入以最小化改动：`from stubs import fake_settings as _fake_settings`。
- FakeRedis 是各文件现用桩的语义并集（strings + hashes + Lua eval token 比对），
  签名与原实现兼容；用例可直接读写 .strings / .hashes 内部字典。
- 领域特化桩（如队列故障注入 Redis）不收录，保留在各自测试文件内。
"""
from unittest.mock import AsyncMock, MagicMock


def fake_settings(**kv) -> MagicMock:
    """settings.get(key, default) 桩（并集：附带 REDIS.DEFAULT.URL 属性链）

    用法：monkeypatch/patch 目标 service 命名空间的 settings：
        patch("backend.services.xxx_service.settings", fake_settings(KEY="v"))
    """
    m = MagicMock()

    def _get(key, default=None):
        return kv.get(key, default)

    m.get.side_effect = _get
    m.REDIS.DEFAULT.URL = "redis-fake-url"
    return m


class FakeRedis:
    """内存 Redis 桩（并集语义）：

    - strings：SET NX / GET / DEL / Lua eval（token 比对 DEL/EXPIRE）
    - hashes：HGETALL / HGET / HSET
    - 用例可直接读写 .strings / .hashes 做断言与预置
    """

    def __init__(self):
        self.strings: dict = {}
        self.hashes: dict = {}
        self.sets: dict = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.strings:
            return False
        self.strings[key] = value
        return True

    async def get(self, key):
        return self.strings.get(key)

    async def delete(self, *keys):
        removed = False
        for key in keys:
            if self.strings.pop(key, None) is not None:
                removed = True
            if self.hashes.pop(key, None) is not None:
                removed = True
        return removed

    async def expire(self, key, ttl):
        return key in self.strings or key in self.hashes  # Fake 无真实 TTL

    async def scan_iter(self, match=None):
        """异步生成器：遍历全部键（strings + hashes + sets）；match 走 fnmatch 通配"""
        import fnmatch

        all_keys = list(self.strings) + list(self.hashes) + list(self.sets)
        for key in sorted(all_keys):
            if match is None or fnmatch.fnmatch(key, match):
                yield key

    async def rename(self, key, new_key):
        """跨类型原子改名（strings/hashes 各自搬移；不存在时模拟 ResponseError）"""
        if key in self.strings:
            self.strings[new_key] = self.strings.pop(key)
            return True
        if key in self.hashes:
            self.hashes[new_key] = self.hashes.pop(key)
            return True
        raise KeyError(f"no such key: {key}")

    async def eval(self, script, numkeys, *args):
        """模拟共享锁设施的两个 Lua 脚本（token 比对 DEL/EXPIRE）"""
        key, token = args[0], args[1]
        if self.strings.get(key) != token:
            return 0
        if "EXPIRE" in script:
            return 1  # Fake 无真实 TTL，仅返回成功
        self.strings.pop(key, None)
        return 1

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    async def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value

    async def hincrby(self, key, field, amount=1):
        bucket = self.hashes.setdefault(key, {})
        try:
            current = int(bucket.get(field, 0))
        except (TypeError, ValueError):
            current = 0
        bucket[field] = str(current + int(amount))
        return current + int(amount)

    async def sadd(self, key, *members):
        bucket = self.sets.setdefault(key, set())
        added = [m for m in members if m not in bucket]
        bucket.update(members)
        return len(added)

    async def sismember(self, key, member):
        return member in self.sets.get(key, set())

    async def aclose(self):
        pass


def fake_async_session() -> MagicMock:
    """异步 SQLAlchemy session 桩（commit/flush/refresh/rollback/execute 为 AsyncMock）"""
    s = MagicMock()
    s.commit = AsyncMock()
    s.flush = AsyncMock()
    s.refresh = AsyncMock()
    s.rollback = AsyncMock()
    s.execute = AsyncMock()
    return s
