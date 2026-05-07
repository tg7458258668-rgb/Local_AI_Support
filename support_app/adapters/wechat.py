from support_app.adapters.base import ChannelAdapter
from support_app.schemas import ChatRequest, ChatResponse


class WeChatAdapter(ChannelAdapter):
    channel = "wechat"

    def parse(self, payload: dict) -> ChatRequest:
        message = payload.get("Content") or payload.get("content") or payload.get("text") or ""
        user_id = payload.get("FromUserName") or payload.get("user_id")
        conversation_id = payload.get("MsgId") or payload.get("conversation_id")
        return ChatRequest(
            message=str(message),
            channel="wechat",
            user_id=str(user_id) if user_id else None,
            conversation_id=str(conversation_id) if conversation_id else None,
            metadata=payload,
        )

    def render(self, response: ChatResponse) -> dict:
        return {
            "msgtype": "text",
            "text": {"content": response.answer},
            "need_human": response.need_human,
            "route": response.route,
        }

