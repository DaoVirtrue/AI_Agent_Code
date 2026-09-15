"""RAG 知识库路由：文档上传、检索、对话、评估和缓存管理。"""

import time
import uuid
import hashlib
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import (
    get_current_tenant,
    get_rag_pipeline,
    get_db,
    get_token_counter,
)
from src.api.dependencies import TenantContext
from src.api.schemas.rag import (
    RAGQueryRequest,
    RAGQueryResponse,
    DocumentUploadResponse,
    SourceDoc,
    EvalRequest,
)
from src.api.schemas.common import ErrorResponse
from src.observability.logging_setup import get_logger
from src.observability.metrics import (
    rag_cache_hits,
    rag_retrieval_latency,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/rag", tags=["RAG 知识库"])

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/html",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/json",
    "text/csv",
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post(
    "/documents/upload",
    response_model=DocumentUploadResponse,
    responses={
        201: {"description": "文档已上传并加入索引队列"},
        400: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
    },
    status_code=201,
)
async def upload_document(
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(None),
    chunk_size: int = Form(1000),
    chunk_overlap: int = Form(200),
    tenant: TenantContext = Depends(get_current_tenant),
    pipeline=Depends(get_rag_pipeline),
    db: AsyncSession = Depends(get_db),
):
    """上传文档进行 RAG 索引。

    文档经过校验、存储、分块后，索引至向量存储以供后续检索。

    支持格式：PDF、TXT、Markdown、HTML、DOCX、JSON、CSV。
    最大文件大小：50 MB。
    """
    # Validate file presence
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                code="MISSING_FILENAME",
                message="Filename is required",
            ).model_dump(),
        )

    # Validate MIME type
    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                code="UNSUPPORTED_FORMAT",
                message=f"Unsupported file type: {file.content_type}. Supported: {', '.join(sorted(ALLOWED_MIME_TYPES))}",
            ).model_dump(),
        )

    # Read file content
    content_bytes = await file.read()

    # Check file size
    if len(content_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=ErrorResponse(
                code="FILE_TOO_LARGE",
                message=f"File size {len(content_bytes)} exceeds maximum {MAX_FILE_SIZE} bytes",
            ).model_dump(),
        )

    # Compute content hash for deduplication
    content_hash = hashlib.sha256(content_bytes).hexdigest()

    # Parse metadata
    meta_dict = {}
    if metadata:
        import json
        try:
            meta_dict = json.loads(metadata)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    code="INVALID_METADATA",
                    message="Metadata must be valid JSON",
                ).model_dump(),
            )

    # Generate document ID
    document_id = f"doc-{uuid.uuid4().hex[:12]}"

    try:
        # Process and index the document
        result = await pipeline.index_document(
            document_id=document_id,
            filename=file.filename,
            content=content_bytes,
            content_type=file.content_type or "application/octet-stream",
            metadata=meta_dict,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            tenant_id=tenant.tenant_id,
            content_hash=content_hash,
        )
    except Exception as e:
        logger.error("Document indexing failed", error=str(e), filename=file.filename)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                code="INDEXING_FAILED",
                message=f"Document indexing failed: {str(e)}",
            ).model_dump(),
        )

    return DocumentUploadResponse(
        document_id=document_id,
        chunks_count=result["chunks_count"],
        status=result["status"],
        filename=file.filename,
        file_size_bytes=len(content_bytes),
        estimated_tokens=result.get("estimated_tokens"),
    )


@router.post(
    "/search",
    response_model=RAGQueryResponse,
    responses={
        200: {"description": "RAG 检索结果"},
        400: {"model": ErrorResponse},
    },
)
async def rag_search(
    request: RAGQueryRequest,
    tenant: TenantContext = Depends(get_current_tenant),
    pipeline=Depends(get_rag_pipeline),
    token_counter=Depends(get_token_counter),
):
    """执行 RAG 检索查询。

    检索相关文档块并使用 LLM 生成回答。
    支持语义检索、关键词检索、混合检索和 MMR 检索策略。
    """
    start_time = time.monotonic()

    # Check cache for identical query
    cache_key = hashlib.sha256(
        f"{tenant.tenant_id}:{request.query}:{request.retrieval_strategy}:{request.top_k}".encode()
    ).hexdigest()

    cached_response = await pipeline.check_cache(cache_key)
    cache_hit = cached_response is not None

    if cache_hit:
        rag_cache_hits.labels(level="exact").inc()
        elapsed_ms = (time.monotonic() - start_time) * 1000
        return RAGQueryResponse(
            answer=cached_response["answer"],
            sources=[SourceDoc(**s) for s in cached_response["sources"]],
            latency_ms=round(elapsed_ms, 2),
            cost_usd=0.0,
            cache_hit=True,
        )

    try:
        retrieval_start = time.monotonic()

        # Retrieve relevant chunks
        retrieval_result = await pipeline.retrieve(
            query=request.query,
            top_k=request.top_k,
            strategy=request.retrieval_strategy,
            filters=request.filters,
            tenant_id=tenant.tenant_id,
        )

        retrieval_latency = (time.monotonic() - retrieval_start) * 1000
        rag_retrieval_latency.observe(retrieval_latency / 1000)

        # Apply reranking if requested
        if request.rerank and retrieval_result.chunks:
            retrieval_result = await pipeline.rerank(
                query=request.query,
                chunks=retrieval_result.chunks,
                model=request.rerank_model,
            )

        # Generate answer
        gen_start = time.monotonic()
        generation_result = await pipeline.generate(
            query=request.query,
            contexts=[c.content for c in retrieval_result.chunks],
            tenant_id=tenant.tenant_id,
        )
        generation_latency = (time.monotonic() - gen_start) * 1000

        elapsed_ms = (time.monotonic() - start_time) * 1000

        # Cache the response
        await pipeline.cache_response(
            cache_key=cache_key,
            answer=generation_result.answer,
            sources=[s.model_dump() if hasattr(s, 'model_dump') else s for s in retrieval_result.chunks],
            ttl=3600,
        )

        # Token tracking
        token_usage_obj = generation_result.token_usage or {}
        from src.observability.metrics import token_usage as token_usage_metric
        token_usage_metric.labels(
            tenant_id=tenant.tenant_id,
            provider="rag",
            model="rag-pipeline",
            type="input",
        ).inc(token_usage_obj.get("prompt_tokens", 0))
        token_usage_metric.labels(
            tenant_id=tenant.tenant_id,
            provider="rag",
            model="rag-pipeline",
            type="output",
        ).inc(token_usage_obj.get("completion_tokens", 0))

        return RAGQueryResponse(
            answer=generation_result.answer,
            sources=[
                SourceDoc(
                    document_id=c.document_id,
                    chunk_id=c.chunk_id,
                    content=c.content,
                    score=c.score,
                    metadata=getattr(c, 'metadata', {}),
                    source_type=getattr(c, 'source_type', 'unknown'),
                    retrieval_strategy=request.retrieval_strategy,
                )
                for c in retrieval_result.chunks
            ],
            latency_ms=round(elapsed_ms, 2),
            cost_usd=getattr(generation_result, 'cost_usd', 0.0),
            cache_hit=False,
            retrieval_latency_ms=round(retrieval_latency, 2),
            generation_latency_ms=round(generation_latency, 2),
        )

    except Exception as e:
        logger.error("RAG search failed", error=str(e), query=request.query)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                code="RAG_SEARCH_FAILED",
                message=f"RAG search failed: {str(e)}",
            ).model_dump(),
        )


@router.post(
    "/chat",
    response_model=RAGQueryResponse,
    responses={200: {"description": "带对话上下文的 RAG 对话"}},
)
async def rag_chat(
    request: RAGQueryRequest,
    tenant: TenantContext = Depends(get_current_tenant),
    pipeline=Depends(get_rag_pipeline),
):
    """执行带对话历史感知的 RAG 对话查询。

    此端点维护对话上下文以支持后续追问。
    """
    # This delegates to the same pipeline but with conversation mode
    result = await pipeline.chat(
        query=request.query,
        top_k=request.top_k,
        strategy=request.retrieval_strategy,
        filters=request.filters,
        tenant_id=tenant.tenant_id,
    )

    return RAGQueryResponse(
        answer=result.answer,
        sources=[
            SourceDoc(
                document_id=s.document_id,
                chunk_id=s.chunk_id,
                content=s.content,
                score=s.score,
                metadata=getattr(s, 'metadata', {}),
                source_type=getattr(s, 'source_type', 'unknown'),
            )
            for s in result.sources
        ],
        latency_ms=round(result.latency_ms, 2),
        cost_usd=result.cost_usd,
        token_usage=getattr(result, 'token_usage', None),
    )


@router.post(
    "/evaluate",
    response_model=dict,
    responses={200: {"description": "RAG Pipeline 评估结果"}},
)
async def evaluate(
    request: EvalRequest,
    tenant: TenantContext = Depends(get_current_tenant),
    pipeline=Depends(get_rag_pipeline),
):
    """评估 RAG Pipeline 质量。

    将给定的测试查询通过 Pipeline 运行，计算评估指标（忠实度、相关性、上下文精确率/召回率）。
    """
    try:
        results = await pipeline.evaluate(
            queries=request.queries,
            expected_answers=request.expected_answers,
            metrics=request.metrics,
            top_k=request.top_k,
            strategy=request.retrieval_strategy,
            tenant_id=tenant.tenant_id,
        )
        return results
    except Exception as e:
        logger.error("RAG evaluation failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                code="EVALUATION_FAILED",
                message=f"Evaluation failed: {str(e)}",
            ).model_dump(),
        )


@router.get(
    "/cache/stats",
    response_model=dict,
    responses={200: {"description": "RAG 缓存统计"}},
)
async def cache_stats(
    tenant: TenantContext = Depends(get_current_tenant),
    pipeline=Depends(get_rag_pipeline),
):
    """获取 RAG 缓存统计数据，包括命中率和缓存大小。"""
    stats = await pipeline.get_cache_stats(tenant_id=tenant.tenant_id)
    return stats


@router.get(
    "/documents",
    response_model=dict,
    responses={200: {"description": "已索引文档列表"}},
)
async def list_documents(
    page: int = 1,
    page_size: int = 20,
    tenant: TenantContext = Depends(get_current_tenant),
    pipeline=Depends(get_rag_pipeline),
):
    """列出当前租户已索引的所有文档。"""
    documents = await pipeline.list_documents(
        tenant_id=tenant.tenant_id,
        page=page,
        page_size=page_size,
    )
    return documents


@router.delete(
    "/documents/{document_id}",
    response_model=dict,
    responses={200: {"description": "文档已删除"}},
)
async def delete_document(
    document_id: str,
    tenant: TenantContext = Depends(get_current_tenant),
    pipeline=Depends(get_rag_pipeline),
):
    """从索引中删除文档及其所有分块。"""
    try:
        await pipeline.delete_document(document_id, tenant_id=tenant.tenant_id)
        return {"status": "deleted", "document_id": document_id}
    except Exception as e:
        logger.error("Document deletion failed", error=str(e), document_id=document_id)
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                code="DOCUMENT_NOT_FOUND",
                message=f"Document not found or deletion failed: {str(e)}",
            ).model_dump(),
        )
