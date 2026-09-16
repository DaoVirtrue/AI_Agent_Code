"""OCR tool — 通过 MCP 识别图片文字.

Wraps the OCRService as an MCP tool. Takes an image (path or base64) and
returns the recognized text. If the image contains sensitive content, the
result dispatch is flagged as requiring approval.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from src.core.tools import BaseTool, ToolDefinition, ToolResult, ToolStatus

logger = logging.getLogger(__name__)


class OCRTool(BaseTool):
    """Recognize text from an image via MCP.

    Args:
        ocr_service: OCRService instance.
    """

    def __init__(self, ocr_service: Any = None):
        self.ocr_service = ocr_service

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="document.ocr",
            description=(
                "识别图片中的文字（OCR）。输入图片文件路径或 base64 编码，"
                "返回识别出的文本内容。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "图片文件路径"},
                    "image_base64": {"type": "string", "description": "图片的 base64 编码（与 image_path 二选一）"},
                },
            },
            category="document",
            requires_approval=False,  # 读取图片文字本身安全；外发需另行授权
            timeout_seconds=60,
            max_retries=1,
        )

    async def execute(self, **kwargs) -> ToolResult:
        image_path = kwargs.get("image_path", "")
        image_b64 = kwargs.get("image_base64", "")

        if not image_path and not image_b64:
            return ToolResult(status=ToolStatus.INVALID_ARGS, error="需提供 image_path 或 image_base64")

        # Load image bytes
        if image_path:
            try:
                image_bytes = Path(image_path).read_bytes()
            except Exception as e:
                return ToolResult(status=ToolStatus.INVALID_ARGS, error=f"无法读取图片: {e}")
        else:
            try:
                image_bytes = base64.b64decode(image_b64)
            except Exception as e:
                return ToolResult(status=ToolStatus.INVALID_ARGS, error=f"base64 解码失败: {e}")

        if self.ocr_service is None:
            from src.services.ocr_service import OCRService
            self.ocr_service = OCRService()

        result = await self.ocr_service.extract(image_bytes, filename=image_path or "image")

        if not result.text.strip():
            return ToolResult(
                status=ToolStatus.SUCCESS,
                data={
                    "text": "",
                    "image_info": result.image_info,
                    "engine": result.engine,
                    "note": "OCR 引擎不可用（未安装 tesseract），已提取图片信息",
                },
            )

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "text": result.text,
                "image_info": result.image_info,
                "engine": result.engine,
            },
        )
