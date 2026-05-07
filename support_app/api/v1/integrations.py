from fastapi import APIRouter, Depends, HTTPException

from support_app.adapters import FeishuAdapter, WeChatAdapter
from support_app.dependencies import get_chat_service
from support_app.schemas import IntegrationWebhookRequest, IntegrationWebhookResponse
from support_app.services.chat_service import ChatService

router = APIRouter(prefix="/integrations", tags=["integrations"])

ADAPTERS = {
    "wechat": WeChatAdapter(),
    "feishu": FeishuAdapter(),
}


@router.post("/webhook", response_model=IntegrationWebhookResponse)
def webhook(req: IntegrationWebhookRequest, service: ChatService = Depends(get_chat_service)):
    adapter = ADAPTERS.get(req.channel)
    if not adapter:
        raise HTTPException(status_code=400, detail=f"Unsupported channel: {req.channel}")

    chat_request = adapter.parse(req.payload)
    chat_response = service.answer(chat_request)
    rendered = adapter.render(chat_response)

    return IntegrationWebhookResponse(
        channel=req.channel,
        reply_text=chat_response.answer,
        rendered=rendered,
        raw_response=chat_response,
    )
