"""AI chat API endpoints.

Provides:
- POST /ai/chat (SSE streaming)
- GET /ai/conversations (list)
- POST /ai/conversations (create)
- GET /ai/conversations/{id} (detail)
- PATCH /ai/conversations/{id} (update title)
- DELETE /ai/conversations/{id} (delete)
- GET /ai/conversations/{id}/messages (list messages)
"""
import json
from typing import AsyncGenerator
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_current_user
from app.models.user import User
from app.services.ai_service import AIService
from app.schemas.ai_conversation import (
    ChatRequest,
    ChatResponse,
    AIConversationCreate,
    AIConversationResponse,
    AIConversationDetail,
    AIConversationUpdate,
    AIMessageResponse,
    ConversationListResponse,
)
from app.utils.errors import NotFoundError

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/ai", tags=["AI"])


# ============================================================================
# Chat endpoint (SSE streaming)
# ============================================================================

@router.post("/chat", response_class=StreamingResponse)
async def chat_stream(
    request: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Chat with AI assistant (SSE streaming).
    
    Event types:
    - token: {"token": "..."}
    - citation: {"record_id": "...", "dataset_id": "...", "text": "..."}
    - tool_call: {"tool_name": "...", "arguments": {...}}
    - done: {"conversation_id": "...", "message_id": "...", "tokens_in": N, "tokens_out": N}
    - denied: {"reason": "..."}
    
    Example:
        ```
        POST /api/v1/ai/chat
        {
            "message": "2024年4月销售额是多少？",
            "conversation_id": "abc123..." // optional
        }
        ```
    """
    
    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events."""
        try:
            service = AIService(db)
            
            # Process chat (non-streaming for Phase 8 v1)
            conversation, user_msg, assistant_msg = await service.chat(
                user_input=request.message,
                user=user,
                conversation_id=request.conversation_id,
            )
            
            await db.commit()
            
            # Stream answer as tokens (simulate streaming)
            answer = assistant_msg.content
            
            # Send tokens (split by character for now, can improve to word-level)
            for char in answer:
                yield f"event: token\ndata: {json.dumps({'token': char}, ensure_ascii=False)}\n\n"
            
            # Send citations
            for citation in assistant_msg.citations:
                citation_data = {
                    "record_id": citation.get("record_id"),
                    "dataset_id": citation.get("dataset_id"),
                    "text": citation.get("text", ""),
                }
                yield f"event: citation\ndata: {json.dumps(citation_data, ensure_ascii=False)}\n\n"
            
            # Check guardrail
            guardrail = assistant_msg.guardrail or {}
            if guardrail.get("action") == "block":
                yield f"event: denied\ndata: {json.dumps({'reason': 'Content blocked by guardrail'}, ensure_ascii=False)}\n\n"
            else:
                # Send done event
                done_data = {
                    "conversation_id": str(conversation.id),
                    "message_id": str(assistant_msg.id),
                    "tokens_in": assistant_msg.tokens_in,
                    "tokens_out": assistant_msg.tokens_out,
                }
                yield f"event: done\ndata: {json.dumps(done_data, ensure_ascii=False)}\n\n"
            
            logger.info(
                "api.chat.stream.complete",
                conversation_id=str(conversation.id),
                user_id=str(user.id),
            )
            
        except Exception as e:
            logger.error("api.chat.stream.error", error=str(e), user_id=str(user.id))
            yield f"event: error\ndata: {{'error': 'Internal server error'}}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post("/chat/sync", response_model=ChatResponse)
async def chat_sync(
    request: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Chat with AI assistant (non-streaming, for testing).
    
    Example:
        ```
        POST /api/v1/ai/chat/sync
        {
            "message": "2024年4月销售额是多少？",
            "conversation_id": "abc123..." // optional
        }
        ```
    """
    try:
        service = AIService(db)
        
        conversation, user_msg, assistant_msg = await service.chat(
            user_input=request.message,
            user=user,
            conversation_id=request.conversation_id,
        )
        
        await db.commit()
        
        logger.info(
            "api.chat.sync.complete",
            conversation_id=str(conversation.id),
            user_id=str(user.id),
        )
        
        return ChatResponse(
            conversation_id=conversation.id,
            message_id=assistant_msg.id,
            answer=assistant_msg.content,
            citations=assistant_msg.citations,
            guardrail=assistant_msg.guardrail or {},
            tokens_in=assistant_msg.tokens_in,
            tokens_out=assistant_msg.tokens_out,
        )
        
    except Exception as e:
        logger.error("api.chat.sync.error", error=str(e), user_id=str(user.id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process chat request",
        )


# ============================================================================
# Conversation management endpoints
# ============================================================================

@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationListResponse:
    """List user's conversations.
    
    Example:
        ```
        GET /api/v1/ai/conversations?page=1&page_size=20
        ```
    """
    service = AIService(db)
    
    conversations, total = await service.list_conversations(
        user=user,
        page=page,
        page_size=page_size,
    )
    
    return ConversationListResponse(
        conversations=[
            AIConversationResponse(
                id=c.id,
                user_id=c.user_id,
                title=c.title,
                created_at=c.created_at,
                message_count=None,  # TODO: Add message count
            )
            for c in conversations
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/conversations", response_model=AIConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request: AIConversationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AIConversationResponse:
    """Create new conversation.
    
    Example:
        ```
        POST /api/v1/ai/conversations
        {
            "title": "销售数据查询"
        }
        ```
    """
    service = AIService(db)
    
    conversation = await service.create_conversation(
        user=user,
        title=request.title,
    )
    
    await db.commit()
    
    return AIConversationResponse(
        id=conversation.id,
        user_id=conversation.user_id,
        title=conversation.title,
        created_at=conversation.created_at,
        message_count=0,
    )


@router.get("/conversations/{conversation_id}", response_model=AIConversationDetail)
async def get_conversation(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AIConversationDetail:
    """Get conversation detail with messages.
    
    Example:
        ```
        GET /api/v1/ai/conversations/abc123...
        ```
    """
    service = AIService(db)
    
    try:
        conversation = await service.get_conversation(conversation_id, user)
        messages = await service.get_messages(conversation_id, user)
        
        return AIConversationDetail(
            id=conversation.id,
            user_id=conversation.user_id,
            title=conversation.title,
            created_at=conversation.created_at,
            message_count=len(messages),
            messages=[
                AIMessageResponse(
                    id=m.id,
                    conversation_id=m.conversation_id,
                    role=m.role,
                    content=m.content,
                    citations=m.citations,
                    guardrail=m.guardrail,
                    tokens_in=m.tokens_in,
                    tokens_out=m.tokens_out,
                    created_at=m.created_at,
                )
                for m in messages
            ],
        )
        
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )


@router.patch("/conversations/{conversation_id}", response_model=AIConversationResponse)
async def update_conversation(
    conversation_id: UUID,
    request: AIConversationUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AIConversationResponse:
    """Update conversation title.
    
    Example:
        ```
        PATCH /api/v1/ai/conversations/abc123...
        {
            "title": "新标题"
        }
        ```
    """
    service = AIService(db)
    
    try:
        conversation = await service.update_conversation_title(
            conversation_id=conversation_id,
            user=user,
            title=request.title,
        )
        
        await db.commit()
        
        return AIConversationResponse(
            id=conversation.id,
            user_id=conversation.user_id,
            title=conversation.title,
            created_at=conversation.created_at,
            message_count=None,
        )
        
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete conversation.
    
    Example:
        ```
        DELETE /api/v1/ai/conversations/abc123...
        ```
    """
    service = AIService(db)
    
    try:
        await service.delete_conversation(conversation_id, user)
        await db.commit()
        
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )


@router.get("/conversations/{conversation_id}/messages", response_model=list[AIMessageResponse])
async def get_messages(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AIMessageResponse]:
    """Get messages in conversation.
    
    Example:
        ```
        GET /api/v1/ai/conversations/abc123.../messages
        ```
    """
    service = AIService(db)
    
    try:
        messages = await service.get_messages(conversation_id, user)
        
        return [
            AIMessageResponse(
                id=m.id,
                conversation_id=m.conversation_id,
                role=m.role,
                content=m.content,
                citations=m.citations,
                guardrail=m.guardrail,
                tokens_in=m.tokens_in,
                tokens_out=m.tokens_out,
                created_at=m.created_at,
            )
            for m in messages
        ]
        
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
