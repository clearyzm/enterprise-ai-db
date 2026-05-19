"""WebSocket connection manager with channel-based routing.

Phase 6: WebSocket connection pool + channel subscription management
- Maintains active WebSocket connections per tenant
- Routes events from EventBus to subscribed WebSocket clients
- Enforces permission checks on channel subscriptions
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from fastapi import WebSocket
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.dataset import DataSet
from app.realtime.redis_bus import get_event_bus, EventBus
from app.services.permission_service import PermissionService

logger = structlog.get_logger(__name__)

# Heartbeat configuration
PING_INTERVAL = 25  # Client should send ping every 25s
PING_TIMEOUT = 30   # Server disconnects if no ping for 30s


class WSConnection:
    """Represents a single WebSocket connection with its subscriptions."""

    def __init__(
        self,
        websocket: WebSocket,
        user: User,
        tenant_id: UUID,
    ) -> None:
        self.websocket = websocket
        self.user = user
        self.tenant_id = tenant_id
        self.subscribed_channels: set[str] = set()
        self.last_ping: datetime = datetime.utcnow()
        self.connection_id = id(websocket)  # Unique identifier

    async def send_json(self, data: dict[str, Any]) -> None:
        """Send JSON message to client with error handling."""
        try:
            await self.websocket.send_json(data)
        except Exception as e:
            logger.warning(
                "ws.send_failed",
                user_id=str(self.user.id),
                error=str(e),
            )
            raise

    def update_ping(self) -> None:
        """Update last ping timestamp."""
        self.last_ping = datetime.utcnow()

    def is_alive(self) -> bool:
        """Check if connection is still alive based on ping timeout."""
        return datetime.utcnow() - self.last_ping < timedelta(seconds=PING_TIMEOUT)


class WSManager:
    """Manages WebSocket connections and routes events to subscribers."""

    def __init__(self) -> None:
        self._connections: dict[UUID, set[WSConnection]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._event_bus: EventBus = get_event_bus()
        self._subscribed_tenants: set[UUID] = set()

    async def connect(
        self,
        websocket: WebSocket,
        user: User,
        tenant_id: UUID,
    ) -> WSConnection:
        """Register a new WebSocket connection."""
        await websocket.accept()
        conn = WSConnection(websocket, user, tenant_id)
        
        async with self._lock:
            self._connections[tenant_id].add(conn)
            if tenant_id not in self._subscribed_tenants:
                await self._event_bus.subscribe(tenant_id, self._handle_event)
                self._subscribed_tenants.add(tenant_id)
        
        logger.info(
            "ws.connected",
            user_id=str(user.id),
            tenant_id=str(tenant_id),
            connection_id=conn.connection_id,
        )
        return conn

    async def disconnect(self, conn: WSConnection) -> None:
        """Unregister a WebSocket connection."""
        async with self._lock:
            tenant_id = conn.tenant_id
            if tenant_id in self._connections:
                self._connections[tenant_id].discard(conn)
                if not self._connections[tenant_id]:
                    del self._connections[tenant_id]
                    if tenant_id in self._subscribed_tenants:
                        await self._event_bus.unsubscribe(tenant_id, self._handle_event)
                        self._subscribed_tenants.discard(tenant_id)
        
        logger.info("ws.disconnected", user_id=str(conn.user.id), connection_id=conn.connection_id)

    async def subscribe_channels(
        self,
        conn: WSConnection,
        channels: list[str],
        db: AsyncSession,
    ) -> dict[str, str]:
        """Subscribe connection to channels with permission checks.
        
        Returns:
            Dict mapping channel → status ("ok" or error message)
        """
        results: dict[str, str] = {}
        for channel in channels:
            try:
                if await self._can_subscribe(conn, channel, db):
                    conn.subscribed_channels.add(channel)
                    results[channel] = "ok"
                    logger.debug("ws.subscribed", user_id=str(conn.user.id), channel=channel)
                else:
                    results[channel] = "permission_denied"
                    logger.warning("ws.subscribe_denied", user_id=str(conn.user.id), channel=channel)
            except Exception as e:
                results[channel] = f"error: {str(e)}"
                logger.error("ws.subscribe_error", user_id=str(conn.user.id), channel=channel, error=str(e))
        return results

    async def unsubscribe_channels(self, conn: WSConnection, channels: list[str]) -> None:
        """Unsubscribe connection from channels."""
        for channel in channels:
            conn.subscribed_channels.discard(channel)
            logger.debug("ws.unsubscribed", user_id=str(conn.user.id), channel=channel)

    async def _can_subscribe(self, conn: WSConnection, channel: str, db: AsyncSession) -> bool:
        """Check if user has permission to subscribe to a channel.
        
        Channel formats:
        - dataset:{id} → requires read:dataset permission
        - record:{id} → requires read:dataset permission (via record's dataset)
        - approvals → always allowed (filtered by user context)
        - ai:{conv_id} → requires ownership or admin (not implemented in Phase 6)
        - notifications → always allowed (user's own notifications)
        """
        parts = channel.split(":", 1)
        if len(parts) != 2:
            return False
        
        channel_type, channel_id = parts
        
        if channel_type == "dataset":
            try:
                dataset_id = UUID(channel_id)
                stmt = select(DataSet).where(
                    DataSet.id == dataset_id,
                    DataSet.tenant_id == conn.tenant_id,
                )
                result = await db.execute(stmt)
                dataset = result.scalar_one_or_none()
                if dataset is None:
                    return False
                perm_svc = PermissionService(db)
                return await perm_svc.check(conn.user, "read", "dataset", dataset)
            except (ValueError, Exception):
                return False
        
        elif channel_type == "record":
            try:
                from app.models.record import DataRecord
                record_id = UUID(channel_id)
                stmt = select(DataRecord.dataset_id).where(
                    DataRecord.id == record_id,
                    DataRecord.tenant_id == conn.tenant_id,
                )
                result = await db.execute(stmt)
                dataset_id = result.scalar_one_or_none()
                if dataset_id is None:
                    return False
                # Check read:dataset on the record's parent dataset
                ds_stmt = select(DataSet).where(DataSet.id == dataset_id)
                ds_result = await db.execute(ds_stmt)
                dataset = ds_result.scalar_one_or_none()
                if dataset is None:
                    return False
                perm_svc = PermissionService(db)
                return await perm_svc.check(conn.user, "read", "dataset", dataset)
            except (ValueError, Exception):
                return False
        
        elif channel_type in ("approvals", "ai", "notifications"):
            # Always allowed - events are filtered by user context
            return True
        
        else:
            return False

    async def _handle_event(self, channel: str, event: dict[str, Any]) -> None:
        """Handle event from EventBus and route to subscribed connections."""
        connections_snapshot: list[WSConnection] = []
        async with self._lock:
            for tenant_conns in self._connections.values():
                connections_snapshot.extend(tenant_conns)
        
        subscribed = [conn for conn in connections_snapshot if channel in conn.subscribed_channels]
        if not subscribed:
            return
        
        logger.debug("ws.routing_event", channel=channel, event_type=event.get("type"), recipient_count=len(subscribed))
        tasks = [self._safe_send(conn, {"channel": channel, **event}) for conn in subscribed]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_send(self, conn: WSConnection, message: dict[str, Any]) -> None:
        """Send message to connection with error handling."""
        try:
            await conn.send_json(message)
        except Exception as e:
            logger.warning("ws.send_failed", user_id=str(conn.user.id), connection_id=conn.connection_id, error=str(e))

    async def cleanup_stale_connections(self) -> int:
        """Remove connections that haven't sent ping within timeout."""
        stale: list[WSConnection] = []
        async with self._lock:
            for tenant_conns in self._connections.values():
                for conn in list(tenant_conns):
                    if not conn.is_alive():
                        stale.append(conn)
        
        for conn in stale:
            try:
                await conn.websocket.close(code=1000, reason="Ping timeout")
            except Exception:
                pass
            await self.disconnect(conn)
        
        if stale:
            logger.info("ws.cleanup_stale", count=len(stale))
        return len(stale)

    async def get_stats(self) -> dict[str, Any]:
        """Get connection statistics (for monitoring)."""
        async with self._lock:
            total = sum(len(conns) for conns in self._connections.values())
            return {
                "total_connections": total,
                "tenants_with_connections": len(self._connections),
                "subscribed_tenants": len(self._subscribed_tenants),
            }


# Global singleton instance
_ws_manager: WSManager | None = None


def get_ws_manager() -> WSManager:
    """Get the global WSManager instance."""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WSManager()
    return _ws_manager
