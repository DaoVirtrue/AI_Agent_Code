import client from './client';
import { RAGQueryRequest, RAGQueryResponse, DocumentUploadResponse } from '@/types';

export async function queryRAG(request: RAGQueryRequest): Promise<RAGQueryResponse> {
  const response = await client.post<RAGQueryResponse>('/v1/rag/query', request);
  return response.data;
}

export async function uploadDocument(file: File, collectionName?: string): Promise<DocumentUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  if (collectionName) formData.append('collection_name', collectionName);
  const response = await client.post<DocumentUploadResponse>('/v1/rag/documents', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
}

export async function listDocuments(): Promise<DocumentUploadResponse[]> {
  const response = await client.get<DocumentUploadResponse[]>('/v1/rag/documents');
  return response.data;
}
