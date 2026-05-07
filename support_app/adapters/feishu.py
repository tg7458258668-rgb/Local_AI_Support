from support_app.adapters.base import ChannelAdapter
from support_app.schemas import ChatRequest, ChatResponse


class FeishuAdapter(ChannelAdapter):
    channel = "feishu"

    def parse(self, payload: dict) -> ChatRequest:
        event = payload.get("event", {}) if isinstance(payload.get("event"), dict) else {}
        message = event.get("message", {}) if isinstance(event.get("message"), dict) else {}
        sender = event.get("sender", {}) if isinstance(event.get("sender"), dict) else {}

        text = payload.get("text") or message.get("content") or payload.get("content") or ""
        user_id = payload.get("user_id") or sender.get("sender_id", {}).get("open_id")
        conversation_id = payload.get("conversation_id") or message.get("chat_id")

        return ChatRequest(
            message=str(text),
            channel="feishu",
            user_id=str(user_id) if user_id else None,
            conversation_id=str(conversation_id) if conversation_id else None,
            metadata=payload,
        )

    def render(self, response: ChatResponse) -> dict:
        return {
            "msg_type": "text",
            "content": {"text": response.answer},
            "need_human": response.need_human,
            "route": response.route,
        }

