import { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Input,
  Button,
  Select,
  Typography,
  Space,
  Tag,
  Empty,
  Skeleton,
  Collapse,
  Progress,
  Alert,
  Divider,
} from 'antd';
import {
  SearchOutlined,
  LinkOutlined,
  ThunderboltOutlined,
  DollarOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import { useRAGStore } from '@/store/ragStore';
import { formatDuration, formatCurrency, truncateText } from '@/utils/format';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const { TextArea } = Input;
const { Text, Title, Paragraph } = Typography;

const TOP_K_OPTIONS = [
  { value: 1, label: '1' },
  { value: 3, label: '3' },
  { value: 5, label: '5' },
  { value: 10, label: '10' },
  { value: 20, label: '20' },
];

export default function SearchTest() {
  const {
    searchResults,
    searchAnswer,
    searchLatency,
    searchCost,
    searchLoading,
    error,
    searchRag,
    clearSearch,
    clearError,
  } = useRAGStore();

  const [query, setQuery] = useState<string>('');
  const [topK, setTopK] = useState<number>(5);
  const [hasSearched, setHasSearched] = useState<boolean>(false);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearSearch();
    };
  }, [clearSearch]);

  // Show store errors
  useEffect(() => {
    if (error) {
      clearError();
    }
  }, [error, clearError]);

  const handleSearch = useCallback(async () => {
    const trimmedQuery = query.trim();
    if (!trimmedQuery) return;

    setHasSearched(true);
    await searchRag(trimmedQuery, topK);
  }, [query, topK, searchRag]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        handleSearch();
      }
    },
    [handleSearch],
  );

  const handleClear = useCallback(() => {
    setQuery('');
    setTopK(5);
    setHasSearched(false);
    clearSearch();
  }, [clearSearch]);

  return (
    <div className="p-4 space-y-6">
      {/* Search Form */}
      <Card
        title={
          <Space>
            <SearchOutlined />
            <span>检索查询</span>
          </Space>
        }
        className="!rounded-xl"
      >
        <Space direction="vertical" className="w-full" size="middle">
          <div className="flex items-end gap-4 flex-wrap">
            <div className="flex-1 min-w-[300px]">
              <TextArea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="输入查询内容，检索知识库..."
                autoSize={{ minRows: 4, maxRows: 8 }}
                disabled={searchLoading}
                className="!rounded-lg"
              />
            </div>
          </div>

          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <Text type="secondary" className="whitespace-nowrap text-sm">
                检索数量:
              </Text>
              <Select
                value={topK}
                onChange={(value) => setTopK(value)}
                options={TOP_K_OPTIONS}
                style={{ width: 80 }}
                size="middle"
                disabled={searchLoading}
              />
            </div>

            <Space>
              <Button
                type="primary"
                icon={<SearchOutlined />}
                onClick={handleSearch}
                loading={searchLoading}
                disabled={!query.trim()}
                className="!rounded-lg"
                size="middle"
              >
                搜索
              </Button>
              <Button
                onClick={handleClear}
                disabled={searchLoading}
                className="!rounded-lg"
                size="middle"
              >
                清空
              </Button>
            </Space>
          </div>

          <Text type="secondary" className="text-xs">
            提示：按 Ctrl+Enter 搜索
          </Text>
        </Space>
      </Card>

      {/* Loading State */}
      {searchLoading && (
        <Card className="!rounded-xl">
          <Skeleton active paragraph={{ rows: 3 }} className="mb-4" />
          <Space direction="vertical" className="w-full" size="small">
            <Skeleton.Button active block size="large" />
            <Skeleton.Button active block size="large" />
            <Skeleton.Button active block size="large" />
          </Space>
        </Card>
      )}

      {/* Error Display */}
      {error && !searchLoading && (
        <Alert
          message="搜索出错"
          description={error}
          type="error"
          showIcon
          closable
          onClose={clearError}
          className="!rounded-lg"
        />
      )}

      {/* Empty State (before first search) */}
      {!hasSearched && !searchLoading && !searchAnswer && searchResults.length === 0 && (
        <Card className="!rounded-xl">
          <Empty
            description={
              <span className="text-gray-400">
                输入查询内容以检索知识库
              </span>
            }
            className="py-8"
          />
        </Card>
      )}

      {/* Results */}
      {hasSearched && !searchLoading && (searchAnswer || searchResults.length > 0) && (
        <div className="space-y-4">
          {/* Generated Answer */}
          {searchAnswer && (
            <Card
              title={
                <Space>
                  <ThunderboltOutlined style={{ color: '#1677ff' }} />
                  <span>生成答案</span>
                </Space>
              }
              extra={
                <Space size="small" wrap>
                  <Tag icon={<ClockCircleOutlined />} color="blue">
                    {formatDuration(searchLatency)}
                  </Tag>
                  {searchCost > 0 && (
                    <Tag icon={<DollarOutlined />} color="green">
                      {formatCurrency(searchCost)}
                    </Tag>
                  )}
                </Space>
              }
              className="!rounded-xl"
            >
              <div className="markdown-content prose prose-sm max-w-none dark:prose-invert">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {searchAnswer}
                </ReactMarkdown>
              </div>
            </Card>
          )}

          {/* Sources */}
          {searchResults.length > 0 && (
            <Card
              title={
                <Space>
                  <LinkOutlined />
                  <span>来源文档 ({searchResults.length})</span>
                </Space>
              }
              className="!rounded-xl"
            >
              <Collapse
                size="small"
                accordion={false}
                items={searchResults.map((source, idx) => ({
                  key: idx.toString(),
                  label: (
                    <div className="flex items-center justify-between gap-3 pr-2">
                      <Text
                        strong
                        className="truncate max-w-[70%]"
                        title={source.sourceName}
                      >
                        {source.sourceName || `来源 ${idx + 1}`}
                      </Text>
                      <Space size="small" className="flex-shrink-0">
                        <Tag
                          color={
                            source.score >= 0.8
                              ? 'green'
                              : source.score >= 0.5
                                ? 'orange'
                                : 'red'
                          }
                          className="text-xs"
                        >
                          {Math.round(source.score * 100)}% 匹配
                        </Tag>
                        <Tag className="text-xs">
                          分块: {source.chunkId}
                        </Tag>
                      </Space>
                    </div>
                  ),
                  children: (
                    <div className="space-y-3">
                      <div className="flex items-center gap-2">
                        <Text type="secondary" className="text-xs">
                          相关度:
                        </Text>
                        <Progress
                          percent={Math.round(source.score * 100)}
                          size="small"
                          style={{ width: 200 }}
                          strokeColor={
                            source.score >= 0.8
                              ? '#52c41a'
                              : source.score >= 0.5
                                ? '#faad14'
                                : '#f5222d'
                          }
                          showInfo={false}
                        />
                        <Text className="text-xs">{Math.round(source.score * 100)}%</Text>
                      </div>
                      <div className="text-xs text-gray-400">
                        <Text type="secondary">文档: {source.documentId}</Text>
                        {' | '}
                        <Text type="secondary">分块 ID: {source.chunkId}</Text>
                      </div>
                      <Divider className="!my-2" />
                      <Paragraph
                        className="!mb-0 text-sm bg-gray-50 dark:bg-gray-800 p-3 rounded-lg"
                        style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
                      >
                        {truncateText(source.content, 200)}
                        {source.content.length > 200 && (
                          <Text type="secondary" className="block mt-1 text-xs">
                            （内容已截断 - 仅显示前 200 个字符）
                          </Text>
                        )}
                      </Paragraph>
                    </div>
                  ),
                }))}
                className="bg-transparent"
              />
            </Card>
          )}

          {/* If we have no answer but have sources */}
          {!searchAnswer && searchResults.length > 0 && (
            <Alert
              message="未生成答案"
              description="搜索返回了相关来源，但未生成答案。请尝试重新表述查询内容。"
              type="info"
              showIcon
              className="!rounded-lg"
            />
          )}
        </div>
      )}

      {/* No Results State */}
      {hasSearched && !searchLoading && !searchAnswer && searchResults.length === 0 && (
        <Card className="!rounded-xl">
          <Empty
            description={
              <span className="text-gray-400">
                未找到匹配结果。请尝试其他关键词或上传更多文档。
              </span>
            }
            className="py-8"
          />
        </Card>
      )}
    </div>
  );
}
