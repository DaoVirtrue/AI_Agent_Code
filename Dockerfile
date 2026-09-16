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

# Batch 2: LLM/AI deps (core)
# NOTE: sentence-transformers (torch) is a ~2GB download that stalls on slow
# networks. The RAG pipeline gracefully falls back to a hash embedder when it
# is absent. For the full BGE semantic-retrieval path, run the backend from the
# local .venv (which already has sentence-transformers installed), or install
# it on-demand inside the container.
RUN pip install --no-cache-dir --default-timeout=120 \
    langchain>=0.3 langgraph>=0.2 langchain-openai>=0.3 langchain-community>=0.3 \
    openai>=1.60 anthropic>=0.40 \
    tiktoken>=0.8 sentencepiece>=0.2 huggingface-hub>=0.26 \
    numpy scipy

# Batch 3: Document generation/processing (light, pure-Python)
# docx/xlsx/pptx for the document-download feature; pdfplumber for PDF upload.
RUN pip install --no-cache-dir --default-timeout=120 \
    python-docx openpyxl python-pptx pdfplumber

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
