"""访客可读值班联系（无鉴权）。空则前端隐藏 CTA。"""
from fastapi import APIRouter

from backend.app.responses import ok
from backend.services.ops_contact_service import public_duty_contact

router = APIRouter()


@router.get("/ops-contact")
async def get_ops_contact():
    return ok(data={"duty_contact": public_duty_contact()})
