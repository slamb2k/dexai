"""
Chat API Routes

Provides endpoints for chat functionality:
- POST /api/chat/message - Send message and get response
- GET /api/chat/history - Get conversation history
- GET /api/chat/conversations - List conversations
- DELETE /api/chat/conversations/{id} - Delete a conversation
- WebSocket /ws/chat - Real-time streaming chat
"""

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from pydantic import BaseModel, Field

from tools.dashboard.backend.services.chat_service import ChatService

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================


class ChatMessageRequest(BaseModel):
    """Request model for sending a chat message."""

    message: str = Field(..., min_length=1, max_length=10000)
    conversation_id: Optional[str] = None


class ChatMessageResponse(BaseModel):
    """Response model for chat message."""

    conversation_id: str
    message_id: str
    content: str
    role: str = "assistant"
    model: Optional[str] = None
    complexity: Optional[str] = None
    cost_usd: Optional[float] = None
    tool_uses: Optional[list] = None
    error: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class ChatHistoryMessage(BaseModel):
    """A single message in chat history."""

    id: str
    role: str
    content: str
    model: Optional[str] = None
    complexity: Optional[str] = None
    cost_usd: Optional[float] = None
    tool_uses: Optional[list] = None
    created_at: str


class ChatHistoryResponse(BaseModel):
    """Response model for chat history."""

    conversation_id: str
    messages: list[ChatHistoryMessage]
    total: int


class ConversationSummary(BaseModel):
    """Summary of a conversation."""

    id: str
    title: Optional[str] = None
    last_message: Optional[str] = None
    created_at: str
    updated_at: str


class ConversationsResponse(BaseModel):
    """Response model for listing conversations."""

    conversations: list[ConversationSummary]
    total: int


# =============================================================================
# REST Endpoints
# =============================================================================


@router.post("/message", response_model=ChatMessageResponse)
async def send_chat_message(request: ChatMessageRequest):
    """
    Send a chat message and receive a response.

    This endpoint sends the user's message to DexAI and returns
    the assistant's response. The conversation is automatically
    persisted in the database.
    """
    # TODO: Get user_id from authenticated session
    user_id = "anonymous"

    service = ChatService(user_id=user_id)

    result = await service.send_message(
        message=request.message,
        conversation_id=request.conversation_id,
    )

    return ChatMessageResponse(
        conversation_id=result["conversation_id"],
        message_id=result["message_id"],
        content=result["content"],
        role=result["role"],
        model=result.get("model"),
        complexity=result.get("complexity"),
        cost_usd=result.get("cost_usd"),
        tool_uses=result.get("tool_uses"),
        error=result.get("error"),
    )


@router.get("/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    conversation_id: str = Query(..., description="Conversation ID to get history for"),
    limit: int = Query(50, ge=1, le=200, description="Maximum messages to return"),
):
    """
    Get the message history for a conversation.

    Returns messages in chronological order (oldest first).
    """
    user_id = "anonymous"

    service = ChatService(user_id=user_id)
    service._current_conversation_id = conversation_id

    messages = service.get_conversation_history(
        conversation_id=conversation_id,
        limit=limit,
    )

    return ChatHistoryResponse(
        conversation_id=conversation_id,
        messages=[
            ChatHistoryMessage(
                id=msg["id"],
                role=msg["role"],
                content=msg["content"],
                model=msg.get("model"),
                complexity=msg.get("complexity"),
                cost_usd=msg.get("cost_usd"),
                tool_uses=msg.get("tool_uses"),
                created_at=msg["created_at"],
            )
            for msg in messages
        ],
        total=len(messages),
    )


@router.get("/conversations", response_model=ConversationsResponse)
async def list_conversations(
    limit: int = Query(20, ge=1, le=100, description="Maximum conversations to return"),
):
    """
    List all conversations for the current user.

    Returns conversations sorted by most recently updated first.
    """
    user_id = "anonymous"

    service = ChatService(user_id=user_id)
    conversations = service.get_conversations(limit=limit)

    return ConversationsResponse(
        conversations=[
            ConversationSummary(
                id=conv["id"],
                title=conv.get("title"),
                last_message=conv.get("last_message"),
                created_at=conv["created_at"],
                updated_at=conv["updated_at"],
            )
            for conv in conversations
        ],
        total=len(conversations),
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """
    Delete a conversation and all its messages.
    """
    user_id = "anonymous"

    service = ChatService(user_id=user_id)
    deleted = service.delete_conversation(conversation_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {"success": True, "conversation_id": conversation_id}


@router.post("/conversations")
async def create_conversation():
    """
    Create a new empty conversation.

    Returns the new conversation ID.
    """
    user_id = "anonymous"

    service = ChatService(user_id=user_id)
    conversation_id = service.get_or_create_conversation()

    return {
        "success": True,
        "conversation_id": conversation_id,
        "created_at": datetime.now().isoformat(),
    }


# =============================================================================
# WebSocket Streaming Endpoint
# =============================================================================


@router.websocket("/stream")
async def websocket_chat_stream(websocket: WebSocket):
    """
    WebSocket endpoint for streaming chat responses.

    Protocol:
    1. Client connects
    2. Client sends JSON: {"message": "...", "conversation_id": "..." (optional)}
    3. Server streams responses as JSON: {"type": "chunk", "content": "..."} or {"type": "done", ...}
    4. Client can send more messages or close connection

    Error handling:
    - Invalid JSON: {"type": "error", "error": "Invalid JSON"}
    - Missing message: {"type": "error", "error": "No message provided"}
    """
    await websocket.accept()

    user_id = "anonymous"
    service = ChatService(user_id=user_id)

    try:
        while True:
            # Wait for client message
            data = await websocket.receive_text()

            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "error": "Invalid JSON"})
                continue

            message = payload.get("message", "").strip()
            conversation_id = payload.get("conversation_id")

            if not message:
                await websocket.send_json({"type": "error", "error": "No message provided"})
                continue

            # Stream the response
            try:
                async for chunk in service.stream_message(
                    message=message,
                    conversation_id=conversation_id,
                ):
                    await websocket.send_json(chunk)
            except Exception as e:
                logger.error(f"Error streaming response: {e}")
                await websocket.send_json({"type": "error", "error": str(e)})

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close(code=1011, reason=str(e))
        except Exception:
            pass
