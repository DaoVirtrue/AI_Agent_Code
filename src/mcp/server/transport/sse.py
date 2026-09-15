"""
SSE (Server-Sent Events) transport for MCP Server.

Provides a FastAPI-based HTTP transport with SSE streaming for
MCP clients that connect over the network.
"""

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def create_sse_app(mcp_server):
    """Create a FastAPI application with SSE transport endpoints.

    Provides two endpoints:
    - POST /message: Accept JSON-RPC requests and return responses
    - GET /sse: SSE stream for server-to-client events

    Args:
        mcp_server: An MCPServer instance.

    Returns:
        A FastAPI application instance.
    """
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, StreamingResponse

    app = FastAPI(
        title=f"MCP Server - {mcp_server.name}",
        version=mcp_server.version,
    )

    # Store active SSE connections
    sse_clients: list[asyncio.Queue] = []

    @app.post("/message")
    async def handle_message(request: Request):
        """Handle JSON-RPC 2.0 messages."""
        try:
            body = await request.body()
            raw_message = body.decode("utf-8")
        except Exception as e:
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {e}"},
                },
                status_code=400,
            )

        response = await mcp_server.handle_request(raw_message)

        # Broadcast response to SSE clients
        for queue in sse_clients:
            try:
                queue.put_nowait(response)
            except asyncio.QueueFull:
                pass

        try:
            return JSONResponse(content=json.loads(response))
        except json.JSONDecodeError:
            return JSONResponse(content={"jsonrpc": "2.0", "result": response})

    @app.get("/sse")
    async def sse_stream(request: Request):
        """SSE stream endpoint for server-to-client events."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        sse_clients.append(queue)

        async def event_generator():
            try:
                # Send initial connection event
                yield f"data: {json.dumps({'type': 'connected', 'server': mcp_server.name})}\n\n"

                while True:
                    if await request.is_disconnected():
                        break

                    try:
                        message = await asyncio.wait_for(queue.get(), timeout=15.0)
                        yield f"data: {message}\n\n"
                    except asyncio.TimeoutError:
                        # Send keepalive comment
                        yield ": keepalive\n\n"

            except asyncio.CancelledError:
                pass
            finally:
                if queue in sse_clients:
                    sse_clients.remove(queue)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "server": mcp_server.name,
            "version": mcp_server.version,
            **mcp_server.stats,
        }

    @app.on_event("shutdown")
    async def shutdown():
        """Clean up on shutdown."""
        logger.info("MCP SSE server '%s' shutting down.", mcp_server.name)

    return app
