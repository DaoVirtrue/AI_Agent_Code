"""OCR service — 图片文字识别（可插拔引擎）。

设计：OCR 引擎做成可插拔抽象，按可用性降级：

1. **pytesseract**（系统装了 Tesseract OCR 时）——真实 OCR 文本识别
2. **vision LLM**（配置了多模态模型时）——走多模态识别
3. **降级**：提取图片元信息（尺寸/格式/大小），OCR 文本返回空并提示

无论如何，图片会作为"文档"索引进 RAG 知识库（图片的元信息 + OCR 文本），
用户上传后可以基于识别出的文本生成答案或下载相关文件。
"""

from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    """Result of an OCR operation."""

    text: str
    image_info: dict = field(default_factory=dict)
    engine: str = "none"
    success: bool = True

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "image_info": self.image_info,
            "engine": self.engine,
            "success": self.success,
        }


class OCRService:
    """Pluggable OCR service with graceful degradation.

    Args:
        vision_llm: Optional multimodal LLM (not yet supported by the current
            DeepSeek key; reserved for future models).
        use_tesseract: Try pytesseract when available.
    """

    def __init__(self, vision_llm: Any = None, use_tesseract: bool = True):
        self.vision_llm = vision_llm
        self.use_tesseract = use_tesseract

    async def extract(self, image_bytes: bytes, filename: str = "image") -> OCRResult:
        """Extract text and metadata from an image."""
        info = self._image_info(image_bytes)

        # Try tesseract first (local, deterministic)
        if self.use_tesseract:
            try:
                import pytesseract  # type: ignore
                from PIL import Image

                img = Image.open(io.BytesIO(image_bytes))
                text = pytesseract.image_to_string(img, lang="chi_sim+eng")
                if text.strip():
                    return OCRResult(text=text.strip(), image_info=info, engine="tesseract")
            except ImportError:
                logger.debug("pytesseract not installed")
            except Exception as exc:  # noqa: BLE001
                logger.warning("tesseract OCR failed: %s", exc)

        # Try vision LLM
        if self.vision_llm is not None:
            text = await self._vision_extract(image_bytes, filename)
            if text:
                return OCRResult(text=text, image_info=info, engine="vision_llm")

        # Fallback: no OCR engine available
        return OCRResult(
            text="",
            image_info=info,
            engine="none",
            success=True,
        )

    def _image_info(self, image_bytes: bytes) -> dict:
        """Extract basic image metadata (size / format / dimensions)."""
        info = {
            "size_bytes": len(image_bytes),
            "format": None,
            "width": None,
            "height": None,
        }
        try:
            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes))
            info["format"] = img.format
            info["width"], info["height"] = img.size
        except ImportError:
            logger.debug("Pillow not installed; image metadata unavailable")
        except Exception as exc:  # noqa: BLE001
            logger.debug("Image metadata extraction failed: %s", exc)
        return info

    async def _vision_extract(self, image_bytes: bytes, filename: str) -> str:
        """Use a multimodal LLM to read text from an image (reserved)."""
        try:
            b64 = base64.b64encode(image_bytes).decode()
            response = await self.vision_llm.ainvoke([
                {"role": "user", "content": [
                    {"type": "text", "text": "请识别这张图片中的所有文字，直接输出文字内容。"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ]},
            ])
            content = response.content if hasattr(response, "content") else str(response)
            return content.strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Vision LLM extraction failed: %s", exc)
            return ""

    def engine_status(self) -> dict:
        """Report which OCR engines are available."""
        tesseract = False
        if self.use_tesseract:
            try:
                import pytesseract  # type: ignore
                tesseract = True
            except ImportError:
                tesseract = False
        return {
            "tesseract": tesseract,
            "vision_llm": self.vision_llm is not None,
        }
