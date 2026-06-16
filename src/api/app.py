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


async def _init_redis(app: FastAPI):
    global _redis_pool
    import redis.asyncio as aioredis

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    _redis_pool = aioredis.ConnectionPool.from_url(
        redis_url, max_connections=50, decode_responses=True,
    )
    app.state.redis = aioredis.Redis(connection_pool=_redis_pool)
    await app.state.redis.ping()


async def _init_token_counter(app: FastAPI):
    from src.token_management.counter import TokenCounter
    app.state.token_counter = TokenCounter()


async def _init_deepseek_client(app: FastAPI):
    """Initialize a simple DeepSeek client for direct API calls."""
    import httpx, os
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        logger.warning("DEEPSEEK_API_KEY not set, chat will not work")
        app.state.deepseek_client = None
        return
    app.state.deepseek_client = httpx.AsyncClient(
        base_url="https://api.deepseek.com",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=60.0,
    )
    logger.info("DeepSeek client initialized")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    logger.info("Starting LLM Platform v1.0.0")

    await _try_init("database", _init_database(app))
    await _try_init("redis", _init_redis(app))
    await _try_init("token_counter", _init_token_counter(app))
    await _try_init("deepseek_client", _init_deepseek_client(app))

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
