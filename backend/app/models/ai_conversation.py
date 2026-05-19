"""AI conversation models — chat history and message storage.

AIConversation:
- Represents a chat session between user and AI assistant
- Contains multiple messages (user questions + assistant responses)

AIMessage:
- Individual message in a conversation
- Stores role (user/assistant/system/tool), content, citations, guardrail info
- Tracks token usage for cost monitoring
"""
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
import sqlalchemy as sa

from app.models.base_model import Base, TenantMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.user import User


class AIConversation(Base, TenantMixin):
    """AI conversation — chat session between user and assistant.
    
    Attributes:
        id: Primary key (UUID)
        tenant_id: Foreign key to tenants (RLS enforced)
        user_id: Foreign key to users
        title: Conversation title (auto-generated from first message or user-provided)
        created_at: Timestamp when conversation was created
    
    Relationships:
        tenant: Parent tenant
        user: User who owns this conversation
        messages: List of messages in this conversation
    """

    __tablename__ = "ai_conversations"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
        comment="Conversation UUID",
    )

    user_id: Mapped[UUID] = mapped_column(
        sa.Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who owns this conversation",
    )

    title: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Conversation title",
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
        comment="Creation timestamp",
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", lazy="joined")
    user: Mapped["User"] = relationship("User", lazy="selectin")
    messages: Mapped[list["AIMessage"]] = relationship(
        "AIMessage",
        back_populates="conversation",
        lazy="noload",
        cascade="all, delete-orphan",
        order_by="AIMessage.created_at",
    )

    def __repr__(self) -> str:
        return f"<AIConversation(id={self.id}, user_id={self.user_id}, title='{self.title}')>"


class AIMessage(Base, TenantMixin):
    """AI message — individual message in a conversation.
    
    Attributes:
        id: Primary key (UUID)
        conversation_id: Foreign key to ai_conversations
        tenant_id: Foreign key to tenants (RLS enforced)
        role: Message role (user/assistant/system/tool)
        content: Message content (text)
        citations: JSONB array of citations (record IDs referenced in response)
        guardrail: JSONB object with guardrail check results (violations, risk_level, action)
        tokens_in: Input tokens used (for cost tracking)
        tokens_out: Output tokens used (for cost tracking)
        created_at: Timestamp when message was created
    
    Relationships:
        tenant: Parent tenant
        conversation: Parent conversation
    
    Example citations:
        [
            {"record_id": "abc123...", "dataset_id": "def456...", "text": "..."},
            ...
        ]
    
    Example guardrail:
        {
            "passed": true,
            "violations": [],
            "risk_level": "low",
            "action": "allow"
        }
    """

    __tablename__ = "ai_messages"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
        comment="Message UUID",
    )

    conversation_id: Mapped[UUID] = mapped_column(
        sa.Uuid,
        ForeignKey("ai_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent conversation",
    )

    role: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Message role (user/assistant/system/tool)",
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Message content",
    )

    citations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
        comment="Citations (record IDs referenced)",
    )

    guardrail: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Guardrail check results",
    )

    tokens_in: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Input tokens used",
    )

    tokens_out: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Output tokens used",
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
        comment="Creation timestamp",
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", lazy="joined")
    conversation: Mapped["AIConversation"] = relationship(
        "AIConversation",
        back_populates="messages",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'system', 'tool')",
            name="ck_message_role",
        ),
        sa.Index(
            "ix_msg_conv",
            "conversation_id",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return f"<AIMessage(id={self.id}, role='{self.role}', conversation_id={self.conversation_id})>"
