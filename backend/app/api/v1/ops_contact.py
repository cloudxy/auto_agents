"""访客可读的联系方式（无鉴权）：值班联系 + 对外联系邮箱与响应时效（D25）。空则前端隐藏 CTA。"""
from fastapi import APIRouter

from backend.app.responses import ok
from backend.services.ops_contact_service import public_contact

router = APIRouter()


@router.get("/ops-contact")
async def get_ops_contact():
    return ok(data=public_contact())
