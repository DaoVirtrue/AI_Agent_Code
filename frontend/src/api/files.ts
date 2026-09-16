import client from './client';

// 解析文档（PDF/DOCX/TXT 等）为文本
export async function parseDocument(file: File): Promise<{ text: string; filename: string }> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await client.post('/v1/rag/parse', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
}

// OCR 识别图片文字
export async function ocrImage(file: File): Promise<any> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('generate_answer', 'false');
  const response = await client.post('/v1/documents/ocr', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
}
