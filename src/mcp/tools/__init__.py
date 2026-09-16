"""MCP 内置工具 — 通过 MCP 暴露给 Agent 自动调用的能力.

这些工具代表"操作电脑/文件/文档"的能力，Agent 通过 MCP 协议自动发现和调用：

- ``cli.execute``      — 执行 shell 命令（高危，每次授权）
- ``document.generate`` — 生成/保存文档（md/docx/xlsx/pptx）
- ``document.ocr``      — OCR 图片文字识别
"""

from src.mcp.tools.cli_tool import CLITool
from src.mcp.tools.document_tool import DocumentTool
from src.mcp.tools.ocr_tool import OCRTool

__all__ = ["CLITool", "DocumentTool", "OCRTool"]
