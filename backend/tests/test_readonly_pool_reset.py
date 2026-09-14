"""H1 只读会话不得把 MySQL SESSION READ ONLY 留在连接池。

试采 INSERT spider_tasks 报 1792：Cannot execute statement in a READ ONLY
transaction。/admin/stats 走 get_async_readonly_db，与写路径共用 async 池。
"""
import pytest
from sqlalchemy.sql.elements import TextClause

from platform_core.db import get_async_readonly_db


def _sql(clause) -> str:
    if isinstance(clause, TextClause):
        return clause.text
    return str(clause)


class _FakeSession:
    def __init__(self, dialect: str) -> None:
        self.bind = type("B", (), {"dialect": type("D", (), {"name": dialect})()})()
        self.executed: list[str] = []
        self.invalidated = False

    async def execute(self, clause, *args, **kwargs):
        self.executed.append(_sql(clause))

    async def rollback(self):
        self.executed.append("rollback")

    async def invalidate(self):
        self.invalidated = True


@pytest.mark.asyncio
async def test_readonly_mysql_session_resets_read_write_on_exit(monkeypatch):
    sess = _FakeSession("mysql")

    class _Mgr:
        async def get_async_session(self, key="DEFAULT"):
            yield sess

    monkeypatch.setattr("platform_core.db.get_manager", lambda: _Mgr())
    agen = get_async_readonly_db()
    assert await anext(agen) is sess
    await agen.aclose()
    joined = " ".join(sess.executed)
    assert "SET SESSION TRANSACTION READ ONLY" in joined
    assert "SET SESSION TRANSACTION READ WRITE" in joined
    assert joined.index("READ ONLY") < joined.index("READ WRITE")
    assert not sess.invalidated


@pytest.mark.asyncio
async def test_readonly_sqlite_skips_session_txn_mode(monkeypatch):
    sess = _FakeSession("sqlite")

    class _Mgr:
        async def get_async_session(self, key="DEFAULT"):
            yield sess

    monkeypatch.setattr("platform_core.db.get_manager", lambda: _Mgr())
    agen = get_async_readonly_db()
    await anext(agen)
    await agen.aclose()
    assert sess.executed == []
