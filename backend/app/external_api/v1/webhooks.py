"""外部 API - Webhook 接收端点

职责：
- 接收第三方系统的回调通知
- 验证签名（未来实现）
- 异步处理 webhook 事件
"""
from fastapi import APIRouter, Request, HTTPException, Header
from platform_core.infra.log_init import get_logger
import time

router = APIRouter()

@router.post("/spider/callback")
async def spider_callback(
    request: Request,
    x_webhook_secret: str = Header(None, alias="X-Webhook-Secret")
):
    """
    接收爬虫任务完成的回调
    
    第三方系统在爬虫完成后调用此接口通知结果
    """
    logger = get_logger("api")
    try:
        # 获取请求体
        body = await request.json()
        
        logger.info(
            f"收到爬虫回调: task_id={body.get('task_id')}, status={body.get('status')}"
        )
        
        # TODO: 验证签名
        # if not verify_signature(body, x_webhook_secret):
        #     raise HTTPException(status_code=401, detail="Invalid signature")
        
        # TODO: 异步处理回调（发送到消息队列）
        # await process_spider_callback(body)
        
        return {
            "status": "received",
            "timestamp": int(time.time()),
            "message": "Callback received successfully"
        }
        
    except Exception as e:
        logger.error(f"Webhook 处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/data/sync")
async def data_sync(
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key")
):
    """
    接收第三方数据同步请求
    
    需要 API Key 认证
    """
    logger = get_logger("api")
    try:
        # 验证 API Key
        if not validate_api_key(x_api_key):
            raise HTTPException(status_code=401, detail="Invalid API Key")
        
        body = await request.json()
        
        logger.info(
            f"收到数据同步请求: source={body.get('source')}"
        )
        
        # TODO: 处理数据同步
        # await process_data_sync(body)
        
        return {
            "status": "synced",
            "timestamp": int(time.time()),
            "records_processed": body.get("records", [])
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"数据同步失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def validate_api_key(api_key: str) -> bool:
    """验证 API Key（示例实现）"""
    # TODO: 从数据库或配置中验证
    valid_keys = ["test-api-key-123"]
    return api_key in valid_keys
