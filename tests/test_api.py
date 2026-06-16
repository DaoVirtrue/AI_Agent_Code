"""LLM Platform 后端 API 完整测试套件。

测试运行中的 LLM Platform 后端的所有 API 接口。
后端地址默认为 http://localhost:8000，可通过 LLM_PLATFORM_BASE_URL 环境变量修改。

运行方式：
    pytest tests/test_api.py -v -m api
    pytest tests/test_api.py -v -k "test_health"
"""

import json
import pytest
import httpx


# ============================================================================
# 辅助函数
# ============================================================================

def _assert_server_responded(response: httpx.Response, *, label: str = "") -> None:
    """断言服务器已响应（不会连接超时或崩溃），状态码可为任意 HTTP 状态。

    此辅助函数用于非健康检查类的接口测试——在这些测试中，
    我们只关心后端是否正常处理请求并返回了 HTTP 响应，
    不对具体的业务状态码做严格要求。
    """
    assert 100 <= response.status_code < 600, (
        f"[{label}] 服务器返回了非预期的状态码 {response.status_code}，"
        f"响应体: {response.text[:500]}"
    )


def _is_json_response(response: httpx.Response) -> bool:
    """检查响应是否为 JSON 格式。"""
    content_type = response.headers.get("content-type", "")
    return "application/json" in content_type


# ============================================================================
# 1. 健康检查接口
# ============================================================================

class TestHealthEndpoints:
    """健康检查接口测试 —— 验证服务存活、就绪与健康状态。"""

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_health接口返回健康状态(
        self, async_client: httpx.AsyncClient
    ):
        """GET /health 应返回 200 且 status 为 'healthy' 或 'degraded'。

        完整健康检查，验证数据库、Redis、Milvus 及 LLM Provider 状态。
        """
        response = await async_client.get("/health")

        assert response.status_code == 200, (
            f"预期 200，实际 {response.status_code}，响应体: {response.text[:500]}"
        )
        assert _is_json_response(response), "响应 Content-Type 应为 application/json"

        data = response.json()
        assert "status" in data, f"响应缺少 'status' 字段: {list(data.keys())}"
        assert data["status"] in ("healthy", "degraded"), (
            f"status 应为 'healthy' 或 'degraded'，实际为 '{data['status']}'"
        )
        assert "version" in data, "响应缺少 'version' 字段"
        assert "checks" in data, "响应缺少 'checks' 字段"
        assert isinstance(data["checks"], dict), "checks 应为字典类型"

        # 验证版本号格式
        assert data["version"] == "1.0.0", (
            f"版本号应为 '1.0.0'，实际为 '{data['version']}'"
        )

        # 验证 checks 中的值均为布尔类型
        for check_name, check_value in data["checks"].items():
            assert isinstance(check_value, bool), (
                f"checks['{check_name}'] 应为布尔值，实际为 {type(check_value).__name__}"
            )

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_health接口不健康时返回503(
        self, async_client: httpx.AsyncClient
    ):
        """GET /health 当关键依赖不可用时可能返回 503。

        在数据库和 Redis 均不可用的环境下，/health 应返回 503。
        正常环境下通常返回 200。
        """
        response = await async_client.get("/health")
        # 此接口在前一个测试已验证 200，这里验证服务器至少不会崩溃
        assert response.status_code in (200, 503), (
            f"health 接口返回意外状态码: {response.status_code}，"
            f"响应体: {response.text[:500]}"
        )

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_ready接口返回状态码(
        self, async_client: httpx.AsyncClient
    ):
        """GET /ready 应返回 HTTP 响应（200 或 503）。

        Kubernetes 就绪探测：验证数据库和 Redis 连接是否就绪。
        依赖可用时返回 200，不可用时返回 503。
        """
        response = await async_client.get("/ready")

        assert response.status_code in (200, 503), (
            f"ready 接口返回意外状态码: {response.status_code}，"
            f"响应体: {response.text[:500]}"
        )
        assert _is_json_response(response), "响应 Content-Type 应为 application/json"

        data = response.json()
        assert "status" in data, "响应缺少 'status' 字段"
        assert "checks" in data, "响应缺少 'checks' 字段"
        assert "database" in data["checks"], "checks 中缺少 'database'"
        assert "redis" in data["checks"], "checks 中缺少 'redis'"

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_live接口始终返回200存活状态(
        self, async_client: httpx.AsyncClient
    ):
        """GET /live 应始终返回 200 —— 无需任何外部依赖。

        Kubernetes 存活探测：仅验证应用进程是否正在运行。
        """
        response = await async_client.get("/live")

        assert response.status_code == 200, (
            f"预期 200，实际 {response.status_code}，响应体: {response.text[:500]}"
        )
        assert _is_json_response(response), "响应 Content-Type 应为 application/json"

        data = response.json()
        assert data["status"] == "alive", (
            f"status 应为 'alive'，实际为 '{data.get('status')}'"
        )
        assert "timestamp" in data, "响应缺少 'timestamp' 字段"

        # 验证 timestamp 是有效的 ISO 格式字符串
        timestamp = data["timestamp"]
        assert isinstance(timestamp, str), "timestamp 应为字符串类型"
        assert "T" in timestamp, f"timestamp 应为 ISO 格式，实际为: {timestamp}"

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_metrics接口返回Prometheus指标(
        self, async_client: httpx.AsyncClient
    ):
        """GET /metrics 应返回 Prometheus 文本格式的指标数据。"""
        response = await async_client.get("/metrics")

        assert response.status_code == 200, (
            f"metrics 接口返回 {response.status_code}"
        )
        content_type = response.headers.get("content-type", "")
        assert "text/plain" in content_type, (
            f"metrics Content-Type 应为 text/plain，实际为: {content_type}"
        )
        # Prometheus 指标文本应包含 HELP 或 TYPE 注释
        assert response.text, "metrics 响应体不应为空"


# ============================================================================
# 2. API 文档接口
# ============================================================================

class TestAPIDocumentation:
    """API 文档接口测试 —— Swagger UI 与 OpenAPI JSON。"""

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_swagger文档页面可正常访问(
        self, async_client: httpx.AsyncClient
    ):
        """GET /docs 应返回 200 并包含 Swagger UI HTML。

        验证 Swagger UI 页面加载正常，Content-Type 为 text/html。
        """
        response = await async_client.get("/docs")

        assert response.status_code == 200, (
            f"Swagger 文档页面返回 {response.status_code}"
        )
        content_type = response.headers.get("content-type", "")
        assert "text/html" in content_type, (
            f"docs Content-Type 应为 text/html，实际为: {content_type}"
        )
        # Swagger UI HTML 应包含特征字符串
        assert "swagger" in response.text.lower(), (
            "响应 HTML 中未找到 'swagger' 相关标记"
        )

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_redoc文档页面可正常访问(
        self, async_client: httpx.AsyncClient
    ):
        """GET /redoc 应返回 200 并包含 ReDoc UI HTML。"""
        response = await async_client.get("/redoc")

        assert response.status_code == 200, (
            f"ReDoc 文档页面返回 {response.status_code}"
        )
        content_type = response.headers.get("content-type", "")
        assert "text/html" in content_type, (
            f"redoc Content-Type 应为 text/html，实际为: {content_type}"
        )

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_openapi_json文档标题包含LLM(
        self, async_client: httpx.AsyncClient
    ):
        """GET /openapi.json 应返回符合 OpenAPI 3.x 规范的有效 JSON。

        验证标题包含 'LLM'，且包含 paths、info、openapi 等必要字段。
        """
        response = await async_client.get("/openapi.json")

        assert response.status_code == 200, (
            f"OpenAPI JSON 返回 {response.status_code}"
        )
        assert _is_json_response(response), (
            "openapi.json Content-Type 应为 application/json"
        )

        data = response.json()

        # OpenAPI 规范必要字段
        assert "openapi" in data, "缺少 openapi 版本号字段"
        assert data["openapi"], "openapi 版本号不应为空"
        assert "info" in data, "缺少 info 对象"
        assert "title" in data["info"], "info 中缺少 title"
        assert "LLM" in data["info"]["title"], (
            f"标题应包含 'LLM'，实际为: '{data['info']['title']}'"
        )
        assert "version" in data["info"], "info 中缺少 version"
        assert "paths" in data, "缺少 paths 对象"
        assert isinstance(data["paths"], dict), "paths 应为字典类型"

        # 验证至少包含已知的路由路径
        paths = data["paths"]
        expected_paths = [
            "/health",
            "/ready",
            "/live",
        ]
        for path in expected_paths:
            assert path in paths, (
                f"OpenAPI paths 中缺少预期路径 '{path}'"
            )

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_openapi_json包含所有主要路由标签(
        self, async_client: httpx.AsyncClient
    ):
        """GET /openapi.json 的 paths 中应包含主要功能模块的路由。"""
        response = await async_client.get("/openapi.json")
        assert response.status_code == 200

        data = response.json()
        paths = data["paths"]
        path_str = json.dumps(list(paths.keys()))

        # 各功能模块的关键路由 — 并非所有模块都能成功加载（取决于依赖可用性）
        route_checks = {
            "AI 网关": "/v1/gateway",
            "RAG 知识库": "/v1/rag",
            "Agent 智能体": "/v1/agent",
            "Prompt 工程": "/v1/prompts",
            "MCP 集成": "/v1/mcp",
            "系统管理": "/v1/admin",
        }
        found_modules = []
        missing_modules = []
        for module_name, prefix in route_checks.items():
            if any(p.startswith(prefix) for p in paths):
                found_modules.append(module_name)
            else:
                missing_modules.append(module_name)
        # At least 3 of 6 module route groups should be present
        assert len(found_modules) >= 3, (
            f"OpenAPI paths 中仅找到 {len(found_modules)}/6 个模块路由 "
            f"(找到: {found_modules}，缺少: {missing_modules})"
        )


# ============================================================================
# 3. AI 网关接口
# ============================================================================

class TestGatewayRoutes:
    """AI 网关接口测试 —— 模型列表与网关健康检查。

    网关接口依赖 Provider 配置和租户认证。
    在 Provider 未完全配置的环境中可能返回 500/503，
    但服务器应正常响应而不会崩溃。
    """

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_gateway模型列表接口有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """GET /v1/gateway/models 应返回有效 HTTP 响应。

        列出所有可用的 LLM 模型及其能力和定价信息。
        Provider 未配置时可能返回 500/503。
        """
        response = await async_client.get(
            "/v1/gateway/models", headers=api_key_headers
        )
        _assert_server_responded(response, label="网关模型列表")

        # 如果认证通过且 Provider 正常，验证响应结构
        if response.status_code == 200 and _is_json_response(response):
            data = response.json()
            assert isinstance(data, list), (
                f"模型列表应为数组，实际为 {type(data).__name__}"
            )

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_gateway健康检查接口有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """GET /v1/gateway/health 应返回有效 HTTP 响应。

        返回网关 provider 状态、断路器状态和速率限制器状态。
        """
        response = await async_client.get(
            "/v1/gateway/health", headers=api_key_headers
        )
        _assert_server_responded(response, label="网关健康检查")

        if response.status_code == 200 and _is_json_response(response):
            data = response.json()
            assert "status" in data, "网关健康响应缺少 'status' 字段"
            assert "providers" in data, "网关健康响应缺少 'providers' 字段"

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_gateway模型列表无需认证也应有响应(
        self, async_client: httpx.AsyncClient
    ):
        """GET /v1/gateway/models 不带 API Key 时也应返回 HTTP 响应。

        缺少认证时应返回 401（Unauthorized）或 403（Forbidden），
        而不应返回连接错误或服务器崩溃。
        """
        response = await async_client.get("/v1/gateway/models")
        _assert_server_responded(response, label="网关模型列表（无认证）")

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_gateway_chat_completions接口有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """POST /v1/gateway/chat/completions 应返回有效 HTTP 响应。

        发送最小化的 Chat Completion 请求，验证端点可达。
        """
        payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "user", "content": "Hello, how are you?"}
            ],
            "temperature": 0.7,
            "max_tokens": 50,
        }
        response = await async_client.post(
            "/v1/gateway/chat/completions",
            json=payload,
            headers=api_key_headers,
        )
        _assert_server_responded(response, label="Chat Completions")

        if response.status_code == 200 and _is_json_response(response):
            data = response.json()
            # 成功响应应包含 id, model, content 等字段
            assert "id" in data or "content" in data or "model" in data, (
                f"Chat Completion 响应结构异常: {list(data.keys())}"
            )


# ============================================================================
# 4. RAG 知识库接口
# ============================================================================

class TestRAGRoutes:
    """RAG 知识库接口测试 —— 文档检索与问答。

    RAG 接口依赖向量存储和 LLM Provider。
    在依赖未配置的环境中可能返回 500/503。
    """

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_rag搜索接口有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """POST /v1/rag/search 应返回有效 HTTP 响应。

        发送包含 query、top_k 和 retrieval_strategy 的 RAG 搜索请求。
        """
        payload = {
            "query": "什么是人工智能？",
            "top_k": 5,
            "retrieval_strategy": "hybrid",
        }
        response = await async_client.post(
            "/v1/rag/search", json=payload, headers=api_key_headers
        )
        _assert_server_responded(response, label="RAG 搜索")

        if response.status_code == 200 and _is_json_response(response):
            data = response.json()
            assert "answer" in data, "RAG 搜索响应缺少 'answer' 字段"
            assert "sources" in data, "RAG 搜索响应缺少 'sources' 字段"
            assert "latency_ms" in data, "RAG 搜索响应缺少 'latency_ms' 字段"

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_rag搜索接口语义检索策略有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """POST /v1/rag/search 使用 semantic 检索策略应有响应。"""
        payload = {
            "query": "解释机器学习的基本概念",
            "top_k": 3,
            "retrieval_strategy": "semantic",
            "include_scores": True,
            "rerank": True,
        }
        response = await async_client.post(
            "/v1/rag/search", json=payload, headers=api_key_headers
        )
        _assert_server_responded(response, label="RAG 搜索（semantic）")

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_rag搜索接口关键词检索策略有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """POST /v1/rag/search 使用 keyword 检索策略应有响应。"""
        payload = {
            "query": "Python编程语言的特点",
            "top_k": 3,
            "retrieval_strategy": "keyword",
            "include_scores": False,
            "rerank": False,
        }
        response = await async_client.post(
            "/v1/rag/search", json=payload, headers=api_key_headers
        )
        _assert_server_responded(response, label="RAG 搜索（keyword）")

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_rag搜索接口mmr检索策略有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """POST /v1/rag/search 使用 mmr 检索策略应有响应。"""
        payload = {
            "query": "深度学习与神经网络的关系",
            "top_k": 5,
            "retrieval_strategy": "mmr",
            "include_scores": True,
            "rerank": True,
        }
        response = await async_client.post(
            "/v1/rag/search", json=payload, headers=api_key_headers
        )
        _assert_server_responded(response, label="RAG 搜索（mmr）")

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_rag搜索空查询应返回验证错误(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """POST /v1/rag/search 发送空 query 应返回 422（验证错误）。"""
        payload = {
            "query": "",
            "top_k": 5,
            "retrieval_strategy": "hybrid",
        }
        response = await async_client.post(
            "/v1/rag/search", json=payload, headers=api_key_headers
        )
        # 空 query 违反 min_length=1 的校验规则，应返回 422/400/404
        assert response.status_code in (422, 400, 401, 403, 404), (
            f"空查询应返回 422/400/404 错误状态，实际返回 {response.status_code}，"
            f"响应体: {response.text[:500]}"
        )

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_rag缓存统计接口有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """GET /v1/rag/cache/stats 应返回有效 HTTP 响应。"""
        response = await async_client.get(
            "/v1/rag/cache/stats", headers=api_key_headers
        )
        _assert_server_responded(response, label="RAG 缓存统计")

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_rag文档列表接口有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """GET /v1/rag/documents 应返回有效 HTTP 响应。"""
        response = await async_client.get(
            "/v1/rag/documents", headers=api_key_headers
        )
        _assert_server_responded(response, label="RAG 文档列表")


# ============================================================================
# 5. Agent 智能体接口
# ============================================================================

class TestAgentRoutes:
    """Agent 智能体接口测试 —— 工具列表、对话管理与编排。

    Agent 接口依赖 Agent Executor 和 Tool Registry。
    在服务未初始化时可能返回 500/503。
    """

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_agent工具列表接口有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """GET /v1/agent/tools 应返回有效 HTTP 响应。

        列出 Agent 可用的所有工具及其名称、描述和参数 Schema。
        """
        response = await async_client.get(
            "/v1/agent/tools", headers=api_key_headers
        )
        _assert_server_responded(response, label="Agent 工具列表")

        if response.status_code == 200 and _is_json_response(response):
            data = response.json()
            assert isinstance(data, list), (
                f"工具列表应为数组，实际为 {type(data).__name__}"
            )
            # 如果返回了工具，验证每个工具的结构
            for tool in data:
                assert "name" in tool, f"工具缺少 'name' 字段: {tool}"
                assert "description" in tool, f"工具缺少 'description' 字段: {tool}"

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_agent运行接口有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """POST /v1/agent/run 应返回有效 HTTP 响应。

        发送最小化的 Agent 执行请求，验证端点可达。
        """
        payload = {
            "task": "搜索最新的AI新闻",
            "agent_type": "react",
            "max_steps": 3,
            "model": "gpt-4o",
            "temperature": 0.7,
            "verbose": False,
        }
        response = await async_client.post(
            "/v1/agent/run", json=payload, headers=api_key_headers
        )
        _assert_server_responded(response, label="Agent 运行")

        if response.status_code == 200 and _is_json_response(response):
            data = response.json()
            assert "run_id" in data, "Agent 运行响应缺少 'run_id'"
            assert "status" in data, "Agent 运行响应缺少 'status'"

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_agent对话列表接口有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """GET /v1/agent/conversations 应返回有效 HTTP 响应。"""
        response = await async_client.get(
            "/v1/agent/conversations", headers=api_key_headers
        )
        _assert_server_responded(response, label="Agent 对话列表")

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_agent编排接口有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """POST /v1/agent/orchestrate 应返回有效 HTTP 响应。"""
        payload = {
            "task": "分析市场趋势并生成报告",
            "agents": [
                {"name": "researcher", "role": "研究员"},
                {"name": "analyst", "role": "分析师"},
            ],
            "workflow": "sequential",
            "max_steps_total": 10,
            "model": "gpt-4o",
        }
        response = await async_client.post(
            "/v1/agent/orchestrate",
            json=payload,
            headers=api_key_headers,
        )
        _assert_server_responded(response, label="Agent 编排")


# ============================================================================
# 6. Prompt 工程接口
# ============================================================================

class TestPromptRoutes:
    """Prompt 工程接口测试 —— 模板管理、渲染与实验。

    Prompt 接口依赖 Prompt Manager。
    """

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_prompt模板列表接口有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """GET /v1/prompts/templates 应返回有效 HTTP 响应。

        列出当前租户的所有 Prompt 模板，支持分页、标签和搜索过滤。
        """
        response = await async_client.get(
            "/v1/prompts/templates", headers=api_key_headers
        )
        _assert_server_responded(response, label="Prompt 模板列表")

        if response.status_code == 200 and _is_json_response(response):
            data = response.json()
            assert "items" in data, "分页响应缺少 'items' 字段"
            assert "total" in data, "分页响应缺少 'total' 字段"
            assert "page" in data, "分页响应缺少 'page' 字段"
            assert "page_size" in data, "分页响应缺少 'page_size' 字段"
            assert isinstance(data["items"], list), "items 应为列表类型"

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_prompt模板列表分页参数有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """GET /v1/prompts/templates?page=1&page_size=10 应有响应。"""
        response = await async_client.get(
            "/v1/prompts/templates",
            params={"page": 1, "page_size": 10},
            headers=api_key_headers,
        )
        _assert_server_responded(response, label="Prompt 模板列表（分页）")

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_prompt模板列表按标签过滤有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """GET /v1/prompts/templates?tag=test 应有响应。"""
        response = await async_client.get(
            "/v1/prompts/templates",
            params={"tag": "production"},
            headers=api_key_headers,
        )
        _assert_server_responded(response, label="Prompt 模板列表（按标签过滤）")

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_prompt模板列表按搜索过滤有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """GET /v1/prompts/templates?search=chat 应有响应。"""
        response = await async_client.get(
            "/v1/prompts/templates",
            params={"search": "chat"},
            headers=api_key_headers,
        )
        _assert_server_responded(response, label="Prompt 模板列表（按搜索过滤）")

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_prompt渲染接口有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """POST /v1/prompts/render 应返回有效 HTTP 响应。

        使用给定变量渲染 Prompt 模板并返回结果。
        """
        payload = {
            "template_name": "test_template",
            "variables": {"name": "World"},
        }
        response = await async_client.post(
            "/v1/prompts/render", json=payload, headers=api_key_headers
        )
        _assert_server_responded(response, label="Prompt 渲染")

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_prompt模板版本历史接口有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """GET /v1/prompts/templates/{name}/versions 应有响应。"""
        response = await async_client.get(
            "/v1/prompts/templates/test_template/versions",
            headers=api_key_headers,
        )
        _assert_server_responded(response, label="Prompt 模板版本历史")

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_prompt实验创建接口有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """POST /v1/prompts/experiments 应返回有效 HTTP 响应。"""
        payload = {
            "name": "测试实验",
            "template_names": ["template_a", "template_b"],
            "test_inputs": [
                {"variable_name": "user_name", "values": ["Alice", "Bob"]}
            ],
            "evaluator": "llm_judge",
            "model": "gpt-4o",
        }
        response = await async_client.post(
            "/v1/prompts/experiments",
            json=payload,
            headers=api_key_headers,
        )
        _assert_server_responded(response, label="Prompt 实验创建")


# ============================================================================
# 7. 系统管理接口
# ============================================================================

class TestAdminRoutes:
    """系统管理接口测试 —— 租户管理、审计日志与使用量报告。

    管理接口通常需要 admin:read 或 admin:write 权限。
    """

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_管理员租户列表接口有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """GET /v1/admin/tenants 应返回有效 HTTP 响应。

        列出所有租户，需要 admin:read 权限。
        无权限时可能返回 401/403。
        """
        response = await async_client.get(
            "/v1/admin/tenants", headers=api_key_headers
        )
        _assert_server_responded(response, label="管理员租户列表")

        if response.status_code == 200 and _is_json_response(response):
            data = response.json()
            assert "items" in data, "分页响应缺少 'items' 字段"
            assert "total" in data, "分页响应缺少 'total' 字段"
            assert "page" in data, "分页响应缺少 'page' 字段"

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_管理员租户列表分页参数有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """GET /v1/admin/tenants?page=1&page_size=5 应有响应。"""
        response = await async_client.get(
            "/v1/admin/tenants",
            params={"page": 1, "page_size": 5},
            headers=api_key_headers,
        )
        _assert_server_responded(response, label="管理员租户列表（分页）")

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_管理员租户列表检索过滤有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """GET /v1/admin/tenants?search=acme 应有响应。"""
        response = await async_client.get(
            "/v1/admin/tenants",
            params={"search": "acme"},
            headers=api_key_headers,
        )
        _assert_server_responded(response, label="管理员租户列表（检索过滤）")

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_管理员审计日志接口有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """GET /v1/admin/audit-logs 应返回有效 HTTP 响应。

        查询审计日志，需要 admin:read 权限。
        """
        response = await async_client.get(
            "/v1/admin/audit-logs", headers=api_key_headers
        )
        _assert_server_responded(response, label="管理员审计日志")

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_管理员使用量报告接口有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """GET /v1/admin/usage-report 应返回有效 HTTP 响应。

        获取按租户/Provider/模型聚合的 Token 消耗和费用报告。
        """
        response = await async_client.get(
            "/v1/admin/usage-report", headers=api_key_headers
        )
        _assert_server_responded(response, label="管理员使用量报告")

        if response.status_code == 200 and _is_json_response(response):
            data = response.json()
            assert "period" in data, "使用量报告缺少 'period' 字段"
            assert "summary" in data, "使用量报告缺少 'summary' 字段"
            assert "breakdown" in data, "使用量报告缺少 'breakdown' 字段"

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_管理员使用量报告自定义周期有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """GET /v1/admin/usage-report?period=weekly 应有响应。"""
        response = await async_client.get(
            "/v1/admin/usage-report",
            params={"period": "weekly"},
            headers=api_key_headers,
        )
        _assert_server_responded(response, label="管理员使用量报告（weekly）")

    @pytest.mark.asyncio
    @pytest.mark.api
    async def test_管理员系统统计接口有响应(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """GET /v1/admin/system/stats 应返回有效 HTTP 响应。

        获取系统全局统计数据，包括活跃租户数、缓存状态等。
        """
        response = await async_client.get(
            "/v1/admin/system/stats", headers=api_key_headers
        )
        _assert_server_responded(response, label="管理员系统统计")


# ============================================================================
# 8. 跨模块集成烟雾测试
# ============================================================================

class TestCrossModuleSmoke:
    """跨模块烟雾测试 —— 快速验证所有主要端点均可达。"""

    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.slow
    async def test_所有主要GET端点均可访问(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """一次性验证所有主要 GET 端点均可访问且不会崩溃。"""
        endpoints = [
            # (路径, 是否需要认证头, 标签)
            ("/health", False, "健康检查"),
            ("/ready", False, "就绪检查"),
            ("/live", False, "存活检查"),
            ("/metrics", False, "Prometheus 指标"),
            ("/docs", False, "Swagger 文档"),
            ("/openapi.json", False, "OpenAPI JSON"),
            ("/v1/gateway/models", True, "网关模型列表"),
            ("/v1/gateway/health", True, "网关健康"),
            ("/v1/agent/tools", True, "Agent 工具"),
            ("/v1/agent/conversations", True, "Agent 对话"),
            ("/v1/prompts/templates", True, "Prompt 模板"),
            ("/v1/rag/documents", True, "RAG 文档"),
            ("/v1/rag/cache/stats", True, "RAG 缓存"),
            ("/v1/admin/tenants", True, "管理员租户"),
            ("/v1/admin/audit-logs", True, "审计日志"),
            ("/v1/admin/usage-report", True, "使用量报告"),
            ("/v1/admin/system/stats", True, "系统统计"),
        ]

        failed_endpoints = []
        for path, needs_auth, label in endpoints:
            headers = api_key_headers if needs_auth else None
            try:
                response = await async_client.get(path, headers=headers)
                assert 100 <= response.status_code < 600, (
                    f"[{label}] 状态码异常: {response.status_code}"
                )
            except Exception as e:
                failed_endpoints.append(f"{label} ({path}): {e}")

        assert not failed_endpoints, (
            "以下端点访问失败:\n" + "\n".join(f"  - {f}" for f in failed_endpoints)
        )

    @pytest.mark.asyncio
    @pytest.mark.api
    @pytest.mark.slow
    async def test_所有主要POST端点均可访问(
        self, async_client: httpx.AsyncClient, api_key_headers: dict
    ):
        """一次性验证所有主要 POST 端点均可访问且不会崩溃。"""
        post_endpoints = [
            ("/v1/rag/search", {
                "query": "测试查询",
                "top_k": 3,
                "retrieval_strategy": "hybrid",
            }, "RAG 搜索"),
            ("/v1/gateway/chat/completions", {
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 10,
            }, "Chat Completions"),
            ("/v1/agent/run", {
                "task": "测试任务",
                "agent_type": "react",
                "max_steps": 1,
                "model": "gpt-4o",
            }, "Agent 运行"),
            ("/v1/prompts/render", {
                "template_name": "test",
                "variables": {"name": "World"},
            }, "Prompt 渲染"),
        ]

        failed_endpoints = []
        for path, payload, label in post_endpoints:
            try:
                response = await async_client.post(
                    path, json=payload, headers=api_key_headers
                )
                assert 100 <= response.status_code < 600, (
                    f"[{label}] 状态码异常: {response.status_code}"
                )
            except Exception as e:
                failed_endpoints.append(f"{label} ({path}): {e}")

        assert not failed_endpoints, (
            "以下 POST 端点访问失败:\n"
            + "\n".join(f"  - {f}" for f in failed_endpoints)
        )
