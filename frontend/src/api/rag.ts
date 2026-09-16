import client from './client';
import { RAGQueryRequest, RAGQueryResponse, DocumentUploadResponse } from '@/types';

export async function queryRAG(request: RAGQueryRequest): Promise<RAGQueryResponse> {
  const response = await client.post<RAGQueryResponse>('/v1/rag/search', request);
  return response.data;
}

export async function uploadDocument(file: File, metadata?: Record<string, unknown>): Promise<DocumentUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  if (metadata) formData.append('metadata', JSON.stringify(metadata));
  const response = await client.post<DocumentUploadResponse>('/v1/rag/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
}

export async function listDocuments(): Promise<any> {
  const response = await client.get('/v1/rag/documents');
  return response.data;
}

export async function listKnowledgeBases(): Promise<{ items: { name: string; documents: number }[]; total: number }> {
  const response = await client.get('/v1/rag/knowledge-bases');
  return response.data;
}

export async function retrieveChunks(query: string, filters?: Record<string, string>, topK = 5): Promise<{ sources: any[] }> {
  const response = await client.post('/v1/rag/retrieve', {
    query,
    top_k: topK,
    retrieval_strategy: 'hybrid',
    filters,
    rerank: true,
  });
  return response.data;
}

export async function deleteDocument(documentId: string): Promise<any> {
  const response = await client.delete(`/v1/rag/documents/${documentId}`);
  return response.data;
}
