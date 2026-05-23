"""AI service — conversation management and agent invocation.

Handles:
- Creating and managing conversations
- Invoking agent for chat
- Storing messages and citations
- Token usage tracking
"""
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.ai_conversation import AIConversation, AIMessage
from app.ai.agent import run_agent
from app.utils.errors import NotFoundError

logger = structlog.get_logger(__name__)


class AIService:
    """Service for AI conversation management."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_conversation(
        self,
        user: User,
        title: str | None = None,
    ) -> AIConversation:
        """Create new conversation.
        
        Args:
            user: User object
            title: Optional conversation title
        
        Returns:
            Created AIConversation
        """
        conversation = AIConversation(
            tenant_id=user.tenant_id,
            user_id=user.id,
            title=title,
        )
        
        self.db.add(conversation)
        await self.db.flush()
        await self.db.refresh(conversation)
        
        logger.info(
            "ai_service.conversation.created",
            conversation_id=str(conversation.id),
            user_id=str(user.id),
        )
        
        return conversation

    async def get_conversation(
        self,
        conversation_id: UUID,
        user: User,
    ) -> AIConversation:
        """Get conversation by ID.
        
        Args:
            conversation_id: Conversation UUID
            user: User object (for permission check)
        
        Returns:
            AIConversation
        
        Raises:
            NotFoundError: If conversation not found or not owned by user
        """
        stmt = select(AIConversation).where(
            AIConversation.id == conversation_id,
            AIConversation.tenant_id == user.tenant_id,
            AIConversation.user_id == user.id,
        )
        
        result = await self.db.execute(stmt)
        conversation = result.scalar_one_or_none()
        
        if not conversation:
            raise NotFoundError(f"Conversation {conversation_id} not found")
        
        return conversation

    async def list_conversations(
        self,
        user: User,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AIConversation], int]:
        """List user's conversations.
        
        Args:
            user: User object
            page: Page number (1-indexed)
            page_size: Items per page
        
        Returns:
            Tuple of (conversations, total_count)
        """
        # Count total
        count_stmt = select(func.count(AIConversation.id)).where(
            AIConversation.tenant_id == user.tenant_id,
            AIConversation.user_id == user.id,
        )
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar_one()
        
        # Get page
        stmt = (
            select(AIConversation)
            .where(
                AIConversation.tenant_id == user.tenant_id,
                AIConversation.user_id == user.id,
            )
            .order_by(AIConversation.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        
        result = await self.db.execute(stmt)
        conversations = result.scalars().all()
        
        return list(conversations), total

    async def update_conversation_title(
        self,
        conversation_id: UUID,
        user: User,
        title: str,
    ) -> AIConversation:
        """Update conversation title.
        
        Args:
            conversation_id: Conversation UUID
            user: User object
            title: New title
        
        Returns:
            Updated AIConversation
        """
        conversation = await self.get_conversation(conversation_id, user)
        conversation.title = title
        
        await self.db.flush()
        await self.db.refresh(conversation)
        
        logger.info(
            "ai_service.conversation.title_updated",
            conversation_id=str(conversation_id),
            title=title,
        )
        
        return conversation

    async def delete_conversation(
        self,
        conversation_id: UUID,
        user: User,
    ) -> None:
        """Delete conversation.
        
        Args:
            conversation_id: Conversation UUID
            user: User object
        """
        conversation = await self.get_conversation(conversation_id, user)
        
        await self.db.delete(conversation)
        await self.db.flush()
        
        logger.info(
            "ai_service.conversation.deleted",
            conversation_id=str(conversation_id),
        )

    async def get_messages(
        self,
        conversation_id: UUID,
        user: User,
    ) -> list[AIMessage]:
        """Get messages in conversation.
        
        Args:
            conversation_id: Conversation UUID
            user: User object
        
        Returns:
            List of AIMessage ordered by created_at
        """
        # Verify conversation ownership
        await self.get_conversation(conversation_id, user)
        
        stmt = (
            select(AIMessage)
            .where(
                AIMessage.conversation_id == conversation_id,
                AIMessage.tenant_id == user.tenant_id,
            )
            .order_by(AIMessage.created_at)
        )
        
        result = await self.db.execute(stmt)
        messages = result.scalars().all()
        
        return list(messages)

    async def chat(
        self,
        user_input: str,
        user: User,
        conversation_id: UUID | None = None,
    ) -> tuple[AIConversation, AIMessage, AIMessage]:
        """Process chat message and generate response.
        
        Args:
            user_input: User's message
            user: User object
            conversation_id: Optional existing conversation ID
        
        Returns:
            Tuple of (conversation, user_message, assistant_message)
        
        Example:
            >>> conversation, user_msg, assistant_msg = await service.chat(
            ...     user_input="2024年4月销售额是多少？",
            ...     user=user,
            ... )
        """
        # Get or create conversation
        if conversation_id:
            conversation = await self.get_conversation(conversation_id, user)
        else:
            conversation = await self.create_conversation(user)
        
        # Store user message
        user_message = AIMessage(
            conversation_id=conversation.id,
            tenant_id=user.tenant_id,
            role="user",
            content=user_input,
            citations=[],
            guardrail=None,
            tokens_in=None,
            tokens_out=None,
        )
        
        self.db.add(user_message)
        await self.db.flush()
        
        logger.info(
            "ai_service.chat.user_message_stored",
            conversation_id=str(conversation.id),
            message_id=str(user_message.id),
        )
        
        # Run agent
        try:
            final_state = await run_agent(
                user_input=user_input,
                user=user,
                tenant_id=user.tenant_id,
                db=self.db,
            )
            
            answer = final_state.get("answer", "")
            retrieval = final_state.get("retrieval", [])
            guardrail = final_state.get("guardrail", {})
            
            # Extract citations from retrieval
            citations = [
                {
                    "record_id": chunk.get("record_id"),
                    "dataset_id": chunk.get("dataset_id"),
                    "text": chunk.get("text", "")[:200],  # Truncate for storage
                }
                for chunk in retrieval
            ]
            
            # TODO: Extract token usage from LLM responses
            tokens_in = None
            tokens_out = None
            
            logger.info(
                "ai_service.chat.agent_complete",
                conversation_id=str(conversation.id),
                answer_length=len(answer),
                citations_count=len(citations),
                guardrail_passed=guardrail.get("passed", True),
            )
            
        except Exception as e:
            import traceback
            logger.error(
                "ai_service.chat.agent_error",
                conversation_id=str(conversation.id),
                error=str(e),
                traceback=traceback.format_exc(),
            )
            
            # Return error message
            answer = "抱歉，处理您的问题时出现错误。请稍后重试。"
            citations = []
            guardrail = {"passed": True, "violations": [], "risk_level": "low", "action": "allow"}
            tokens_in = None
            tokens_out = None
        
        # Store assistant message
        assistant_message = AIMessage(
            conversation_id=conversation.id,
            tenant_id=user.tenant_id,
            role="assistant",
            content=answer,
            citations=citations,
            guardrail=guardrail,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        
        self.db.add(assistant_message)
        await self.db.flush()
        await self.db.refresh(assistant_message)
        
        # Auto-generate title if first message
        if not conversation.title:
            # Simple title generation: first 50 chars of user input
            conversation.title = user_input[:50] + ("..." if len(user_input) > 50 else "")
            await self.db.flush()
        
        logger.info(
            "ai_service.chat.complete",
            conversation_id=str(conversation.id),
            user_message_id=str(user_message.id),
            assistant_message_id=str(assistant_message.id),
        )
        
        return conversation, user_message, assistant_message
