"""Pydantic schemas for AI conversation API."""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ============================================================================
# AIMessage schemas
# ============================================================================

class AIMessageBase(BaseModel):
    """Base schema for AI message."""
    role: str = Field(..., description="Message role (user/assistant/system/tool)")
    content: str = Field(..., description="Message content")


class AIMessageCreate(AIMessageBase):
    """Schema for creating AI message."""
    conversation_id: UUID = Field(..., description="Parent conversation ID")
    citations: list[dict[str, Any]] = Field(default_factory=list, description="Citations")
    guardrail: dict[str, Any] | None = Field(None, description="Guardrail check results")
    tokens_in: int | None = Field(None, description="Input tokens")
    tokens_out: int | None = Field(None, description="Output tokens")


class AIMessageResponse(AIMessageBase):
    """Schema for AI message response."""
    id: UUID
    conversation_id: UUID
    citations: list[dict[str, Any]]
    guardrail: dict[str, Any] | None
    tokens_in: int | None
    tokens_out: int | None
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# AIConversation schemas
# ============================================================================

class AIConversationBase(BaseModel):
    """Base schema for AI conversation."""
    title: str | None = Field(None, description="Conversation title")


class AIConversationCreate(AIConversationBase):
    """Schema for creating AI conversation."""
    pass


class AIConversationUpdate(BaseModel):
    """Schema for updating AI conversation."""
    title: str = Field(..., description="Conversation title")


class AIConversationResponse(AIConversationBase):
    """Schema for AI conversation response."""
    id: UUID
    user_id: UUID
    created_at: datetime
    message_count: int | None = Field(None, description="Number of messages in conversation")

    class Config:
        from_attributes = True


class AIConversationDetail(AIConversationResponse):
    """Schema for AI conversation with messages."""
    messages: list[AIMessageResponse] = Field(default_factory=list, description="Messages in conversation")


# ============================================================================
# Chat request/response schemas
# ============================================================================

class ChatRequest(BaseModel):
    """Schema for chat request."""
    message: str = Field(..., min_length=1, max_length=10000, description="User message")
    conversation_id: UUID | None = Field(None, description="Existing conversation ID (optional)")


class ChatResponse(BaseModel):
    """Schema for chat response (non-streaming)."""
    conversation_id: UUID
    message_id: UUID
    answer: str
    citations: list[dict[str, Any]]
    guardrail: dict[str, Any]
    tokens_in: int | None
    tokens_out: int | None


# ============================================================================
# SSE event schemas (for streaming)
# ============================================================================

class SSEEvent(BaseModel):
    """Base schema for SSE events."""
    event: str = Field(..., description="Event type")
    data: dict[str, Any] = Field(..., description="Event data")


class TokenEvent(BaseModel):
    """Schema for token event (streaming)."""
    token: str = Field(..., description="Token text")


class CitationEvent(BaseModel):
    """Schema for citation event."""
    record_id: str = Field(..., description="Record ID")
    dataset_id: str = Field(..., description="Dataset ID")
    text: str = Field(..., description="Citation text")


class ToolCallEvent(BaseModel):
    """Schema for tool call event."""
    tool_name: str = Field(..., description="Tool name")
    arguments: dict[str, Any] = Field(..., description="Tool arguments")


class DoneEvent(BaseModel):
    """Schema for done event."""
    conversation_id: str = Field(..., description="Conversation ID")
    message_id: str = Field(..., description="Message ID")
    tokens_in: int | None = Field(None, description="Input tokens")
    tokens_out: int | None = Field(None, description="Output tokens")


class DeniedEvent(BaseModel):
    """Schema for denied event."""
    reason: str = Field(..., description="Denial reason")


# ============================================================================
# List/pagination schemas
# ============================================================================

class ConversationListResponse(BaseModel):
    """Schema for conversation list response."""
    conversations: list[AIConversationResponse]
    total: int
    page: int
    page_size: int
