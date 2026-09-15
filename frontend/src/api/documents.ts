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
