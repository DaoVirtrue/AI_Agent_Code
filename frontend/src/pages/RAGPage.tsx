import { useEffect, useState, useCallback } from 'react';
import { Tabs, Card, Input, Select, Button, InputNumber, Upload, Table, Space, Typography, Empty, message, Tag, Collapse, Alert, Descriptions } from 'antd';
import { SearchOutlined, UploadOutlined, InboxOutlined, FileTextOutlined, DatabaseOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { useAppStore } from '@/store';
import { StatusBadge } from '@/components/common/StatusBadge';
import type { RAGQueryResponse, DocumentUploadResponse } from '@/types';
import { queryRAG, uploadDocument, listDocuments, deleteDocument } from '@/api/rag';
import { formatDuration } from '@/utils/format';

const { TextArea } = Input;
const { Dragger } = Upload;
const { Title, Text, Paragraph } = Typography;

export function RAGPage() {
  const setBreadcrumbs = useAppStore((s) => s.setBreadcrumbs);
  const [activeTab, setActiveTab] = useState('search');
  const [query, setQuery] = useState('');
  const [topK, setTopK] = useState(5);
  const [strategy, setStrategy] = useState('hybrid');
  const [searchResult, setSearchResult] = useState<RAGQueryResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [documents, setDocuments] = useState<any[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(false);

  useEffect(() => {
    setBreadcrumbs([{ title: 'RAG' }]);
    refreshDocuments();
  }, [setBreadcrumbs]);

  const refreshDocuments = useCallback(async () => {
    setLoadingDocs(true);
    try {
      const data = await listDocuments();
      setDocuments(data?.items || data || []);
    } catch {
      setDocuments([]);
    } finally {
      setLoadingDocs(false);
    }
  }, []);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setSearching(true);
    setSearchResult(null);
    try {
      const result = await queryRAG({
        query: query.trim(),
        top_k: topK,
        retrieval_strategy: strategy,
        include_scores: true,
        rerank: true,
      });
      setSearchResult(result);
    } catch (err: any) {
      message.error('检索失败: ' + (err?.message || '未知错误'));
    } finally {
      setSearching(false);
    }
  };

  const handleUpload = async (file: File) => {
    try {
      const result = await uploadDocument(file);
      message.success(`${file.name} 上传成功，已分 ${result.chunks_count} 块`);
      refreshDocuments();
    } catch (err: any) {
      message.error('上传失败: ' + (err?.message || '未知错误'));
    }
    return false; // prevent auto upload by antd
  };

  const handleDelete = async (documentId: string) => {
    try {
      await deleteDocument(documentId);
      message.success('已删除');
      refreshDocuments();
    } catch (err: any) {
      message.error('删除失败: ' + (err?.message || '未知错误'));
    }
  };

  const searchTab = (
    <div className="space-y-4">
      <div className="flex gap-3 flex-wrap items-end">
        <TextArea value={query} onChange={e => setQuery(e.target.value)} placeholder="输入查询内容" className="flex-1 min-w-[200px]" rows={2} />
        <div>
          <label className="block text-sm mb-1">检索策略</label>
          <Select value={strategy} onChange={setStrategy} className="w-32">
            <Select.Option value="hybrid">混合</Select.Option>
            <Select.Option value="semantic">语义</Select.Option>
            <Select.Option value="keyword">关键词</Select.Option>
            <Select.Option value="mmr">MMR</Select.Option>
          </Select>
        </div>
        <div><label className="block text-sm mb-1">检索数量</label><InputNumber min={1} max={20} value={topK} onChange={v => setTopK(v || 5)} /></div>
        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch} loading={searching} className="!rounded-lg">搜索</Button>
      </div>

      {searchResult && (
        <div className="space-y-4">
          <Card title="生成答案" extra={<Text type="secondary">{formatDuration(searchResult.latency_ms)} · ${(searchResult.cost_usd || 0).toFixed(6)}</Text>}>
            <Paragraph className="!mb-0 whitespace-pre-wrap">{searchResult.answer}</Paragraph>
          </Card>
          <Card title={<span className="flex items-center gap-2"><DatabaseOutlined /> 来源 ({searchResult.sources?.length || 0})</span>}>
            <div className="space-y-3">
              {searchResult.sources?.map((source: any, idx: number) => (
                <div key={idx} className="border rounded-lg p-3">
                  <div className="flex justify-between items-center mb-2">
                    <Text strong>{source.document_name || source.document_id}</Text>
                    <Tag color="blue">{Math.round((source.score || 0) * 100)}% 匹配</Tag>
                  </div>
                  <Text className="text-sm text-gray-600">{source.content?.substring(0, 200)}...</Text>
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
      <Dragger beforeUpload={handleUpload} showUploadList={false} accept=".pdf,.docx,.md,.txt,.csv,.json">
        <p className="ant-upload-drag-icon"><InboxOutlined /></p>
        <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
        <p className="ant-upload-hint">支持 PDF、TXT、Markdown、CSV、JSON 和 DOCX 文件（后端解析 + 分块 + 向量化）</p>
      </Dragger>
      <Collapse ghost items={[{
        key: 'chunking', label: <span><InfoCircleOutlined className="mr-2" />分块与检索策略说明</span>,
        children: (
          <div className="text-sm space-y-2">
            <Alert type="info" showIcon message="真实 RAG 链路" description="文档上传后由后端完成：解析 → 分块 → 向量化 → 索引。检索时走 dense 向量相似度，支持重排序。" />
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="分块大小">约 1000 字符/块（可配置 chunk_size/chunk_overlap）</Descriptions.Item>
              <Descriptions.Item label="Embedding">BGE-M3（1024维，未安装时降级为 hash embedding）</Descriptions.Item>
              <Descriptions.Item label="向量库">Milvus（未连接时降级为 InMemoryVectorStore）</Descriptions.Item>
              <Descriptions.Item label="生成">DeepSeek 生成（未配置时降级为抽取式摘要）</Descriptions.Item>
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
          <Button type="link" danger size="small" onClick={() => handleDelete(record.document_id)}>删除</Button>
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
