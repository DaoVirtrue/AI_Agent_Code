"""文档生成与下载路由 — LLM 生成内容转 md/docx/xlsx/pptx 文件下载。"""

from fastapi import APIRouter, Depends, HTTPException, Request
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
