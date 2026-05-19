"""Row-Level Security context helpers."""
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def set_tenant_context(session: AsyncSession, tenant_id: UUID | None) -> None:
    tid = str(tenant_id) if tenant_id else "00000000-0000-0000-0000-000000000000"
    await session.execute(text(f"SET LOCAL app.tenant_id = '{tid}'"))


async def set_user_context(session: AsyncSession, user_id: UUID | None) -> None:
    uid = str(user_id) if user_id else "00000000-0000-0000-0000-000000000000"
    await session.execute(text(f"SET LOCAL app.user_id = '{uid}'"))
