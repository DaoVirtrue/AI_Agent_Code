import { create } from 'zustand';
import type { RAGQueryRequest, RAGQueryResponse, SourceDoc } from '@/types';

// ---- Mock RAG data ----

const MOCK_SOURCES: SourceDoc[] = [
  {
    content: '大型语言模型（LLM）平台是一种统一管理和调用多种大语言模型的中间层系统。它提供了标准化的API接口、负载均衡、故障转移、速率限制和成本控制等功能。通过LLM平台，企业可以避免与多个模型供应商直接集成的复杂性。',
    metadata: {
      source: 'LLM平台技术白皮书.pdf',
      chunk_index: 3,
      score: 0.94,
      page: 5,
    },
  },
  {
    content: 'RAG（Retrieval-Augmented Generation）检索增强生成是一种将信息检索与文本生成相结合的技术。它首先从知识库中检索相关文档片段，然后将这些片段作为上下文提供给大语言模型，从而生成更准确、更具时效性的回答。',
    metadata: {
      source: 'RAG系统设计指南.md',
      chunk_index: 1,
      score: 0.89,
      page: 2,
    },
  },
  {
    content: 'Agent（智能体）是具备自主决策能力的AI系统。在LLM平台中，Agent可以调用各种工具（如搜索、计算、代码执行）来完成复杂任务。ReAct模式是常见的Agent实现方式，交替进行推理（Thought）和行动（Action）。',
    metadata: {
      source: 'Agent架构设计文档.pdf',
      chunk_index: 5,
      score: 0.82,
      page: 12,
    },
  },
  {
    content: '提示词工程（Prompt Engineering）是设计和优化输入提示词以引导LLM产生期望输出的技术。好的提示词应包含角色定义、任务描述、输出格式要求和示例。模板化提示词系统可以提升团队协作效率。',
    metadata: {
      source: '提示词最佳实践.pdf',
      chunk_index: 2,
      score: 0.78,
      page: 8,
    },
  },
  {
    content: 'API网关是LLM平台的核心组件，负责请求路由、认证授权、速率限制和监控日志。它支持OpenAI兼容的API格式，使得用户可以无缝切换不同的后端模型提供商。健康检查和熔断机制保证了系统的高可用性。',
    metadata: {
      source: '网关架构说明.md',
      chunk_index: 0,
      score: 0.73,
      page: 1,
    },
  },
];

const MOCK_DOCUMENTS: DocumentItem[] = [
  {
    id: 'doc_1',
    filename: 'LLM平台技术白皮书.pdf',
    file_type: 'pdf',
    status: 'indexed',
    chunk_count: 45,
    file_size_bytes: 2048000,
    upload_date: new Date(Date.now() - 7 * 86400000).toISOString(),
  },
  {
    id: 'doc_2',
    filename: 'RAG系统设计指南.md',
    file_type: 'md',
    status: 'indexed',
    chunk_count: 32,
    file_size_bytes: 512000,
    upload_date: new Date(Date.now() - 5 * 86400000).toISOString(),
  },
  {
    id: 'doc_3',
    filename: 'Agent架构设计文档.pdf',
    file_type: 'pdf',
    status: 'indexed',
    chunk_count: 78,
    file_size_bytes: 4096000,
    upload_date: new Date(Date.now() - 3 * 86400000).toISOString(),
  },
];

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function generateAnswer(query: string, sources: SourceDoc[]): string {
  const topSource = sources[0];
  const docNames = sources.map((s, i) => `${i + 1}. ${s.metadata.source}`).join('\n');

  return `## 检索结果分析

根据您的问题"${query}"，系统从知识库中检索到 ${sources.length} 个相关文档片段。

### 检索到的文档

${docNames}

### 综合回答

结合上述文档内容，${topSource.content.slice(0, 80)}...

检索增强生成（RAG）系统通过向量相似度搜索找到了与您问题相关的信息。最高匹配度的文档是 **${topSource.metadata.source}**（相似度分数：${topSource.metadata.score}），其中包含了关于该主题的核心内容。

基于这些检索结果，系统综合生成了上述回答。这种方法结合了**精确检索**和**语言生成**的优势，确保了回答的准确性和相关性。

> 本次搜索共检索 ${sources.length} 个文档片段，处理时间约 450ms。`;
}

interface DocumentItem {
  id: string;
  filename: string;
  file_type: string;
  status: 'indexed' | 'processing' | 'failed';
  chunk_count: number;
  file_size_bytes: number;
  upload_date: string;
}

interface SearchResultItem {
  content: string;
  score: number;
  documentId: string;
  chunkId: string;
  sourceName: string;
}

interface RAGState {
  documents: DocumentItem[];
  documentsLoading: boolean;
  searchResults: SearchResultItem[];
  searchAnswer: string;
  searchLatency: number;
  searchCost: number;
  searchLoading: boolean;
  uploadProgress: number;
  isUploading: boolean;
  error: string | null;

  fetchDocuments: () => Promise<void>;
  uploadDoc: (file: File, collectionName?: string) => Promise<void>;
  deleteDoc: (documentId: string) => Promise<void>;
  searchRag: (query: string, topK: number) => Promise<void>;
  clearSearch: () => void;
  clearError: () => void;
}

export const useRAGStore = create<RAGState>((set, get) => ({
  documents: [],
  documentsLoading: false,
  searchResults: [],
  searchAnswer: '',
  searchLatency: 0,
  searchCost: 0,
  searchLoading: false,
  uploadProgress: 0,
  isUploading: false,
  error: null,

  fetchDocuments: async () => {
    set({ documentsLoading: true, error: null });
    try {
      // MOCK: Return pre-built mock documents after a short delay
      await sleep(300);
      set({ documents: MOCK_DOCUMENTS, documentsLoading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch documents';
      set({ error: message, documentsLoading: false });
    }
  },

  uploadDoc: async (file: File, collectionName?: string) => {
    set({ isUploading: true, uploadProgress: 0, error: null });
    try {
      // MOCK: Simulate upload with progress
      set({ uploadProgress: 30 });
      await sleep(400);
      set({ uploadProgress: 70 });
      await sleep(300);

      const ext = file.name.split('.').pop() || 'unknown';
      const newDoc: DocumentItem = {
        id: `doc_${Date.now()}`,
        filename: file.name,
        file_type: ext,
        status: 'indexed',
        chunk_count: Math.floor(10 + Math.random() * 40),
        file_size_bytes: file.size,
        upload_date: new Date().toISOString(),
      };

      set((s) => ({
        documents: [newDoc, ...s.documents],
        isUploading: false,
        uploadProgress: 100,
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Upload failed';
      set({ error: message, isUploading: false, uploadProgress: 0 });
    }
  },

  deleteDoc: async (documentId: string) => {
    try {
      // Remove from local state (API delete endpoint not yet implemented)
      set((state) => ({
        documents: state.documents.filter((d) => d.id !== documentId),
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Delete failed';
      set({ error: message });
    }
  },

  searchRag: async (query: string, topK: number) => {
    set({ searchLoading: true, searchResults: [], searchAnswer: '', error: null });
    try {
      // MOCK: Simulate search with 500ms delay
      await sleep(400 + Math.floor(Math.random() * 200));

      const numResults = Math.min(topK, MOCK_SOURCES.length);
      const shuffled = [...MOCK_SOURCES].sort(() => Math.random() - 0.5);
      const selected = shuffled.slice(0, numResults);

      const results: SearchResultItem[] = selected.map((s: SourceDoc) => ({
        content: s.content,
        score: s.metadata?.score ?? 0,
        documentId: s.metadata?.source ?? 'unknown',
        chunkId: (s.metadata?.chunk_index ?? 0).toString(),
        sourceName: s.metadata?.source ?? 'unknown',
      }));

      const answer = generateAnswer(query, selected);
      const promptTokens = 120 + Math.floor(Math.random() * 30);
      const completionTokens = 300 + Math.floor(Math.random() * 100);
      const totalTokens = promptTokens + completionTokens;
      const latency = 400 + Math.floor(Math.random() * 200);

      set({
        searchResults: results,
        searchAnswer: answer,
        searchLatency: latency,
        searchCost: (totalTokens / 1000000) * 0.3,
        searchLoading: false,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Search failed';
      set({ error: message, searchLoading: false });
    }
  },

  clearSearch: () => set({ searchResults: [], searchAnswer: '', searchLatency: 0, searchCost: 0 }),
  clearError: () => set({ error: null }),
}));
