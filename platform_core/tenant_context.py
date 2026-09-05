"""租户上下文与行级隔离（SaaS S1-2，审计 10.2-A 双侧收口；T8 豁免清单外移）

作用域（ContextVar，请求中间件/后台组件显式声明）：
- tenant_scope(tenant_id)：租户态——写侧断言（flush 中 TenantMixin 新行必须归属本租户）
  + 读侧注入（ORM select/update/delete 自动加 tenant_id 条件）；
- platform_scope()：平台态（平台超管/后台组件）——跳过断言与过滤；
- 无上下文：legacy/测试路径——不过滤不断言（真实请求必经中间件，不落此分支；
  DB 层 NOT NULL（迁移 017）与 R13 越权套件兜底）。

业务表语义经注册机制由应用层注入（T8，B1 语义收口：基建不持有任何业务表名）：
- register_tenant_exempt_tables(*names)：平台级豁免表——tenant_scope 下
  Core UPDATE/DELETE 不注入 tenant_id 条件（含 tenant_id 列的平台级表必须登记，
  否则恒 NULL 行与注入条件全部失配；无 tenant_id 列的表登记属防御性声明，
  防未来加列后语义静默漂移）；
- register_platform_shared_read_tables(*names)：读注入保留平台公共行
  （tenant_id IS NULL 可见），写侧仍注入本租户条件（平台公共行仅平台态可写）。

豁免/共享读清单的唯一事实源在应用组装层（backend/app/tenant_isolation.py），
启动时显式注册；scripts/check-arch.sh R13 从该事实源做同步校验（防双写漂移）。
"""
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional

from sqlalchemy import event, or_
from sqlalchemy.orm import Session

from platform_core.logger import get_logger
from platform_core.models.mixins import TenantMixin

logger = get_logger("tenant")

_TENANT_ID: ContextVar[Optional[int]] = ContextVar("tenant_id", default=None)
_MODE: ContextVar[str] = ContextVar("tenant_mode", default="none")  # none | tenant | platform

# ---------------- 业务表语义注册表（T8：应用组装点写入，基建零业务表名） ----------------

# 平台级豁免表（tenant_scope 下 Core UPDATE/DELETE 跳过注入）
_TENANT_EXEMPT: "set[str]" = set()

# 读注入保留平台公共行（tenant_id IS NULL 可见）的表
_PLATFORM_SHARED_READ: "set[str]" = set()


def register_tenant_exempt_tables(*names: str) -> None:
    """登记平台级豁免表（幂等；唯一事实源：backend/app/tenant_isolation.py）"""
    new = sorted({n for n in names if n and n not in _TENANT_EXEMPT})
    if new:
        _TENANT_EXEMPT.update(new)
        logger.info(f"平台级豁免表登记 | +{new}")


def tenant_exempt_tables() -> frozenset:
    """当前已登记的豁免表（快照；测试/R13 同步校验用）"""
    return frozenset(_TENANT_EXEMPT)


def register_platform_shared_read_tables(*names: str) -> None:
    """登记平台共享读表（幂等；tenant_scope 读注入保留 tenant_id IS NULL 行）"""
    new = sorted({n for n in names if n and n not in _PLATFORM_SHARED_READ})
    if new:
        _PLATFORM_SHARED_READ.update(new)
        logger.info(f"平台共享读表登记 | +{new}")


def platform_shared_read_tables() -> frozenset:
    """当前已登记的平台共享读表（快照；测试/R13 同步校验用）"""
    return frozenset(_PLATFORM_SHARED_READ)


@contextmanager
def tenant_scope(tenant_id: int):
    """租户态作用域（请求中间件按登录身份进入）"""
    token_t = _TENANT_ID.set(int(tenant_id))
    token_m = _MODE.set("tenant")
    try:
        yield
    finally:
        _TENANT_ID.reset(token_t)
        _MODE.reset(token_m)


@contextmanager
def platform_scope():
    """平台态作用域（平台超管请求/后台常驻组件/运维路径）"""
    token_t = _TENANT_ID.set(None)
    token_m = _MODE.set("platform")
    try:
        yield
    finally:
        _TENANT_ID.reset(token_t)
        _MODE.reset(token_m)


def current_tenant_id() -> Optional[int]:
    """当前生效租户（仅租户态返回值；平台态/无上下文返回 None）"""
    return _TENANT_ID.get() if _MODE.get() == "tenant" else None


def is_platform_mode() -> bool:
    return _MODE.get() == "platform"


def _is_tenant_model(obj) -> bool:
    return isinstance(obj, TenantMixin)


# ---------------- 事件钩子（安装一次） ----------------

_installed = False


def install_tenant_isolation() -> None:
    """注册写侧断言与读侧注入（幂等；platform_core 导入链自动安装）"""
    global _installed
    if _installed:
        return
    _installed = True

    @event.listens_for(Session, "before_flush")
    def _assert_tenant_ownership(session, flush_context, instances):
        tenant_id = current_tenant_id()
        if tenant_id is None:
            return  # 平台态/无上下文：不适用断言
        for obj in session.new:
            if not _is_tenant_model(obj):
                continue
            if getattr(obj, "tenant_id", None) != tenant_id:
                raise ValueError(
                    f"租户写入断言失败：{type(obj).__name__} 归属 "
                    f"{getattr(obj, 'tenant_id', None)} 与上下文租户 {tenant_id} 不符"
                )

    @event.listens_for(Session, "do_orm_execute")
    def _inject_tenant_filter(execute_state):
        from sqlalchemy.sql.dml import Delete, Update

        tenant_id = current_tenant_id()
        if tenant_id is None or not execute_state.is_orm_statement:
            return
        stmt = execute_state.statement

        if isinstance(stmt, Update) or isinstance(stmt, Delete):
            table = stmt.table
            if table.name in _TENANT_EXEMPT:
                return
            if "tenant_id" not in table.c:
                return
            execute_state.statement = stmt.where(table.c.tenant_id == tenant_id)
            return

        # SELECT：with_loader_criteria 官方租户配方（自动覆盖 join/别名/子查询实体；
        # 豁免表恒真跳过；平台共享表保留 NULL 行可见性）
        from sqlalchemy.orm import with_loader_criteria

        # lambda-SQL 约束：闭包非 SQL 对象参与运算会被绑成参数（集合成员判断
        # → contains 报错），故豁免分支不存在——豁免表本就不继承 TenantMixin
        # （with_loader_criteria 不匹配）；平台共享表用纯字符串比较分支
        # （cls 非闭包，运行时求值）。
        def _criteria(cls):
            col = cls.tenant_id
            if any(getattr(cls, "__tablename__", "") == name
                   for name in _PLATFORM_SHARED_READ):
                return or_(col == tenant_id, col.is_(None))
            return col == tenant_id

        execute_state.statement = stmt.options(
            with_loader_criteria(TenantMixin, _criteria, include_aliases=True)
        )


install_tenant_isolation()
