"""Event bus for real-time notifications.

Phase 6: In-process implementation with Redis interface for future multi-instance support.
- EventBus maintains in-memory subscribers (tenant_id → callbacks)
- publish() directly invokes local callbacks
- Redis pub/sub interface reserved for Phase 11 multi-instance deployment
"""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any, Callable, Awaitable
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)

# Type alias for event callback
EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


class EventBus:
    """In-process event bus with tenant isolation.
    
    Events are published to channels within a tenant context.
    Subscribers register callbacks for specific tenant_id.
    
    Future: Phase 11 will add Redis pub/sub for multi-instance coordination.
    """

    def __init__(self) -> None:
        # tenant_id → list of callbacks
        self._subscribers: dict[UUID, list[EventCallback]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def subscribe(
        self, tenant_id: UUID, callback: EventCallback
    ) -> None:
        """Register a callback for events in a specific tenant.
        
        Args:
            tenant_id: Tenant to subscribe to
            callback: Async function(channel: str, event: dict) to invoke on events
        """
        async with self._lock:
            self._subscribers[tenant_id].append(callback)
            logger.debug(
                "eventbus.subscribe",
                tenant_id=str(tenant_id),
                subscriber_count=len(self._subscribers[tenant_id]),
            )

    async def unsubscribe(
        self, tenant_id: UUID, callback: EventCallback
    ) -> None:
        """Unregister a callback.
        
        Args:
            tenant_id: Tenant to unsubscribe from
            callback: The callback to remove
        """
        async with self._lock:
            if tenant_id in self._subscribers:
                try:
                    self._subscribers[tenant_id].remove(callback)
                    logger.debug(
                        "eventbus.unsubscribe",
                        tenant_id=str(tenant_id),
                        subscriber_count=len(self._subscribers[tenant_id]),
                    )
                    # Clean up empty lists
                    if not self._subscribers[tenant_id]:
                        del self._subscribers[tenant_id]
                except ValueError:
                    pass  # Callback not found, ignore

    async def publish(
        self,
        tenant_id: UUID,
        channel: str,
        event: dict[str, Any],
    ) -> None:
        """Publish an event to all subscribers in a tenant.
        
        Args:
            tenant_id: Tenant context for this event
            channel: Channel name (e.g., "dataset:abc", "approvals")
            event: Event payload (must be JSON-serializable)
        
        Events are delivered to all callbacks registered for this tenant.
        Callbacks are invoked concurrently; failures are logged but don't block others.
        """
        # Validate event is JSON-serializable
        try:
            json.dumps(event)
        except (TypeError, ValueError) as e:
            logger.error(
                "eventbus.publish.invalid_event",
                tenant_id=str(tenant_id),
                channel=channel,
                error=str(e),
            )
            return

        # Get subscribers snapshot (avoid holding lock during callbacks)
        async with self._lock:
            callbacks = list(self._subscribers.get(tenant_id, []))

        if not callbacks:
            logger.debug(
                "eventbus.publish.no_subscribers",
                tenant_id=str(tenant_id),
                channel=channel,
            )
            return

        logger.debug(
            "eventbus.publish",
            tenant_id=str(tenant_id),
            channel=channel,
            event_type=event.get("type"),
            subscriber_count=len(callbacks),
        )

        # Invoke all callbacks concurrently
        tasks = [self._safe_invoke(callback, channel, event) for callback in callbacks]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_invoke(
        self,
        callback: EventCallback,
        channel: str,
        event: dict[str, Any],
    ) -> None:
        """Invoke a callback with error handling."""
        try:
            await callback(channel, event)
        except Exception as e:
            logger.error(
                "eventbus.callback_error",
                channel=channel,
                event_type=event.get("type"),
                error=str(e),
                exc_info=True,
            )

    async def get_subscriber_count(self, tenant_id: UUID) -> int:
        """Get number of active subscribers for a tenant (for monitoring)."""
        async with self._lock:
            return len(self._subscribers.get(tenant_id, []))


# Global singleton instance
_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Get the global EventBus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
