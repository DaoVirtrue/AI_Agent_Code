"""Unit tests for the document generation service (md/docx/xlsx/pptx)."""

import pytest

from src.services.document_generator import DocumentGenerator, GeneratedDocument


@pytest.fixture
def generator():
    return DocumentGenerator(llm=None)


class TestDocumentGenerator:
    """Tests for document rendering."""

    def test_render_markdown(self, generator):
        doc = generator.render("# Title\n\n- point 1", "md", "test")
        assert isinstance(doc, GeneratedDocument)
        assert doc.format == "md"
        assert doc.filename == "test.md"
        assert b"point 1" in doc.content

    def test_render_docx(self, generator):
        doc = generator.render("# Title\n\nContent here", "docx", "test")
        assert doc.format == "docx"
        assert doc.media_type.startswith("application/vnd.openxmlformats-officedocument")
        assert len(doc.content) > 0  # non-empty docx zip

    def test_render_xlsx(self, generator):
        doc = generator.render("row1\nrow2", "xlsx", "test")
        assert doc.format == "xlsx"
        assert len(doc.content) > 0

    def test_render_pptx(self, generator):
        doc = generator.render("# Title\n\n# Section 1\ncontent", "pptx", "test")
        assert doc.format == "pptx"
        assert len(doc.content) > 0

    def test_unsupported_format(self, generator):
        with pytest.raises(ValueError, match="Unsupported format"):
            generator.render("x", "pdf", "test")

    def test_supported_formats(self, generator):
        formats = generator.supported_formats()
        assert "md" in formats  # md always supported

    @pytest.mark.asyncio
    async def test_generate_content_without_llm(self, generator):
        content = await generator.generate_content("测试主题", "md")
        assert "测试主题" in content
        assert "# " in content  # markdown heading
