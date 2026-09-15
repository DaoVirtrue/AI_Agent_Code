FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.aliyun.com \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5

# Replace apt sources with Aliyun mirrors for faster downloads in China
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        curl libpq-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Batch 1: Core web/db deps (small, fast)
RUN pip install --no-cache-dir --default-timeout=120 \
    fastapi>=0.115 uvicorn[standard] pydantic>=2.10 pydantic-settings>=2.7 \
    sqlalchemy[asyncio]>=2.0 asyncpg>=0.30 alembic>=1.14 \
    redis>=5.0 celery>=5.4 \
    prometheus-client>=0.21 structlog>=24.4 \
    opentelemetry-api>=1.28 opentelemetry-sdk>=1.28 opentelemetry-exporter-otlp>=1.28 \
    httpx>=0.28 tenacity>=9.0 jinja2>=3.1 \
    pytest>=8.0 pytest-asyncio>=0.24 python-multipart>=0.0.18 \
    sse-starlette>=2.0 aiofiles>=24.0

# Batch 2: LLM/AI deps (core + sentence-transformers for BGE-M3 embeddings)
# NOTE: chromadb / pymilvus / FlagEmbedding / dspy / pdfplumber / python-docx
# are lazily imported with graceful fallbacks, so they are NOT in the base image.
RUN pip install --no-cache-dir --default-timeout=120 \
    langchain>=0.3 langgraph>=0.2 langchain-openai>=0.3 langchain-community>=0.3 \
    openai>=1.60 anthropic>=0.40 \
    tiktoken>=0.8 sentencepiece>=0.2 huggingface-hub>=0.26 \
    sentence-transformers>=3.3 numpy scipy

# NOTE: Document-processing libraries (pdfplumber, python-docx, dspy) are all
# lazily imported inside function bodies with graceful fallbacks, so they are
# intentionally excluded from the base image. PDF/DOCX upload parses to plain
# text (built-in) when these are absent; install them on-demand for full parsing.

COPY pyproject.toml README.md ./
COPY config ./config
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
COPY tests ./tests

RUN mkdir -p /app/uploads /app/cache /app/logs \
    && useradd --system --create-home appuser \
    && chown -R appuser:appuser /app

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
