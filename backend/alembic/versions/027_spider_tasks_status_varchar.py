"""B3：spider_tasks.status 由 MySQL ENUM 改 VARCHAR(20) + 应用层枚举校验

Revision ID: 027
Revises: 026
Create Date: 2026-09-05

体检 F-08 处置：002a 基线将 status 建为 DDL 级 ENUM('pending','running',
'completed','failed')。加一个状态值（cancelled/timeout）就要 ALTER TABLE
改 ENUM 定义（锁表 DDL），与「status VARCHAR + 应用层枚举校验」的项目
数据契约相悖（dba 方法论第 2 步：不用 MySQL ENUM——改值要 DDL）。

expand 定性（安全方向）：ENUM→VARCHAR 是类型放宽，存量 4 个合法枚举值
在 VARCHAR(20) 下无损表达，无数据迁移需求，单步完成。
- 线上执行提示：MySQL 8 的 MODIFY COLUMN 为 ALGORITHM=COPY（重建表副本，
  写阻塞窗口 ≈ 表量级）；本机/当前环境 spider_tasks 为空表秒级完成。
  生产大表执行前评估量级与耗时，超预期走 gh-ost/pt-osc（同 SM-6 口径）。

应用层校验落点：
- 合法值与状态流转图：platform_core/models/spider_task.py 模型 docstring
  （本票同步对齐模型列类型 String(20)）
- 写入口枚举校验（schemas/API 层）：独立票——本票不动 services/API（B3 边界）

downgrade（收紧方向）带前置校验：VARCHAR 存续期若写入过 4 个合法值之外
的状态串，回滚 ENUM 会截断/报错。先检测非法值并显式 raise（impossible-down
显式化，与 025 同口径），杜绝 ALTER 中途失败留半回滚态。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "027"
down_revision: Union[str, Sequence[str], None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LEGAL_VALUES = ("pending", "running", "completed", "failed")
_ENUM_NAME = "spider_task_status"


def upgrade() -> None:
    op.alter_column(
        "spider_tasks", "status",
        existing_type=sa.Enum(*_LEGAL_VALUES, name=_ENUM_NAME),
        type_=sa.String(length=20),
        existing_nullable=True,
        comment="任务状态（合法值与流转图见模型 docstring：pending/running/completed/failed）",
    )


def downgrade() -> None:
    # 前置校验（migration data guard）：VARCHAR 存续期可能写入过枚举外的值
    illegal = op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM spider_tasks "
        "WHERE status NOT IN ('pending', 'running', 'completed', 'failed')"
    )).scalar()
    if illegal:
        raise RuntimeError(
            f"027 downgrade 前置校验失败：spider_tasks 存在 {illegal} 行 "
            "ENUM 四值之外的状态串，无法无损收紧回 ENUM。先处置（改判终态/"
            "归档）再回滚。检测 SQL：SELECT id, status FROM spider_tasks "
            "WHERE status NOT IN ('pending','running','completed','failed');"
        )
    op.alter_column(
        "spider_tasks", "status",
        existing_type=sa.String(length=20),
        type_=sa.Enum(*_LEGAL_VALUES, name=_ENUM_NAME),
        existing_nullable=True,
        existing_comment=None,
    )
