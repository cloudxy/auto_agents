"""任务模板（C1）- 模板增删改查 + 从模板创建并运行任务

自 spider_registry_service 拆出（规模约定），SpiderRegistryService 经
SpiderTemplateMixin 组合（公开签名、返回值与异常不变）；依赖宿主的 session。
"""
from backend.repositories.task_template_repository import TaskTemplateRepository
from backend.services.spider_common import require_enqueue_tenant
from platform_core.exceptions import BusinessException, NotFoundException
from platform_core.logger import get_logger
from platform_core.schemas.spider import SpiderTaskResponse, TaskTemplateResponse

logger = get_logger("api")


class SpiderTemplateMixin:
    """SpiderRegistryService 的任务模板部分"""

    async def list_templates(self) -> list[TaskTemplateResponse]:
        """获取所有任务模板"""
        logger.debug("获取任务模板列表")
        repo = TaskTemplateRepository(self.session)
        items = await repo.list_all()
        return [TaskTemplateResponse.model_validate(item) for item in items]

    async def create_template(
        self, payload: dict, created_by: str | None = None, tenant_id: int | None = None,
    ) -> TaskTemplateResponse:
        """创建任务模板（名称唯一性校验）"""
        logger.info(f"创建任务模板: name={payload.get('name')}")
        owner_id = require_enqueue_tenant(tenant_id)
        repo = TaskTemplateRepository(self.session)
        existing = await repo.get_by_name(payload["name"])
        if existing:
            raise BusinessException(f"模板名称 '{payload['name']}' 已存在")
        data = {k: v for k, v in payload.items() if k != "tenant_id"}
        item = await repo.create(**data, created_by=created_by, tenant_id=owner_id)
        await self.session.commit()
        await self.session.refresh(item)
        return TaskTemplateResponse.model_validate(item)

    async def update_template(self, template_id: int, payload: dict) -> TaskTemplateResponse:
        """更新任务模板"""
        logger.info(f"更新任务模板: id={template_id}")
        repo = TaskTemplateRepository(self.session)
        item = await repo.get_by_id(template_id)
        if item is None:
            raise NotFoundException("任务模板")
        if "name" in payload and payload["name"] != item.name:
            existing = await repo.get_by_name(payload["name"])
            if existing:
                raise BusinessException(f"模板名称 '{payload['name']}' 已存在")
        updated = await repo.update(template_id, **payload)
        await self.session.commit()
        await self.session.refresh(updated)
        return TaskTemplateResponse.model_validate(updated)

    async def delete_template(self, template_id: int) -> dict:
        """删除任务模板"""
        logger.info(f"删除任务模板: id={template_id}")
        repo = TaskTemplateRepository(self.session)
        item = await repo.get_by_id(template_id)
        if item is None:
            raise NotFoundException("任务模板")
        await repo.delete(template_id)
        await self.session.commit()
        return {"id": template_id, "deleted": True}

    async def create_task_from_template(
        self, template_id: int, tenant_id: int | None = None,
    ) -> SpiderTaskResponse:
        """从模板创建并运行任务"""
        logger.info(f"从模板创建任务: template_id={template_id}")
        owner_id = require_enqueue_tenant(tenant_id)
        repo = TaskTemplateRepository(self.session)
        template = await repo.get_by_id(template_id)
        if template is None:
            raise NotFoundException("任务模板")
        tmpl_tid = getattr(template, "tenant_id", None)
        try:
            tmpl_owner = int(tmpl_tid) if tmpl_tid is not None else None
        except (TypeError, ValueError):
            tmpl_owner = None
        if tmpl_owner != owner_id:
            raise NotFoundException("任务模板")
        # 局部构造（无状态）：避免 registry → task 顶层互相依赖
        from backend.services.spider_task_service import SpiderTaskService
        return await SpiderTaskService(self.session).enqueue(
            spider_name=template.spider_name,
            params=template.params,
            priority=template.priority or "normal",
            tenant_id=owner_id,
        )
