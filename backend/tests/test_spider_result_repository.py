"""SpiderResultRepository 单元测试 - keyword 深翻页护栏 + 导出 id 游标分批

约定：不连接真实 MySQL/Redis，session 用 AsyncMock 桩；
SQL 断言基于 literal_binds 编译后的语句文本。
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.repositories.spider_result_repository import (
    EXPORT_BATCH_SIZE,
    KEYWORD_SEARCH_MAX_ROWS,
    SpiderResultRepository,
)


def _repo() -> tuple[SpiderResultRepository, MagicMock]:
    """构造 repository 桩（session.execute 用 AsyncMock）"""
    session = MagicMock()
    session.execute = AsyncMock()
    return SpiderResultRepository(session=session), session


def _count_result(total: int) -> MagicMock:
    r = MagicMock()
    r.scalar.return_value = total
    return r


def _rows_result(rows: list) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = rows
    return r


def _compiled(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


class TestKeywordSearchGuard:
    """keyword LIKE 检索深翻页护栏（KEYWORD_SEARCH_MAX_ROWS）"""

    @pytest.mark.asyncio
    async def test_first_page_limit_is_min_of_page_size_and_cap(self):
        repo, session = _repo()
        session.execute.side_effect = [_count_result(0), _rows_result([])]

        items, total = await repo.query_by_spider(keyword="kw", page=1, page_size=50)

        assert items == [] and total == 0
        sql = _compiled(session.execute.call_args_list[1].args[0])
        assert "LIMIT 50" in sql  # min(page_size, 200)

    @pytest.mark.asyncio
    async def test_page_size_over_cap_is_capped(self):
        repo, session = _repo()
        session.execute.side_effect = [_count_result(0), _rows_result([])]

        await repo.query_by_spider(keyword="kw", page=1, page_size=500)

        sql = _compiled(session.execute.call_args_list[1].args[0])
        assert f"LIMIT {KEYWORD_SEARCH_MAX_ROWS}" in sql

    @pytest.mark.asyncio
    async def test_boundary_window_exactly_at_cap(self):
        """page=2 & page_size=100 -> 窗口 [100, 200) 恰好贴上硬上限，仍返回数据"""
        repo, session = _repo()
        session.execute.side_effect = [_count_result(999), _rows_result([])]

        items, total = await repo.query_by_spider(keyword="kw", page=2, page_size=100)

        assert items == [] and total == 999
        sql = _compiled(session.execute.call_args_list[1].args[0])
        assert "OFFSET 100" in sql
        assert "LIMIT 100" in sql

    @pytest.mark.asyncio
    async def test_deep_page_beyond_cap_skips_data_query(self):
        """page=3 & page_size=100 -> 窗口越过 200 上限：不再执行 LIKE 分页查询"""
        repo, session = _repo()
        session.execute.side_effect = [_count_result(999)]

        items, total = await repo.query_by_spider(keyword="kw", page=3, page_size=100)

        assert items == [] and total == 999  # total 仍为真实计数
        assert session.execute.await_count == 1  # 仅 count，无数据查询

    @pytest.mark.asyncio
    async def test_without_keyword_pagination_unchanged(self):
        """无 keyword 时不启用护栏（深翻页语义保持原样）"""
        repo, session = _repo()
        session.execute.side_effect = [_count_result(0), _rows_result([])]

        await repo.query_by_spider(page=50, page_size=100)

        sql = _compiled(session.execute.call_args_list[1].args[0])
        assert "OFFSET 4900" in sql
        assert "LIMIT 100" in sql


class TestIterByTask:
    """导出 id 游标分批（iter_by_task）"""

    @pytest.mark.asyncio
    async def test_yields_all_rows_across_batches_with_cursor(self):
        repo, session = _repo()
        batch1 = [SimpleNamespace(id=i) for i in (1, 2, 3)]
        batch2 = [SimpleNamespace(id=i) for i in (4, 5)]
        session.execute.side_effect = [
            _rows_result(batch1),
            _rows_result(batch2),
            _rows_result([]),
        ]

        collected = [r async for r in repo.iter_by_task(7, batch_size=3)]

        assert [r.id for r in collected] == [1, 2, 3, 4, 5]
        assert session.execute.await_count == 3
        # 游标推进：第 2/3 批以 id > 上一批末尾 id 为界
        sql2 = _compiled(session.execute.call_args_list[1].args[0])
        sql3 = _compiled(session.execute.call_args_list[2].args[0])
        assert "spider_results.task_id = 7" in sql2
        assert "spider_results.id > 3" in sql2
        assert "spider_results.id > 5" in sql3

    @pytest.mark.asyncio
    async def test_empty_task_runs_single_query(self):
        repo, session = _repo()
        session.execute.side_effect = [_rows_result([])]

        collected = [r async for r in repo.iter_by_task(7)]

        assert collected == []
        assert session.execute.await_count == 1
        sql = _compiled(session.execute.call_args_list[0].args[0])
        assert f"LIMIT {EXPORT_BATCH_SIZE}" in sql

    @pytest.mark.asyncio
    async def test_batch_order_is_id_ascending(self):
        repo, session = _repo()
        session.execute.side_effect = [
            _rows_result([SimpleNamespace(id=1)]),
            _rows_result([]),
        ]

        _ = [r async for r in repo.iter_by_task(7)]

        sql = _compiled(session.execute.call_args_list[0].args[0])
        assert "ORDER BY spider_results.id ASC" in sql
