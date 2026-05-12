from fastapi import APIRouter
from app.models.schemas import ChatRequest, ChatResponse
from app import agents

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    return await agents.orchestrator.run(request)
