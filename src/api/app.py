"""FastAPI 应用工厂，支持弹性启动和生命周期管理。"""

import os
import signal
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

logger = __import__("logging").getLogger(__name__)

# Global handles for graceful shutdown
_db_engine = None
_redis_pool = None


async def _try_init(name: str, coro):
    """Try an init step; log and continue on failure (resilient startup)."""
    try:
        await coro
        logger.info("[init] %s: OK", name)
    except Exception as exc:
        logger.warning("[init] %s: SKIPPED (%s: %s)", name, type(exc).__name__, exc)


async def _init_database(app: FastAPI):
    global _db_engine
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://llm:llm@localhost:5432/llm_platform")
    _db_engine = create_async_engine(
        db_url, pool_size=20, max_overflow=10, pool_pre_ping=True, pool_recycle=3600, echo=False,
    )
    app.state.db_session_factory = async_sessionmaker(_db_engine, expire_on_commit=False)

    # Create tables if they don't exist (MVP: no alembic migration yet).
    # Tables include tenants, users, api_keys, conversations, documents,
    # prompt_templates, request_logs, model_registry.
    from src.repositories.models.base import Base
    async with _db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured (create_all)")

    # Seed a demo tenant + API key so authenticated endpoints work out-of-the-box.
    await _seed_demo_data(app)


async def _seed_demo_data(app: FastAPI):
    """Seed a demo tenant and API key for out-of-the-box authenticated access."""
    try:
        from sqlalchemy import select
        from src.repositories.models.tenant import Tenant
        from src.repositories.models.api_key import APIKey
        from src.security.auth import hash_api_key
        from src.infrastructure.config import load_settings

        load_settings()  # ensure settings are loaded for hash_api_key

        session_factory = app.state.db_session_factory
        async with session_factory() as session:
            # Check if a demo tenant already exists
            existing = await session.execute(
                select(Tenant).where(Tenant.slug == "demo").limit(1)
            )
            if existing.scalar_one_or_none() is None:
                tenant = Tenant(name="Demo Tenant", slug="demo", tier="enterprise")
                session.add(tenant)
                await session.flush()  # get tenant.id

                # Seed a demo API key: plaintext "llm-demo-key"
                demo_key = "llm-demo-key"
                api_key = APIKey(
                    tenant_id=tenant.id,
                    key_hash=hash_api_key(demo_key),
                    key_prefix=demo_key[:8],
                    name="Demo Key",
                    scopes=["read:all", "write:all"],
                )
                session.add(api_key)
                await session.commit()
                logger.info("Seeded demo tenant + API key (use X-API-Key: llm-demo-key)")
            else:
                logger.info("Demo tenant already exists, skipping seed")
    except Exception as exc:  # noqa: BLE001 - seed is best-effort
        logger.warning("Demo seed skipped: %s", exc)


async def _init_redis(app: FastAPI):
    global _redis_pool
    import redis.asyncio as aioredis

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    _redis_pool = aioredis.ConnectionPool.from_url(
        redis_url, max_connections=50, decode_responses=True,
    )
    client = aioredis.Redis(connection_pool=_redis_pool)
    # Only publish the client to app.state after a successful ping, so that
    # dependency injection (`get_redis`) can cleanly report 503 when Redis is
    # unavailable instead of handing out a broken client.
    await client.ping()
    app.state.redis = client


async def _init_token_counter(app: FastAPI):
    from src.domain.token_management.counter import TokenCounter
    app.state.token_counter = TokenCounter()


async def _init_deepseek_client(app: FastAPI):
    """Initialize a simple DeepSeek client for direct API calls, plus a
    LangChain-compatible DeepSeekLLM for agent / RAG generation."""
    import httpx, os
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        logger.warning("DEEPSEEK_API_KEY not set, chat will not work")
        app.state.deepseek_client = None
        app.state.llm = None
        return
    app.state.deepseek_client = httpx.AsyncClient(
        base_url="https://api.deepseek.com",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=60.0,
    )
    # LangChain-compatible LLM adapter (agent + RAG generation)
    from src.infrastructure.deepseek_llm import DeepSeekLLM
    app.state.llm = DeepSeekLLM(model="deepseek-chat")
    logger.info("DeepSeek client + LLM adapter initialized")


async def _init_document_generator(app: FastAPI):
    """Initialize the document generation service (md/docx/xlsx/pptx download)."""
    from src.services.document_generator import DocumentGenerator
    from src.services.ocr_service import OCRService
    from src.services.conversation_memory import ConversationMemory

    app.state.document_generator = DocumentGenerator(llm=getattr(app.state, "llm", None))
    app.state.ocr_service = OCRService(vision_llm=None)
    app.state.conversation_memory = ConversationMemory(llm=getattr(app.state, "llm", None))
    logger.info(
        "Document generator initialized (formats=%s, ocr=%s)",
        app.state.document_generator.supported_formats(),
        app.state.ocr_service.engine_status(),
    )


async def _init_agent_executor(app: FastAPI):
    """Initialize the unified AgentExecutor and ToolRegistry.

    The executor bridges the four agent patterns (ReAct / PlanExecute /
    ReWOO / Reflection) behind a single execute() contract. The tool
    registry is populated with the built-in tools (calculator, search, etc.).
    """
    from src.agents.tools.registry import ToolRegistry
    from src.agents.executor import AgentExecutor
    from src.agents.tools.builtins import (
        WebSearchTool,
        CalculatorTool,
        WebFetchTool,
    )

    tool_registry = ToolRegistry()
    for tool in (WebSearchTool(), CalculatorTool(), WebFetchTool()):
        try:
            tool_registry.register(tool)
        except Exception as exc:  # noqa: BLE001 - resilient startup
            logger.warning("Failed to register tool %s: %s", tool.definition.name, exc)

    app.state.tool_registry = tool_registry
    app.state.agent_executor = AgentExecutor(tool_registry=tool_registry)


async def _init_mcp_tools(app: FastAPI):
    """Initialize MCP server with built-in tools (CLI / document / OCR) and
    the approval gate + business-expert registry."""
    from src.mcp.server.server import MCPServer
    from src.mcp.approval import ApprovalGate
    from src.mcp.tools import CLITool, DocumentTool, OCRTool
    from src.agents.expert_registry import ExpertRegistry
    from src.services.document_generator import DocumentGenerator
    from src.services.ocr_service import OCRService

    # Approval gate (每次授权)
    approval_gate = ApprovalGate(timeout_seconds=300)
    app.state.approval_gate = approval_gate

    # Built-in MCP tools (reuse services initialized earlier)
    document_generator = getattr(app.state, "document_generator", None) or DocumentGenerator(llm=getattr(app.state, "llm", None))
    ocr_service = getattr(app.state, "ocr_service", None) or OCRService(vision_llm=None)
    cli_tool = CLITool()
    doc_tool = DocumentTool(generator=document_generator)
    ocr_tool = OCRTool(ocr_service=ocr_service)

    mcp_server = MCPServer(name="llm-platform", version="1.0.0")
    for tool in (cli_tool, doc_tool, ocr_tool):
        mcp_server.register_tool(tool)

    # Approval hook: CLI tool requires approval (already requires_approval=True,
    # enforced in the expert/tool execution path via approval_gate)
    app.state.mcp_server = mcp_server
    app.state.approval_gate = approval_gate

    # Business expert registry (roles + prompt + skills + MCP tools)
    tools_by_name = {
        tool.definition.name: tool
        for tool in (cli_tool, doc_tool, ocr_tool)
    }
    # Also expose the agent tool registry tools
    for tool in app.state.tool_registry.list_all():
        tools_by_name[tool.name] = app.state.tool_registry.get_tool(tool.name)

    app.state.expert_registry = ExpertRegistry(
        llm=getattr(app.state, "llm", None),
        tools=tools_by_name,
        approval_gate=approval_gate,
    )
    logger.info("MCP tools initialized: %s", list(tools_by_name.keys()))


async def _init_rag_pipeline(app: FastAPI):
    """Initialize a real RAG pipeline backed by a vector store + LLM.

    Uses the InMemoryVectorStore (works without Milvus) with a hash-based
    embedder fallback, and a DeepSeek LLM adapter when a key is present.
    The Milvus/BGE-M3 wiring is enabled in M2's docker profile.
    """
    from src.rag.pipeline import RAGPipeline
    from src.rag.indexing.vector_store import InMemoryVectorStore
    from src.rag.embedding.registry import EmbeddingRegistry
    from src.infrastructure.deepseek_llm import DeepSeekLLM

    vector_store = InMemoryVectorStore()

    # Primary embedder: bge-small-zh-v1.5 (512d, ~95MB, strong for Chinese).
    # The heavier BGE-M3 (1024d multilingual) can be enabled by switching the
    # model key when its weights are downloadable.
    try:
        import importlib.util
        if importlib.util.find_spec("sentence_transformers") is None:
            raise ImportError("sentence_transformers not installed")
        embedder = EmbeddingRegistry().get_embedder("bge-small-zh-v1.5")
        if getattr(embedder, "_model", None) is None:
            raise RuntimeError("embedding model failed to load")
        logger.info("Using bge-small-zh-v1.5 embedder (dim=%d)", embedder.dim)
    except Exception as exc:  # noqa: BLE001 - model download may be unavailable
        logger.warning("Embedding model unavailable (%s); using hash embedder", exc)
        embedder = _HashEmbedder(dim=512)

    # DeepSeek LLM for generation (optional — extractive fallback if no key).
    llm = None
    if app.state.deepseek_client is not None:
        try:
            llm = DeepSeekLLM(model="deepseek-chat")
        except Exception as exc:  # noqa: BLE001
            logger.warning("DeepSeek LLM adapter failed: %s", exc)

    app.state.rag_pipeline = RAGPipeline(
        vector_store=vector_store,
        embedder=embedder,
        llm=llm,
    )


class _HashEmbedder:
    """Deterministic hash-based embedder (fallback when BGE-M3 unavailable)."""

    def __init__(self, dim: int = 1024):
        self._dim = dim
        self.name = "hash-embedder"

    async def embed(self, texts: list[str]):
        import hashlib
        import numpy as np
        out = []
        for text in texts:
            vec = np.zeros(self._dim, dtype=float)
            for token in text.lower().split():
                h = int(hashlib.md5(token.encode()).hexdigest(), 16)
                vec[h % self._dim] += 1.0
            norm = np.linalg.norm(vec)
            out.append(vec / norm if norm > 0 else vec)
        return out

    async def embed_query(self, query: str):
        return (await self.embed([query]))[0]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    logger.info("Starting LLM Platform v1.0.0")

    await _try_init("database", _init_database(app))
    await _try_init("redis", _init_redis(app))
    await _try_init("token_counter", _init_token_counter(app))
    await _try_init("deepseek_client", _init_deepseek_client(app))
    await _try_init("agent_executor", _init_agent_executor(app))
    await _try_init("rag_pipeline", _init_rag_pipeline(app))
    await _try_init("document_generator", _init_document_generator(app))
    await _try_init("mcp_tools", _init_mcp_tools(app))

    logger.info("LLM Platform started (some services may be deferred)")
    yield
    # ── Shutdown ──
    logger.info("Shutting down LLM Platform")
    global _db_engine
    if _db_engine:
        await _db_engine.dispose()
    redis_client = getattr(app.state, "redis", None)
    if redis_client:
        await redis_client.aclose()
    logger.info("LLM Platform shut down complete")


def create_app(settings=None) -> FastAPI:
    app = FastAPI(
        title="LLM Platform - 企业级 AI 应用平台",
        description="企业级 AI 应用平台：AI 网关、RAG 知识库、Agent 智能体、MCP 集成、Prompt 工程管理",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    from src.api.routes.health_routes import router as health_router
    app.include_router(health_router)

    try:
        from src.api.routes.gateway_routes import router as gateway_router
        app.include_router(gateway_router)
    except Exception as e:
        logger.warning("Gateway routes not loaded: %s", e)

    try:
        from src.api.routes.rag_routes import router as rag_router
        app.include_router(rag_router)
    except Exception as e:
        logger.warning("RAG routes not loaded: %s", e)

    try:
        from src.api.routes.agent_routes import router as agent_router
        app.include_router(agent_router)
    except Exception as e:
        logger.warning("Agent routes not loaded: %s", e)

    try:
        from src.api.routes.prompt_routes import router as prompt_router
        app.include_router(prompt_router)
    except Exception as e:
        logger.warning("Prompt routes not loaded: %s", e)

    try:
        from src.api.routes.mcp_routes import router as mcp_router
        app.include_router(mcp_router)
    except Exception as e:
        logger.warning("MCP routes not loaded: %s", e)

    try:
        from src.api.routes.admin_routes import router as admin_router
        app.include_router(admin_router)
    except Exception as e:
        logger.warning("Admin routes not loaded: %s", e)

    try:
        from src.api.routes.document_routes import router as document_router
        app.include_router(document_router)
    except Exception as e:
        logger.warning("Document routes not loaded: %s", e)

    try:
        from src.api.routes.expert_routes import router as expert_router
        app.include_router(expert_router)
    except Exception as e:
        logger.warning("Expert routes not loaded: %s", e)

    if settings:
        app.state.settings = settings

    # Add simple real chat endpoint that bypasses complex gateway
    from pydantic import BaseModel as PydanticBase
    class SimpleChatRequest(PydanticBase):
        model: str = "deepseek-chat"
        messages: list[dict] = []
        max_tokens: int = 2048
        temperature: float = 0.7
        stream: bool = False

    @app.post("/v1/chat/completions")
    async def simple_chat(req: SimpleChatRequest):
        client = getattr(app.state, "deepseek_client", None)
        if not client:
            raise HTTPException(503, "DeepSeek client not initialized")
        clean_messages = [{"role": m.get("role","user"), "content": str(m.get("content",""))} for m in req.messages if m.get("content")]
        body = {"model": req.model or "deepseek-chat", "messages": clean_messages, "max_tokens": req.max_tokens, "temperature": req.temperature}
        if req.stream:
            async def generate():
                async with client.stream("POST", "/v1/chat/completions", json={**body, "stream": True}) as resp:
                    async for chunk in resp.aiter_bytes():
                        yield chunk
            return StreamingResponse(generate(), media_type="text/event-stream")
        r = await client.post("/v1/chat/completions", json=body)
        if r.status_code != 200:
            raise HTTPException(r.status_code, detail=r.text[:500])
        return r.json()

    # Memory-aware chat endpoint: retains conversation state + compresses
    # older turns into a summary so key facts survive context truncation.
    class MemoryChatRequest(PydanticBase):
        conversation_id: str = "default"
        message: str = ""
        model: str = "deepseek-chat"

    @app.post("/v1/chat/memory")
    async def memory_chat(req: MemoryChatRequest):
        llm = getattr(app.state, "llm", None)
        if not llm:
            raise HTTPException(503, "LLM not initialized (DEEPSEEK_API_KEY required)")
        memory: "ConversationMemory" = app.state.conversation_memory

        # Add user message to memory
        memory.add_message(req.conversation_id, "user", req.message)

        # Build context (summary + recent STM)
        context = await memory.build_context(req.conversation_id)

        # Generate reply
        try:
            response = await llm.ainvoke(context)
            reply = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            raise HTTPException(500, f"LLM generation failed: {e}")

        # Add assistant reply to memory
        memory.add_message(req.conversation_id, "assistant", reply)

        return {
            "conversation_id": req.conversation_id,
            "reply": reply,
            "memory_state": memory.get_state(req.conversation_id).to_dict(),
        }

    @app.get("/v1/chat/memory/{conversation_id}")
    async def get_memory_state(conversation_id: str):
        memory: "ConversationMemory" = getattr(app.state, "conversation_memory", None)
        if not memory:
            return {"error": "memory not initialized"}
        return memory.get_state(conversation_id).to_dict()

    # Sync-only endpoint: record a message into conversation memory WITHOUT
    # generating a reply. Used by the streaming chat frontend to keep the
    # backend memory (STM + compression) in sync while the LLM reply is
    # streamed through the existing /v1/chat/completions endpoint.
    class MemorySyncRequest(PydanticBase):
        conversation_id: str = "default"
        role: str = "user"  # user | assistant
        content: str = ""

    @app.post("/v1/chat/memory/sync")
    async def sync_memory(req: MemorySyncRequest):
        memory: "ConversationMemory" = getattr(app.state, "conversation_memory", None)
        if not memory:
            raise HTTPException(503, "memory not initialized")

        memory.add_message(req.conversation_id, req.role, req.content)
        # Trigger compression check (async) so key facts are summarized before
        # the next turn rather than silently dropped.
        await memory.build_context(req.conversation_id)

        return {
            "conversation_id": req.conversation_id,
            "memory_state": memory.get_state(req.conversation_id).to_dict(),
        }

    @app.post("/v1/rag/parse")
    async def parse_document(file: UploadFile):
        """解析 PDF/DOCX 文件为文本"""
        try:
            content = await file.read()
            ext = file.filename.split('.')[-1].lower() if file.filename else ''
            text = ''
            if ext == 'pdf':
                try:
                    import pdfplumber, io
                    with pdfplumber.open(io.BytesIO(content)) as pdf:
                        text = '\n'.join(p.extract_text() or '' for p in pdf.pages)
                except: pass
            elif ext in ('docx', 'doc'):
                try:
                    import docx, io
                    doc = docx.Document(io.BytesIO(content))
                    text = '\n'.join(p.text for p in doc.paragraphs)
                except: pass
            if not text:
                text = content.decode('utf-8', errors='ignore')[:100000]
            return {"text": text[:50000], "filename": file.filename}
        except Exception as e:
            raise HTTPException(500, str(e))

    return app


# Module-level app instance for uvicorn/gunicorn discovery
app = create_app()
