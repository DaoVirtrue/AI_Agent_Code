"""
MCP Client for connecting to external MCP servers.

Supports stdio (subprocess) and SSE (HTTP) transports for
communicating with MCP-compatible tool/resource servers.
"""

import asyncio
import json
import logging
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for connecting to external MCP servers.

    Discovers tools, resources, and prompts from remote MCP servers
    and invokes them. Supports conversion to OpenAI function format
    for seamless LLM integration.

    Args:
        server_name: Identifier for this server connection.
        transport: Transport type ("stdio" or "sse").
        **kwargs: Transport-specific configuration.
            For stdio: command (str), args (list[str]), env (dict).
            For sse: base_url (str), api_key (str|None).
    """

    def __init__(self, server_name: str, transport: str = "stdio", **kwargs):
        self.server_name = server_name
        self.transport = transport
        self.config = kwargs

        # State
        self._connected = False
        self._process: subprocess.Popen | None = None
        self._tools: list[dict] = []
        self._resources: list[dict] = []
        self._prompts: list[dict] = []
        self._capabilities: dict = {}
        self._request_id = 0

        # For SSE transport
        self._http_client = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Establish connection to the MCP server.

        For stdio: launches the subprocess.
        For sse: verifies the HTTP endpoint.
        Sends initialize request and discovers capabilities.
        """
        if self._connected:
            return

        if self.transport == "stdio":
            await self._connect_stdio()
        elif self.transport == "sse":
            await self._connect_sse()
        else:
            raise ValueError(f"Unsupported transport: {self.transport}")

        # Initialize
        await self._initialize()

        # Discover tools
        await self.discover_tools()

        self._connected = True
        logger.info(
            "Connected to MCP server '%s' (transport=%s, tools=%d)",
            self.server_name, self.transport, len(self._tools),
        )

    async def _connect_stdio(self) -> None:
        """Connect via subprocess stdio."""
        command = self.config.get("command", "")
        if not command:
            raise ValueError("stdio transport requires 'command' in config.")

        args = self.config.get("args", [])

        try:
            self._process = await asyncio.create_subprocess_exec(
                command,
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            raise RuntimeError(f"MCP server command not found: {command}")
        except Exception as e:
            raise RuntimeError(f"Failed to start MCP server: {e}")

        logger.info("Launched MCP stdio server: %s %s", command, " ".join(args))

    async def _connect_sse(self) -> None:
        """Connect via SSE (HTTP)."""
        import httpx

        base_url = self.config.get("base_url", "http://localhost:8000")
        self._base_url = base_url.rstrip("/")

        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.config['api_key']}"}
                   if self.config.get("api_key") else {}),
            },
        )

        # Verify connectivity
        try:
            response = await self._http_client.get(f"{self._base_url}/health")
            response.raise_for_status()
        except Exception as e:
            await self._http_client.aclose()
            raise RuntimeError(f"Failed to connect to MCP SSE server: {e}")

    # ------------------------------------------------------------------
    # Initialize
    # ------------------------------------------------------------------

    async def _initialize(self) -> None:
        """Send initialize request to get server capabilities."""
        result = await self._send_request("initialize", {
            "protocolVersion": "0.1.0",
            "clientInfo": {
                "name": "mcp-client",
                "version": "1.0.0",
            },
        })

        if result:
            self._capabilities = result.get("capabilities", {})

        # Send initialized notification
        await self._send_notification("notifications/initialized", {})

    # ------------------------------------------------------------------
    # Tool discovery & invocation
    # ------------------------------------------------------------------

    async def discover_tools(self) -> list[dict]:
        """Discover and cache available tools from the server.

        Returns:
            List of tool definition dicts.
        """
        result = await self._send_request("tools/list", {})
        if result and "tools" in result:
            self._tools = result["tools"]
        return self._tools

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """Call a tool on the remote MCP server.

        Args:
            name: The tool name.
            arguments: Tool arguments dict.

        Returns:
            Tool result dict with content and isError fields.

        Raises:
            RuntimeError: If the tool call fails.
        """
        result = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments,
        })

        if result is None:
            raise RuntimeError(f"Tool call '{name}' returned no result.")

        if result.get("isError"):
            content = result.get("content", [])
            error_text = content[0].get("text", "Unknown error") if content else "Unknown error"
            raise RuntimeError(f"Tool '{name}' failed: {error_text}")

        return result

    # ------------------------------------------------------------------
    # Resources
    # ------------------------------------------------------------------

    async def list_resources(self) -> list[dict]:
        """List available resources from the server.

        Returns:
            List of resource definition dicts.
        """
        result = await self._send_request("resources/list", {})
        if result and "resources" in result:
            self._resources = result["resources"]
        return self._resources

    async def read_resource(self, uri: str) -> dict:
        """Read a resource by URI.

        Args:
            uri: The resource URI.

        Returns:
            Resource content dict.
        """
        result = await self._send_request("resources/read", {"uri": uri})
        return result or {}

    # ------------------------------------------------------------------
    # Prompts
    # ------------------------------------------------------------------

    async def list_prompts(self) -> list[dict]:
        """List available prompts.

        Returns:
            List of prompt definition dicts.
        """
        result = await self._send_request("prompts/list", {})
        if result and "prompts" in result:
            self._prompts = result["prompts"]
        return self._prompts

    async def get_prompt(self, name: str, arguments: dict | None = None) -> dict:
        """Get a prompt template with arguments.

        Args:
            name: Prompt name.
            arguments: Template arguments.

        Returns:
            Prompt messages dict.
        """
        result = await self._send_request("prompts/get", {
            "name": name,
            "arguments": arguments or {},
        })
        return result or {}

    # ------------------------------------------------------------------
    # OpenAI format conversion
    # ------------------------------------------------------------------

    def to_openai_tools(self, prefix: str = "") -> list[dict]:
        """Convert MCP tools to OpenAI-compatible function call format.

        Args:
            prefix: Optional prefix to add to tool names (e.g., "mcp_").

        Returns:
            List of dicts suitable for OpenAI's tools parameter.
        """
        openai_tools = []
        for tool in self._tools:
            input_schema = tool.get("inputSchema", {})
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": f"{prefix}{tool['name']}",
                    "description": tool.get("description", ""),
                    "parameters": {
                        "type": "object",
                        "properties": input_schema.get("properties", {}),
                        "required": input_schema.get("required", []),
                    },
                },
            })
        return openai_tools

    # ------------------------------------------------------------------
    # Low-level request/response
    # ------------------------------------------------------------------

    async def _send_request(self, method: str, params: dict) -> dict | None:
        """Send a JSON-RPC 2.0 request and return the result.

        Args:
            method: RPC method name.
            params: Method parameters dict.

        Returns:
            Result dict or None on failure.
        """
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        if self.transport == "stdio":
            return await self._send_stdio(request)
        elif self.transport == "sse":
            return await self._send_sse(request)
        return None

    async def _send_notification(self, method: str, params: dict) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        if self.transport == "stdio":
            await self._send_stdio(request, expect_response=False)
        elif self.transport == "sse":
            await self._send_sse(request, expect_response=False)

    async def _send_stdio(self, request: dict, expect_response: bool = True) -> dict | None:
        """Send a request via stdio to the subprocess."""
        if not self._process or not self._process.stdin:
            raise RuntimeError("Not connected to stdio MCP server.")

        request_line = json.dumps(request, ensure_ascii=False) + "\n"
        self._process.stdin.write(request_line.encode("utf-8"))
        await self._process.stdin.drain()

        if not expect_response:
            return None

        # Read response
        if not self._process.stdout:
            return None

        try:
            response_line = await asyncio.wait_for(
                self._process.stdout.readline(),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for MCP response: %s", request.get("method"))
            return None

        if not response_line:
            return None

        try:
            response = json.loads(response_line.decode("utf-8").strip())
        except json.JSONDecodeError:
            logger.error("Invalid JSON response from MCP server")
            return None

        if "error" in response:
            error = response["error"]
            logger.error("MCP error: %s (code=%d)", error.get("message", ""), error.get("code", 0))
            return None

        return response.get("result")

    async def _send_sse(self, request: dict, expect_response: bool = True) -> dict | None:
        """Send a request via HTTP to the SSE server."""
        if not self._http_client:
            raise RuntimeError("Not connected to SSE MCP server.")

        try:
            response = await self._http_client.post(
                f"{self._base_url}/message",
                json=request,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.error("SSE request failed: %s", e)
            return None

        if not expect_response:
            return None

        if "error" in data:
            error = data["error"]
            logger.error("MCP error: %s (code=%d)", error.get("message", ""), error.get("code", 0))
            return None

        return data.get("result")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the connection and clean up resources."""
        self._connected = False

        if self.transport == "stdio" and self._process:
            # Send shutdown notification
            try:
                await self._send_notification("shutdown", {})
            except Exception:
                pass

            try:
                self._process.stdin.close()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except Exception:
                self._process.kill()
                await self._process.wait()

            self._process = None

        if self.transport == "sse" and self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        logger.info("Disconnected from MCP server '%s'.", self.server_name)

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.close()

    def __repr__(self) -> str:
        return (
            f"MCPClient(server={self.server_name!r}, transport={self.transport}, "
            f"connected={self._connected})"
        )
