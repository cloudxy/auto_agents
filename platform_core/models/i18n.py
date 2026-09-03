"""国际化 i18n（DB 升级 2026-09 Phase C / DB-11）

字段级翻译粒度：locale + resource_type + resource_id + field_name；
前端按 locale 查翻译表，fallback 到资源原字段值。
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from platform_core.models.base import Base


class I18nLocale(Base):
    """语言注册表（code 全局唯一；is_default 至多一行，由 service 层保证）"""

    __tablename__ = "i18n_locales"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    code = Column(String(10), nullable=False, unique=True, comment="语言代码（zh-CN/en/ja）")
    name = Column(String(64), nullable=False, comment="显示名")
    is_default = Column(Boolean, nullable=False, default=False,
                         server_default="0", comment="默认语言")
    enabled = Column(Boolean, nullable=False, default=True,
                     server_default="1", comment="是否启用")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")


class I18nTranslation(Base):
    """翻译内容（字段级）"""

    __tablename__ = "i18n_translations"
    __table_args__ = (
        UniqueConstraint("locale_id", "resource_type", "resource_id", "field_name",
                         name="uq_i18n_translations_field"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    locale_id = Column(Integer, ForeignKey("i18n_locales.id"), nullable=False,
                       comment="语言")
    resource_type = Column(String(32), nullable=False, comment="资源类型（模型名小写下划线）")
    resource_id = Column(Integer, nullable=False, comment="资源 ID")
    field_name = Column(String(64), nullable=False, comment="字段名")
    translated_value = Column(Text, nullable=False, comment="翻译内容")
    updated_by = Column(String(64), nullable=True, comment="最后修改人")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
