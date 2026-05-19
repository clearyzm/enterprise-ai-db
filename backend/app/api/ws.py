"""FastAPI WebSocket endpoint for real-time event streaming.

WSS /ws?token=<access_token>  (or Authorization: Bearer <token> in handshake headers)

Protocol:
  Client → Server:
    { "type": "subscribe",   "channels": ["dataset:abc", "approvals"] }
    { "type": "unsubscribe", "channels": ["dataset:abc"] }
    { "type": "ping" }

  Server → Client:
    { "type": "pong" }
    { "type": "subscribed",   "results": {"dataset:abc": "ok", "approvals": "ok"} }
    { "type": "unsubscribed", "channels": ["dataset:abc"] }
    { "type": "error",        "message": "..." }
    { "channel": "dataset:abc", "type": "record.upserted", ... }
"""
from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_maker
from app.models.user import User
from app.realtime.ws_manager import get_ws_manager, WSConnection
from app.utils.errors import TokenInvalidError, TokenExpiredError, AuthenticationError
from app.utils.jwt import decode_access_token

logger = structlog.get_logger(__name__)

router = APIRouter()


async def _authenticate_ws(
    token: str | None,
    db: AsyncSession,
) -> User:
    """Authenticate a WebSocket connection using an access token.

    Args:
        token: JWT access token (from query param or header)
        db: Database session

    Returns:
        Authenticated User

    Raises:
        TokenInvalidError: Missing, malformed, or expired token
        AuthenticationError: User not found or inactive
    """
    if not token:
        raise TokenInvalidError()

    payload = decode_access_token(token)

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise TokenInvalidError()

    try:
        user_id = UUID(user_id_str)
    except (ValueError, TypeError):
        raise TokenInvalidError()

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise AuthenticationError("User not found")
    if user.status != "active":
        raise AuthenticationError("User account is not active")

    return user


async def _handle_subscribe(
    conn: WSConnection,
    data: dict[str, Any],
    db: AsyncSession,
) -> None:
    """Handle subscribe message from client."""
    channels = data.get("channels", [])
    if not isinstance(channels, list):
        await conn.send_json({"type": "error", "message": "channels must be a list"})
        return

    manager = get_ws_manager()
    results = await manager.subscribe_channels(conn, channels, db)
    await conn.send_json({"type": "subscribed", "results": results})


async def _handle_unsubscribe(
    conn: WSConnection,
    data: dict[str, Any],
) -> None:
    """Handle unsubscribe message from client."""
    channels = data.get("channels", [])
    if not isinstance(channels, list):
        await conn.send_json({"type": "error", "message": "channels must be a list"})
        return

    manager = get_ws_manager()
    await manager.unsubscribe_channels(conn, channels)
    await conn.send_json({"type": "unsubscribed", "channels": channels})


async def _message_loop(
    conn: WSConnection,
    websocket: WebSocket,
    db: AsyncSession,
) -> None:
    """Process incoming messages from a single WebSocket connection."""
    while True:
        try:
            data = await asyncio.wait_for(websocket.receive_json(), timeout=PING_TIMEOUT_S)
        except asyncio.TimeoutError:
            # No message received within 30s — server-side ping timeout
            logger.info(
                "ws.ping_timeout",
                user_id=str(conn.user.id),
                connection_id=conn.connection_id,
            )
            await websocket.close(code=1000, reason="Ping timeout")
            return
        except WebSocketDisconnect:
            return
        except Exception as e:
            logger.warning("ws.receive_error", user_id=str(conn.user.id), error=str(e))
            return

        msg_type = data.get("type") if isinstance(data, dict) else None

        if msg_type == "ping":
            conn.update_ping()
            await conn.send_json({"type": "pong"})

        elif msg_type == "subscribe":
            conn.update_ping()
            await _handle_subscribe(conn, data, db)

        elif msg_type == "unsubscribe":
            conn.update_ping()
            await _handle_unsubscribe(conn, data)

        elif msg_type is None:
            await conn.send_json({"type": "error", "message": "missing type field"})

        else:
            await conn.send_json({"type": "error", "message": f"unknown type: {msg_type}"})


# 30s server-side receive timeout mirrors the ping-timeout requirement
PING_TIMEOUT_S = 30


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(default=None, description="JWT access token"),
) -> None:
    """WebSocket endpoint for real-time event streaming.

    Authentication:
      Pass the access token via query parameter: /ws?token=<access_token>
      Or via the Sec-WebSocket-Protocol header (not yet implemented).

    After connection, the client sends subscribe messages to opt into channels.
    The server pushes events to subscribed channels.
    """
    # --- authentication ---
    async with async_session_maker() as db:
        # Support token from query param; header Bearer is handled by HTTP upgrade
        # before WebSocket handshake completes, so we read from query param first.
        ws_token = token
        if ws_token is None:
            # Attempt to read from Sec-WebSocket-Protocol header as fallback
            # (some browser environments can't set custom headers on WS upgrade)
            ws_token = websocket.headers.get("authorization", "").removeprefix("Bearer ").strip() or None

        try:
            user = await _authenticate_ws(ws_token, db)
        except (TokenInvalidError, TokenExpiredError, AuthenticationError) as exc:
            await websocket.close(code=4001, reason=str(exc))
            return

        tenant_id: UUID = user.tenant_id

        # --- register connection ---
        manager = get_ws_manager()
        conn: WSConnection = await manager.connect(websocket, user, tenant_id)

        logger.info(
            "ws.session_start",
            user_id=str(user.id),
            tenant_id=str(tenant_id),
        )

        try:
            await _message_loop(conn, websocket, db)
        except WebSocketDisconnect:
            pass
        finally:
            await manager.disconnect(conn)
            logger.info(
                "ws.session_end",
                user_id=str(user.id),
                tenant_id=str(tenant_id),
            )
