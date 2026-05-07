from fastapi import APIRouter, Depends

from support_app.dependencies import get_chat_service
from support_app.schemas import ChatRequest, ChatResponse
from support_app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest, service: ChatService = Depends(get_chat_service)):
    return service.answer(req)


@router.post("/ask", response_model=ChatResponse)
def ask(req: ChatRequest, service: ChatService = Depends(get_chat_service)):
    return service.answer(req)

