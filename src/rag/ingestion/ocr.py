"""OCR Engine for extracting text from images and scanned PDFs.

Supports PaddleOCR (primary) and Tesseract (fallback) backends.
Both are optional dependencies - graceful degradation when unavailable.
"""

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Optional imports
try:
    from paddleocr import PaddleOCR
    HAS_PADDLEOCR = True
except ImportError:
    HAS_PADDLEOCR = False
    logger.info("PaddleOCR not installed")

try:
    import pytesseract
    from PIL import Image
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False
    logger.info("Tesseract not installed")


class OCREngine:
    """OCR engine for extracting text from images and scanned PDFs.

    Backends: paddleocr (default, Chinese+English), tesseract (fallback).
    When neither is available, falls back to a warning-only mode.
    """

    def __init__(self, backend: str = "paddleocr", lang: str = "ch"):
        """Initialize OCR engine.

        Args:
            backend: "paddleocr" or "tesseract"
            lang: Language code - "ch" for Chinese, "en" for English, "ch_en" for both
        """
        self.backend = backend.lower()
        self.lang = lang
        self._ocr = None

        if self.backend == "paddleocr":
            if HAS_PADDLEOCR:
                try:
                    use_angle_cls = True
                    lang_code = lang if lang in ("ch", "en") else "ch"
                    self._ocr = PaddleOCR(
                        use_angle_cls=use_angle_cls,
                        lang=lang_code,
                        use_gpu=False,
                        show_log=False,
                    )
                    logger.info("PaddleOCR initialized (lang=%s)", lang_code)
                except Exception as e:
                    logger.error("PaddleOCR init failed: %s", e)
                    self._ocr = None
            else:
                logger.warning("PaddleOCR not available, falling back to tesseract")
                self.backend = "tesseract"

        if self.backend == "tesseract":
            if HAS_TESSERACT:
                logger.info("Tesseract OCR initialized")
            else:
                logger.warning("Neither PaddleOCR nor Tesseract available. OCR disabled.")

    async def extract_text(self, image_path: str) -> str:
        """Extract text from a single image file.

        Args:
            image_path: Path to image file (PNG, JPG, TIFF, etc.)

        Returns:
            Extracted text string
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")

        if self.backend == "paddleocr" and self._ocr:
            return await self._extract_paddleocr(image_path)
        elif self.backend == "tesseract" and HAS_TESSERACT:
            return await self._extract_tesseract(image_path)
        else:
            logger.warning("No OCR backend available for %s", image_path)
            return f"[OCR unavailable - could not process: {image_path}]"

    async def extract_from_pdf(
        self, pdf_path: str, page_range: Optional[tuple[int, int]] = None
    ) -> list[dict]:
        """Extract text from each page of a scanned PDF.

        Converts PDF pages to images, then OCRs each one.

        Args:
            pdf_path: Path to PDF file
            page_range: Optional (start_page, end_page) 1-based inclusive

        Returns:
            List of {page_num, text, confidence} dicts
        """
        results: list[dict] = []

        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        # Try using pdf2image if available
        try:
            from pdf2image import convert_from_path
            start_page = page_range[0] if page_range else 1
            end_page = page_range[1] if page_range else None

            images = convert_from_path(
                pdf_path,
                first_page=start_page,
                last_page=end_page,
                dpi=300,
            )

            import tempfile
            for i, img in enumerate(images):
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    img.save(tmp.name, "PNG")
                    tmp_path = tmp.name

                try:
                    text = await self.extract_text(tmp_path)
                    results.append({
                        "page_num": start_page + i,
                        "text": text,
                        "confidence": 0.85,  # Estimated
                    })
                finally:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

        except ImportError:
            logger.warning("pdf2image not installed, cannot process PDF pages to images")
            results.append({
                "page_num": 1,
                "text": f"[pdf2image not available - cannot OCR PDF: {pdf_path}]",
                "confidence": 0.0,
            })

        return results

    async def _extract_paddleocr(self, image_path: str) -> str:
        """Extract using PaddleOCR."""
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._ocr.ocr, image_path, cls=True)

        if not result or not result[0]:
            return ""

        lines = []
        for line_info in result[0]:
            if line_info and len(line_info) >= 2:
                text = line_info[1][0] if isinstance(line_info[1], (list, tuple)) else str(line_info[1])
                lines.append(text)

        return "\n".join(lines)

    async def _extract_tesseract(self, image_path: str) -> str:
        """Extract using Tesseract."""
        import asyncio
        loop = asyncio.get_event_loop()
        img = await loop.run_in_executor(None, Image.open, image_path)
        lang_map = {"ch": "chi_sim", "en": "eng", "ch_en": "chi_sim+eng"}
        tesseract_lang = lang_map.get(self.lang, "eng")
        text = await loop.run_in_executor(
            None, pytesseract.image_to_string, img, tesseract_lang
        )
        return text.strip()

    def is_available(self) -> bool:
        """Check if any OCR backend is configured and working."""
        return (self.backend == "paddleocr" and self._ocr is not None) or \
               (self.backend == "tesseract" and HAS_TESSERACT)
