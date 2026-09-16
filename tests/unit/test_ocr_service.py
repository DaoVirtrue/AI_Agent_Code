"""Unit tests for the OCR service (image info extraction + graceful degradation)."""

import base64
import io
import struct
import zlib

import pytest

from src.services.ocr_service import OCRService, OCRResult


def make_png(width: int = 1, height: int = 1) -> bytes:
    """Generate a minimal valid PNG image."""
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    raw = b''.join(b'\x00\xff\x00\x00' for _ in range(height))  # filter + RGB red per row
    def chunk(typ, data):
        c = typ + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    return sig + chunk(b'IHDR', ihdr) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


class TestOCRService:
    """Tests for OCR service behavior."""

    @pytest.mark.asyncio
    async def test_extract_image_info(self):
        ocr = OCRService(use_tesseract=False)  # disable tesseract for deterministic test
        png = make_png(width=10, height=20)
        result = await ocr.extract(png, "test.png")
        assert isinstance(result, OCRResult)
        assert result.image_info["width"] == 10
        assert result.image_info["height"] == 20
        assert result.image_info["format"] == "PNG"
        # No tesseract -> no text, but success (graceful degradation)
        assert result.success is True
        assert result.engine == "none"

    @pytest.mark.asyncio
    async def test_empty_image_bytes(self):
        ocr = OCRService(use_tesseract=False)
        result = await ocr.extract(b"", "empty.png")
        assert result.success is True
        # Empty bytes may fail image info, but should not crash
        assert isinstance(result, OCRResult)

    def test_engine_status(self):
        ocr = OCRService(use_tesseract=False)
        status = ocr.engine_status()
        assert "tesseract" in status
        assert "vision_llm" in status
