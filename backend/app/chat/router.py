import json
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.chat.models import (
    ConversationListResponse,
    ConversationResponse,
    CreateConversationRequest,
    MessageResponse,
    SendMessageRequest,
    UpdateConversationRequest,
)
from app.chat.service import (
    create_conversation,
    delete_conversation,
    get_conversation,
    get_conversation_messages,
    get_user_conversations,
    stream_chat_response,
    update_conversation,
)
from app.core.dependencies import (
    AuthContext,
    require_active_subscription,
    require_token_quota,
)
from app.postgres import get_db_session

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/chat",
    tags=["chat"],
)


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation_endpoint(
    request: CreateConversationRequest,
    context: AuthContext = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db_session),
):
    """Create a new conversation"""
    conversation = await create_conversation(
        db=db,
        user_id=context.user.id,
        organization_id=context.organization.id,
        title=request.title,
    )
    return ConversationResponse.model_validate(conversation)


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    context: AuthContext = Depends(require_active_subscription),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
):
    """Get all conversations for current user"""
    conversations = await get_user_conversations(
        db=db, user_id=context.user.id, limit=limit, offset=offset
    )
    return ConversationListResponse(
        conversations=[ConversationResponse.model_validate(c) for c in conversations],
        total=len(conversations),
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation_endpoint(
    conversation_id: int,
    request: UpdateConversationRequest,
    context: AuthContext = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db_session),
):
    """Update a conversation's title"""
    conversation = await update_conversation(
        db=db,
        conversation_id=conversation_id,
        user_id=context.user.id,
        title=request.title,
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationResponse.model_validate(conversation)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation_endpoint(
    conversation_id: int,
    context: AuthContext = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db_session),
):
    """Delete a conversation"""
    success = await delete_conversation(
        db=db, conversation_id=conversation_id, user_id=context.user.id
    )
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.get("/conversations/{conversation_id}/messages", response_model=List[MessageResponse])
async def get_conversation_messages_endpoint(
    conversation_id: int,
    context: AuthContext = Depends(require_active_subscription),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db_session),
):
    """Get messages for a conversation"""
    # Verify ownership
    conversation = await get_conversation(db, conversation_id, context.user.id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = await get_conversation_messages(db=db, conversation_id=conversation_id, limit=limit)
    return [MessageResponse.model_validate(m) for m in messages]


@router.post(
    "/conversations/{conversation_id}/messages/stream",
    response_class=StreamingResponse,
)
async def send_message(
    conversation_id: int,
    request: SendMessageRequest,
    context: AuthContext = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(require_token_quota),
):
    """Send a message and stream AI response via SSE"""

    async def event_stream():
        try:
            async for chunk in stream_chat_response(
                db=db,
                conversation_id=conversation_id,
                user_message=request.message,
                user_id=context.user.id,
                organization_id=context.organization.id,
            ):
                yield chunk
        except Exception as e:
            logger.exception(f"Error in send_message endpoint: {e}")
            yield f"data: {json.dumps({'type': 'error', 'error': 'Internal server error'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
