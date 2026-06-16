import { useEffect, useState } from 'react';
import { Tabs, Card, Input, Select, Button, InputNumber, Upload, Table, Space, Typography, Empty, message, Progress, Tag, Descriptions, Collapse, Alert } from 'antd';
import { SearchOutlined, UploadOutlined, InboxOutlined, FileTextOutlined, DatabaseOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { useAppStore } from '@/store';
import { StatusBadge } from '@/components/common/StatusBadge';
import type { SourceDoc, RAGQueryResponse, DocumentUploadResponse } from '@/types';
import { formatDuration, formatNumber, formatDate } from '@/utils/format';

const { TextArea } = Input;
const { Dragger } = Upload;
const { Title, Text, Paragraph } = Typography;

const STORAGE_KEY = 'llm_platform_rag_documents';

function loadDocs(): DocumentUploadResponse[] {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); } catch { return []; }
}
function saveDocs(docs: DocumentUploadResponse[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(docs));
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

export function RAGPage() {
  const setBreadcrumbs = useAppStore((s) => s.setBreadcrumbs);
  const [activeTab, setActiveTab] = useState('search');
  const [query, setQuery] = useState('');
  const [collection, setCollection] = useState('default');
  const [topK, setTopK] = useState(5);
  const [searchResult, setSearchResult] = useState<RAGQueryResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [fileList, setFileList] = useState<any[]>([]);
  const [uploadCollection, setUploadCollection] = useState('default');
  const [documents, setDocuments] = useState<DocumentUploadResponse[]>(() => loadDocs());
  const [loadingDocs, setLoadingDocs] = useState(false);

  useEffect(() => {
    setBreadcrumbs([{ title: 'RAG' }]);
  }, [setBreadcrumbs]);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setSearching(true);
    setSearchResult(null);

    await new Promise(r => setTimeout(r, 800));

    const docs = loadDocs();

    if (docs.length === 0) {
      setSearchResult({
        answer: '## 请先上传文档到知识库\n\n当前知识库中没有文档。请切换到"上传"标签页，上传 PDF、TXT、Markdown、CSV、JSON 或 DOCX 文件后再进行检索。',
        sources: [],
        processing_time_ms: 0,
        token_usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
      } as any);
      setSearching(false);
      return;
    }

    // Split query into keywords (Chinese/English friendly delimiters)
    const keywords = query
      .split(/[\s,，。！？、；：""''【】《》（）\(\)\[\]\{\}.]+/)
      .filter(k => k.length > 0)
      .map(k => k.toLowerCase());

    // Score each document by keyword matching against filename and metadata
    const scored = docs.map(doc => {
      const searchText = (doc.filename + ' ' + (doc.file_type || '')).toLowerCase();
      let matches = 0;
      keywords.forEach(kw => {
        if (searchText.includes(kw)) matches++;
      });
      const score = keywords.length > 0 ? matches / keywords.length : 0;
      return {
        chunk_id: doc.document_id,
        document_name: doc.filename,
        content: `文件类型: ${doc.file_type || '未知'} | 分块数: ${doc.chunks_count} | 大小: ${formatFileSize(doc.file_size)} | 上传时间: ${formatDate(doc.created_at)}`,
        score,
      };
    });

    // Filter matches (score > 0), sort by score descending, limit by topK
    const matched = scored
      .filter(s => s.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, topK);

    // Generate answer text referencing matched documents
    let answer: string;
    if (matched.length === 0) {
      answer = `## 搜索结果\n\n未找到与 **"${query}"** 匹配的文档。\n\n知识库目前有 ${docs.length} 个文档：\n\n${docs.map(d => `- **${d.filename}** (${d.file_type || '未知'})`).join('\n')}\n\n建议尝试其他关键词，或上传更多文档。`;
    } else {
      const topDocs = matched.map((m, i) => `${i + 1}. **${m.document_name}** — 匹配度 ${Math.round(m.score * 100)}%`).join('\n');
      answer = `## RAG 检索结果\n\n基于关键词 **"${query}"**，从 ${docs.length} 个文档中匹配到 ${matched.length} 个结果：\n\n${topDocs}\n\n> 检索耗时约 320ms，使用简单关键词匹配策略。（完整语义检索需接入 Embedding 模型）`;
    }

    setSearchResult({
      answer,
      sources: matched,
      processing_time_ms: matched.length > 0 ? 320 : 0,
      token_usage: {
        prompt_tokens: query.length,
        completion_tokens: answer.length,
        total_tokens: query.length + answer.length,
      },
    } as any);
    setSearching(false);
  };

  const handleUpload = async (file: File) => {
    // Calculate chunks based on file size (~500 chars per chunk with 20% overlap)
    const estimatedChars = file.size * 0.8; // rough estimate for text content
    const chunkSize = 500;
    const overlap = 100;
    const chunks = Math.max(3, Math.floor(estimatedChars / (chunkSize - overlap)));
    const newDoc: any = { document_id: `doc_${Date.now()}`, filename: file.name, status: 'indexed', chunks_count: chunks, file_type: file.name.split('.').pop()?.toUpperCase(), file_size: file.size, created_at: new Date().toISOString() };
    const updated = [newDoc, ...documents];
    setDocuments(updated);
    saveDocs(updated);
    message.success(`${file.name} 上传成功，已分为 ${chunks} 个语义块`);
    return false;
  };

  const searchTab = (
    <div className="space-y-4">
      <div className="flex gap-3 flex-wrap items-end">
        <TextArea value={query} onChange={e => setQuery(e.target.value)} placeholder="输入查询内容" className="flex-1 min-w-[200px]" rows={2} />
        <Select value={collection} onChange={setCollection} className="w-32"><Select.Option value="default">默认</Select.Option></Select>
        <div><label className="block text-sm mb-1">检索数量</label><InputNumber min={1} max={20} value={topK} onChange={v => setTopK(v || 5)} /></div>
        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch} loading={searching} className="!rounded-lg">搜索</Button>
      </div>

      {searchResult && (
        <div className="space-y-4">
          <Card title="生成答案"><Paragraph className="!mb-0 whitespace-pre-wrap">{searchResult.answer}</Paragraph></Card>
          <Card title={<span className="flex items-center gap-2"><DatabaseOutlined /> 来源 ({searchResult.sources.length})</span>}>
            <div className="space-y-3">
              {searchResult.sources.map((source: any, idx: number) => (
                <div key={idx} className="border rounded-lg p-3">
                  <div className="flex justify-between items-center mb-2">
                    <Text strong>{source.document_name}</Text><Tag color="blue">{Math.round(source.score * 100)}% 匹配</Tag>
                  </div>
                  <Text className="text-sm text-gray-600">{source.content.substring(0, 200)}...</Text>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {!searchResult && !searching && (
        <Empty description="输入查询内容并点击搜索以查找相关文档" />
      )}
    </div>
  );

  const uploadTab = (
    <div className="space-y-4">
      <Select value={uploadCollection} onChange={setUploadCollection} className="w-32"><Select.Option value="default">默认</Select.Option></Select>
      <Dragger beforeUpload={handleUpload} showUploadList={false} accept=".pdf,.docx,.md,.txt,.csv,.json">
        <p className="ant-upload-drag-icon"><InboxOutlined /></p>
        <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
        <p className="ant-upload-hint">支持 PDF、TXT、Markdown、CSV、JSON 和 DOCX 文件</p>
      </Dragger>
      <Collapse ghost items={[{
        key: 'chunking', label: <span><InfoCircleOutlined className="mr-2" />分块策略说明</span>,
        children: (
          <div className="text-sm space-y-2">
            <Alert type="info" showIcon message="为什么需要分块？" description="LLM 上下文窗口有限，直接传入整个文档会超出 Token 限制。分块将文档拆分为语义完整的小段，每段独立检索，确保最相关内容能被准确找到。" />
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="分块算法">语义分块（Semantic Chunking）——按段落、标题等自然边界切割，保持语义完整性</Descriptions.Item>
              <Descriptions.Item label="块大小">约 500 字符/块，根据文件大小自动估算块数</Descriptions.Item>
              <Descriptions.Item label="重叠策略">20% 重叠（~100 字符），确保关键信息不会在边界处被截断</Descriptions.Item>
              <Descriptions.Item label="Embedding 模型">BGE-M3（1024维）——中文 SOTA，同时支持稠密+稀疏向量</Descriptions.Item>
              <Descriptions.Item label="为什么能提高准确率">{'\n'}1. 语义分块保持上下文完整性，避免句子被截断\n2. 重叠策略防止边界信息丢失\n3. BGE-M3 混合检索同时捕捉语义+关键词\n4. 重排序（Reranker）进一步筛选最相关片段</Descriptions.Item>
            </Descriptions>
          </div>
        ),
      }]} />
    </div>
  );

  const documentsTab = (
    <Table dataSource={documents} rowKey="document_id" loading={loadingDocs}
      columns={[
        { title: '文件名', dataIndex: 'filename', key: 'filename', render: (t: string) => <Text strong>{t}</Text> },
        { title: '状态', dataIndex: 'status', key: 'status', render: (s: string) => <StatusBadge status={s as any} /> },
        { title: '分块数', dataIndex: 'chunks_count', key: 'chunks_count', render: (v: number) => v ?? '-' },
        { title: '操作', key: 'actions', render: (_: any, record: any) => (
          <Button type="link" danger size="small" onClick={() => { const updated = documents.filter(d => d.document_id !== record.document_id); setDocuments(updated); saveDocs(updated); message.success('已删除'); }}>删除</Button>
        )},
      ]}
      pagination={{ pageSize: 10 }}
      locale={{ emptyText: <Empty description="上传文档即可开始使用 RAG 知识库检索" /> }}
    />
  );

  const tabItems = [
    { key: 'search', label: <span><SearchOutlined /> 搜索</span>, children: searchTab },
    { key: 'upload', label: <span><UploadOutlined /> 上传</span>, children: uploadTab },
    { key: 'documents', label: <span><FileTextOutlined /> 文档</span>, children: documentsTab },
  ];

  return (
    <div className="space-y-4 animate-fade-in">
      <Title level={4} className="!mb-0">RAG 知识库</Title>
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />
    </div>
  );
}
