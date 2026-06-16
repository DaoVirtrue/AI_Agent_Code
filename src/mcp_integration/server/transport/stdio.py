"""
Stdio transport for MCP Server.

Handles line-delimited JSON-RPC 2.0 messages over stdin/stdout.
Implements the standard MCP transport protocol.
"""

import asyncio
import json
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)


class StdioTransport:
    """Line-delimited JSON-RPC transport over stdin/stdout.

    Each message is a single line of JSON terminated by \n.
    This transport is used for local/subprocess MCP connections.

    Args:
        server: The MCPServer instance to serve.
        buffer_size: Read buffer size in bytes.
    """

    def __init__(self, server=None, buffer_size: int = 65536):
        self.server = server
        self.buffer_size = buffer_size
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._running = False

    async def serve(self) -> None:
        """Start serving on stdin/stdout.

        Creates a read loop that processes incoming JSON-RPC lines
        and writes responses back to stdout.
        """
        if not self.server:
            raise RuntimeError("No MCPServer configured for transport.")

        loop = asyncio.get_event_loop()
        self._reader = asyncio.StreamReader(limit=self.buffer_size)
        protocol = asyncio.StreamReaderProtocol(self._reader)

        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        # Setup writer for stdout
        w_transport, w_protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin,
            sys.stdout,
        )
        self._writer = asyncio.StreamWriter(
            w_transport, w_protocol, self._reader, loop,
        )

        self._running = True
        logger.info("Stdio transport started for MCP server '%s'", self.server.name)

        try:
            while self._running:
                try:
                    line = await self._reader.readline()
                    if not line:
                        # EOF
                        logger.info("Stdio transport: EOF received, shutting down.")
                        break

                    line_str = line.decode("utf-8").strip()
                    if not line_str:
                        continue

                    response = await self.server.handle_request(line_str)

                    self._writer.write((response + "\n").encode("utf-8"))
                    await self._writer.drain()

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.exception("Error processing stdio message")
                    error_response = json.dumps({
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32603, "message": str(e)},
                    })
                    self._writer.write((error_response + "\n").encode("utf-8"))
                    await self._writer.drain()

        finally:
            await self.close()

    async def close(self) -> None:
        """Clean up the transport."""
        self._running = False
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        logger.info("Stdio transport closed.")


async def run_stdio_server(server) -> None:
    """Convenience function to run an MCP server over stdio.

    Args:
        server: MCPServer instance.
    """
    transport = StdioTransport(server=server)
    await transport.serve()
