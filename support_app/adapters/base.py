from abc import ABC, abstractmethod

from support_app.schemas import ChatRequest, ChatResponse


class ChannelAdapter(ABC):
    channel: str

    @abstractmethod
    def parse(self, payload: dict) -> ChatRequest:
        """Convert a channel webhook payload into the internal chat request."""

    @abstractmethod
    def render(self, response: ChatResponse) -> dict:
        """Convert an internal chat response into channel-specific reply payload."""

