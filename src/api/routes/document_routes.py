"""文档生成与下载路由 — LLM 生成内容转 md/docx/xlsx/pptx 文件下载，以及图片 OCR。"""

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.api.dependencies import get_current_tenant
from src.api.dependencies import TenantContext
from src.observability.logging_setup import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/documents", tags=["文档生成"])


class DocumentGenerateRequest(BaseModel):
    """Request to generate a downloadable document."""

    topic: str = Field(..., description="文档主题", min_length=1, max_length=5000)
    format: str = Field("md", description="输出格式", examples=["md", "docx", "xlsx", "pptx"])
    title: str = Field("document", description="文档标题/文件名")
    content: str | None = Field(None, description="直接提供的内容（可选，缺省则 LLM 生成）")


@router.get("/formats", response_model=dict)
async def list_formats(http_request: Request, tenant: TenantContext = Depends(get_current_tenant)):
    """列出当前环境支持的文档生成格式。"""
    generator = http_request.app.state.document_generator
    return {"formats": generator.supported_formats()}


@router.post("/generate")
async def generate_document(
    request_body: DocumentGenerateRequest,
    http_request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """生成文档并返回可下载的文件。"""
    generator = http_request.app.state.document_generator

    try:
        # 内容：优先用请求提供的 content，否则 LLM 生成
        content = request_body.content
        if content is None:
            content = await generator.generate_content(request_body.topic, request_body.format)

        doc = generator.render(content, request_body.format, request_body.title)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # noqa: BLE001
        logger.error("Document generation failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Document generation failed: {e}")

    return Response(
        content=doc.content,
        media_type=doc.media_type,
        headers={"Content-Disposition": f'attachment; filename="{doc.filename}"'},
    )


@router.get("/ocr/status", response_model=dict)
async def ocr_status(http_request: Request, tenant: TenantContext = Depends(get_current_tenant)):
    """报告当前 OCR 引擎可用性。"""
    ocr = http_request.app.state.ocr_service
    return ocr.engine_status()


@router.post("/ocr")
async def ocr_image(
    http_request: Request,
    file: UploadFile = File(...),
    generate_answer: bool = Form(False),
    question: str = Form(""),
    tenant: TenantContext = Depends(get_current_tenant),
):
    """上传图片，OCR 识别文字，可选生成答案。

    识别出的文字会作为文档索引进 RAG 知识库，用户可基于识别内容提问。
    """
    ocr = http_request.app.state.ocr_service

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="空文件")

    result = await ocr.extract(content, filename=file.filename or "image")

    # 索引到 RAG（让 OCR 文本可被检索）
    rag_pipeline = getattr(http_request.app.state, "rag_pipeline", None)
    indexed = False
    if rag_pipeline and result.text.strip():
        import uuid
        await rag_pipeline.index_document(
            document_id=f"ocr-{uuid.uuid4().hex[:8]}",
            filename=file.filename or "ocr-image",
            content=result.text.encode("utf-8"),
            content_type="text/plain",
            metadata={"source": "ocr", "original_filename": file.filename},
            tenant_id=tenant.tenant_id,
        )
        indexed = True

    response: dict = {
        "ocr": result.to_dict(),
        "indexed": indexed,
    }

    # 可选：基于 OCR 文本生成答案
    if generate_answer and result.text.strip():
        question_text = question or "请总结这张图片的内容"
        generation = await rag_pipeline.generate(
            query=question_text,
            contexts=[result.text],
            tenant_id=tenant.tenant_id,
        )
        response["answer"] = generation.answer

    return response
