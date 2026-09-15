"""
Full MCP Server with JSON-RPC 2.0 handling.

Implements the Model Context Protocol specification:
- tools/list, tools/call
- resources/list, resources/read
- prompts/list, prompts/get
- initialize
- JSON-RPC 2.0 error handling
"""

import json
import logging
import sys
import uuid
from typing import Any, Callable

from src.core.tools import BaseTool

logger = logging.getLogger(__name__)

# JSON-RPC 2.0 error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class MCPServer:
    """Model Context Protocol (MCP) Server.

    Hosts tools, resources, and prompts for exposure to MCP clients.
    Communicates via JSON-RPC 2.0 over stdio or SSE transports.

    Args:
        name: Server name (used in initialize response).
        version: Server version string.
        max_request_size: Maximum JSON-RPC request size in bytes.
    """

    def __init__(self, name: str, version: str = "1.0.0", max_request_size: int = 10 * 1024 * 1024):
        self.name = name
        self.version = version
        self.max_request_size = max_request_size

        # Tools
        self._tools: dict[str, BaseTool] = {}

        # Resources
        self._resources: dict[str, dict] = {}

        # Prompts
        self._prompts: dict[str, dict] = {}

        # Hooks/callbacks
        self._on_before_tool_call: Callable | None = None
        self._on_after_tool_call: Callable | None = None

        # Stats
        self._request_count = 0
        self._error_count = 0

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_tool(self, tool: BaseTool) -> None:
        """Register a tool for exposure to MCP clients.

        Args:
            tool: A BaseTool instance.

        Raises:
            ValueError: If a tool with the same name is already registered.
        """
        if tool.definition.name in self._tools:
            raise ValueError(f"Tool '{tool.definition.name}' already registered.")
        self._tools[tool.definition.name] = tool
        logger.info("MCP tool registered: %s", tool.definition.name)

    def register_resource(
        self,
        uri: str,
        name: str,
        description: str,
        handler: Callable,
    ) -> None:
        """Register a resource for reading by clients.

        Args:
            uri: Unique resource URI.
            name: Human-readable name.
            description: Description of the resource.
            handler: Async callable that returns the resource content.
        """
        self._resources[uri] = {
            "uri": uri,
            "name": name,
            "description": description,
            "handler": handler,
        }
        logger.info("MCP resource registered: %s (%s)", name, uri)

    def register_prompt(
        self,
        name: str,
        description: str,
        template: str,
    ) -> None:
        """Register a prompt template.

        Args:
            name: Unique prompt name.
            description: Description of the prompt.
            template: The prompt template string.
        """
        self._prompts[name] = {
            "name": name,
            "description": description,
            "template": template,
        }
        logger.info("MCP prompt registered: %s", name)

    # ------------------------------------------------------------------
    # JSON-RPC 2.0 Dispatch
    # ------------------------------------------------------------------

    async def handle_request(self, raw_message: str) -> str:
        """Handle a raw JSON-RPC 2.0 message.

        Dispatches to the appropriate handler based on the method field.
        Returns a JSON-RPC 2.0 response string.

        Args:
            raw_message: Raw JSON-RPC request string.

        Returns:
            JSON-RPC 2.0 response string.
        """
        self._request_count += 1

        # Parse JSON
        try:
            request = json.loads(raw_message)
        except json.JSONDecodeError as e:
            self._error_count += 1
            return self._error_response(None, PARSE_ERROR, f"Parse error: {e}")

        # Validate basic structure
        if not isinstance(request, dict):
            self._error_count += 1
            return self._error_response(None, INVALID_REQUEST, "Request must be a JSON object.")

        request_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        if not method:
            self._error_count += 1
            return self._error_response(request_id, INVALID_REQUEST, "Missing 'method' field.")

        # Route to handler
        try:
            result = await self._dispatch(method, params, request_id)
        except Exception as e:
            logger.exception("Unhandled error in method '%s'", method)
            self._error_count += 1
            return self._error_response(request_id, INTERNAL_ERROR, str(e))

        # If result is already a JSON-RPC error response, return it
        if isinstance(result, str) and '"error"' in result:
            return result

        # Success response
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        }
        return json.dumps(response, ensure_ascii=False)

    async def _dispatch(self, method: str, params: dict, request_id: Any) -> Any:
        """Dispatch to the appropriate handler method.

        Args:
            method: JSON-RPC method name.
            params: Method parameters.
            request_id: The request ID from the JSON-RPC call.

        Returns:
            Handler result (will be serialized to JSON).
        """
        handlers = {
            "initialize": self._handle_initialize,
            "tools/list": self._handle_list_tools,
            "tools/call": self._handle_call_tool,
            "resources/list": self._handle_list_resources,
            "resources/read": self._handle_read_resource,
            "prompts/list": self._handle_list_prompts,
            "prompts/get": self._handle_get_prompt,
            "notifications/initialized": self._handle_initialized,
            "ping": self._handle_ping,
        }

        handler = handlers.get(method)
        if handler is None:
            return self._error_response(request_id, METHOD_NOT_FOUND, f"Method not found: {method}")

        return await handler(params, request_id)

    # ------------------------------------------------------------------
    # Handler implementations
    # ------------------------------------------------------------------

    async def _handle_initialize(self, params: dict, request_id: Any) -> dict:
        """Handle the initialize method."""
        return {
            "protocolVersion": "0.1.0",
            "serverInfo": {
                "name": self.name,
                "version": self.version,
            },
            "capabilities": {
                "tools": {"enabled": len(self._tools) > 0},
                "resources": {"enabled": len(self._resources) > 0},
                "prompts": {"enabled": len(self._prompts) > 0},
            },
        }

    async def _handle_initialized(self, params: dict, request_id: Any) -> dict:
        """Handle the initialized notification (no response needed)."""
        logger.info("Client initialized connection to MCP server '%s'", self.name)
        return {}

    async def _handle_ping(self, params: dict, request_id: Any) -> dict:
        """Handle ping requests."""
        return {"status": "ok"}

    async def _handle_list_tools(self, params: dict, request_id: Any) -> dict:
        """List all registered tools."""
        tools = []
        for tool in self._tools.values():
            definition = tool.definition
            tools.append({
                "name": definition.name,
                "description": definition.description,
                "inputSchema": {
                    "type": "object",
                    "properties": definition.parameters.get("properties", {}),
                    "required": definition.parameters.get("required", []),
                },
            })
        return {"tools": tools}

    async def _handle_call_tool(self, params: dict, request_id: Any) -> dict:
        """Execute a tool call."""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name not in self._tools:
            return self._error_response(request_id, INVALID_PARAMS, f"Unknown tool: {tool_name}")

        tool = self._tools[tool_name]

        # Pre-call hook
        if self._on_before_tool_call:
            try:
                await self._on_before_tool_call(tool_name, arguments)
            except Exception as e:
                return self._error_response(request_id, INTERNAL_ERROR, f"Pre-call hook failed: {e}")

        try:
            result = await tool.execute(**arguments)
        except Exception as e:
            return self._error_response(request_id, INTERNAL_ERROR, f"Tool execution failed: {e}")

        # Post-call hook
        if self._on_after_tool_call:
            try:
                await self._on_after_tool_call(tool_name, arguments, result)
            except Exception as e:
                logger.warning("Post-call hook failed: %s", e)

        if result.status.value == "success":
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result.data, ensure_ascii=False, default=str),
                    }
                ],
                "isError": False,
            }
        else:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": result.error or "Unknown tool error",
                    }
                ],
                "isError": True,
            }

    async def _handle_list_resources(self, params: dict, request_id: Any) -> dict:
        """List all registered resources."""
        resources = []
        for uri, resource in self._resources.items():
            resources.append({
                "uri": resource["uri"],
                "name": resource["name"],
                "description": resource.get("description", ""),
            })
        return {"resources": resources}

    async def _handle_read_resource(self, params: dict, request_id: Any) -> dict:
        """Read a resource by URI."""
        uri = params.get("uri", "")

        if uri not in self._resources:
            return self._error_response(request_id, INVALID_PARAMS, f"Unknown resource: {uri}")

        resource = self._resources[uri]
        handler = resource["handler"]

        try:
            if asyncio:
                import asyncio as _asyncio
                if _asyncio.iscoroutinefunction(handler):
                    content = await handler(uri, params)
                else:
                    content = handler(uri, params)
            else:
                content = handler(uri, params)
        except Exception as e:
            return self._error_response(request_id, INTERNAL_ERROR, f"Resource read failed: {e}")

        return {
            "contents": [
                {
                    "uri": uri,
                    "text": str(content),
                }
            ],
        }

    async def _handle_list_prompts(self, params: dict, request_id: Any) -> dict:
        """List all registered prompts."""
        prompts = []
        for name, prompt in self._prompts.items():
            prompts.append({
                "name": prompt["name"],
                "description": prompt.get("description", ""),
            })
        return {"prompts": prompts}

    async def _handle_get_prompt(self, params: dict, request_id: Any) -> dict:
        """Get a prompt template by name."""
        prompt_name = params.get("name", "")
        prompt_args = params.get("arguments", {})

        if prompt_name not in self._prompts:
            return self._error_response(request_id, INVALID_PARAMS, f"Unknown prompt: {prompt_name}")

        prompt = self._prompts[prompt_name]
        template = prompt["template"]

        # Apply template arguments via simple string replacement
        for key, value in prompt_args.items():
            template = template.replace(f"{{{{{key}}}}}", str(value))

        return {
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": template,
                    },
                }
            ],
        }

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def _error_response(self, request_id: Any, code: int, message: str) -> str:
        """Create a JSON-RPC 2.0 error response.

        Args:
            request_id: The original request ID (or None).
            code: JSON-RPC error code.
            message: Error message.

        Returns:
            JSON-RPC 2.0 error response string.
        """
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message,
            },
        }
        return json.dumps(response, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Transport methods
    # ------------------------------------------------------------------

    def run_stdio(self) -> None:
        """Run the server using stdin/stdout JSON-RPC transport.

        Reads JSON-RPC requests from stdin line by line and writes
        responses to stdout. Runs synchronously (blocking).
        """
        import asyncio

        logger.info("MCP Server '%s' starting on stdio transport...", self.name)

        async def _read_loop():
            loop = asyncio.get_event_loop()
            reader = asyncio.StreamReader()
            protocol = asyncio.StreamReaderProtocol(reader)

            await loop.connect_read_pipe(lambda: protocol, sys.stdin)
            w_transport, w_protocol = await loop.connect_write_pipe(
                asyncio.streams.FlowControlMixin, sys.stdout
            )
            writer = asyncio.StreamWriter(w_transport, w_protocol, reader, loop)

            while True:
                try:
                    line = await reader.readline()
                    if not line:
                        break

                    line_str = line.decode("utf-8").strip()
                    if not line_str:
                        continue

                    response = await self.handle_request(line_str)
                    writer.write((response + "\n").encode("utf-8"))
                    await writer.drain()

                except Exception as e:
                    logger.exception("Error in stdio read loop")
                    break

        try:
            asyncio.run(_read_loop())
        except KeyboardInterrupt:
            logger.info("MCP Server '%s' shutting down.", self.name)

    async def run_sse(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        """Run the server using SSE (Server-Sent Events) transport.

        Uses FastAPI for the HTTP layer with SSE streaming.

        Args:
            host: Host address to bind to.
            port: Port number.
        """
        try:
            from src.mcp_integration.server.transport.sse import create_sse_app
            import uvicorn
        except ImportError as e:
            logger.error("SSE transport requires fastapi and uvicorn: %s", e)
            return

        app = create_sse_app(self)
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)

        logger.info("MCP Server '%s' starting on SSE transport at %s:%d", self.name, host, port)
        await server.serve()

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def on_before_tool_call(self, callback: Callable) -> None:
        """Register a callback invoked before each tool call."""
        self._on_before_tool_call = callback

    def on_after_tool_call(self, callback: Callable) -> None:
        """Register a callback invoked after each tool call."""
        self._on_after_tool_call = callback

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @property
    def stats(self) -> dict:
        """Return server statistics."""
        return {
            "name": self.name,
            "version": self.version,
            "tools": len(self._tools),
            "resources": len(self._resources),
            "prompts": len(self._prompts),
            "requests": self._request_count,
            "errors": self._error_count,
        }

    def __repr__(self) -> str:
        return (
            f"MCPServer(name={self.name!r}, version={self.version!r}, "
            f"tools={len(self._tools)}, resources={len(self._resources)})"
        )
