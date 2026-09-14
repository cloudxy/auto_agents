"""LiteLLM Admin API 契约（无 ORM；禁直连 LiteLLM 库）。"""
from typing import Any, Optional

from pydantic import BaseModel, Field


class LitellmKeyCreate(BaseModel):
    key_alias: str = Field(..., min_length=1, max_length=128)
    max_budget: Optional[float] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LitellmKeyOut(BaseModel):
    key_alias: Optional[str] = None
    token: Optional[str] = None
    max_budget: Optional[float] = None
    spend: Optional[float] = None
    raw: dict[str, Any] = Field(default_factory=dict)
