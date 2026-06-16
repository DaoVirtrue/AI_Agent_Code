export interface RAGQueryRequest {
  query: string;
  collection_name?: string;
  top_k?: number;
  tenant_id?: string;
  filters?: Record<string, string>;
}

export interface RAGQueryResponse {
  answer: string;
  sources: SourceDoc[];
  processing_time_ms: number;
  token_usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
}

export interface SourceDoc {
  content: string;
  metadata: {
    source: string;
    page?: number;
    chunk_index?: number;
    score: number;
    [key: string]: string | number | undefined;
  };
}

export interface DocumentUploadResponse {
  document_id: string;
  filename: string;
  status: 'processing' | 'completed' | 'failed';
  chunks_count?: number;
  error?: string;
}

export interface EvalRequest {
  query: string;
  expected_answer?: string;
  collection_name?: string;
  top_k?: number;
}
