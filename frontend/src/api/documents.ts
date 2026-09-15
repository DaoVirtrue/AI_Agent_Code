import client from './client';

export async function listDocFormats(): Promise<{ formats: string[] }> {
  const response = await client.get('/v1/documents/formats');
  return response.data;
}

export async function generateDocument(topic: string, format: string, title?: string, content?: string): Promise<Blob> {
  const response = await client.post(
    '/v1/documents/generate',
    { topic, format, title, content },
    { responseType: 'blob' },
  );
  return response.data as Blob;
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export async function ocrImage(file: File, generateAnswer: boolean, question?: string): Promise<any> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('generate_answer', String(generateAnswer));
  if (question) formData.append('question', question);
  const response = await client.post('/v1/documents/ocr', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
}
