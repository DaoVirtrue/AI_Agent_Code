import { useEffect, useState, useMemo, useCallback } from 'react';
import {
  Table,
  Input,
  Button,
  Tag,
  Space,
  Typography,
  Spin,
  Empty,
  Alert,
  Popconfirm,
  Card,
} from 'antd';
import {
  DeleteOutlined,
  ReloadOutlined,
  FileTextOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { useRAGStore } from '@/store/ragStore';
import { formatBytes, formatDate } from '@/utils/format';
import { StatusBadge } from '@/components/common/StatusBadge';
import type { ColumnsType } from 'antd/es/table';

const { Text } = Typography;

interface DocumentRow {
  id: string;
  filename: string;
  file_type: string;
  status: 'indexed' | 'processing' | 'failed';
  chunk_count: number;
  file_size_bytes: number;
  upload_date: string;
}

const fileTypeColorMap: Record<string, string> = {
  pdf: 'red',
  docx: 'blue',
  md: 'green',
  txt: 'default',
};

function mapStatusToBadgeStatus(status: 'indexed' | 'processing' | 'failed'): 'completed' | 'processing' | 'failed' {
  switch (status) {
    case 'indexed':
      return 'completed';
    case 'processing':
      return 'processing';
    case 'failed':
      return 'failed';
    default:
      return 'failed';
  }
}

export default function KnowledgeBase() {
  const { documents, documentsLoading, error, fetchDocuments, deleteDoc, clearError } = useRAGStore();

  const [searchText, setSearchText] = useState<string>('');

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  useEffect(() => {
    if (error) {
      clearError();
    }
  }, [error, clearError]);

  const handleRefresh = useCallback(() => {
    setSearchText('');
    fetchDocuments();
  }, [fetchDocuments]);

  const handleDelete = useCallback(
    async (documentId: string) => {
      await deleteDoc(documentId);
    },
    [deleteDoc],
  );

  const handleSearch = useCallback((value: string) => {
    setSearchText(value.trim().toLowerCase());
  }, []);

  const filteredDocuments = useMemo(() => {
    if (!searchText) return documents;
    return documents.filter((doc) =>
      doc.filename.toLowerCase().includes(searchText),
    );
  }, [documents, searchText]);

  const columns: ColumnsType<DocumentRow> = [
    {
      title: '文档名称',
      dataIndex: 'filename',
      key: 'filename',
      sorter: (a, b) => a.filename.localeCompare(b.filename),
      render: (filename: string) => (
        <Space>
          <FileTextOutlined style={{ color: '#1677ff' }} />
          <Text>{filename}</Text>
        </Space>
      ),
    },
    {
      title: '类型',
      dataIndex: 'file_type',
      key: 'file_type',
      width: 120,
      render: (fileType: string) => (
        <Tag color={fileTypeColorMap[fileType?.toLowerCase()] || 'default'}>
          {fileType?.toUpperCase() || '未知'}
        </Tag>
      ),
    },
    {
      title: '分块数',
      dataIndex: 'chunk_count',
      key: 'chunk_count',
      width: 130,
      align: 'center',
      sorter: (a, b) => a.chunk_count - b.chunk_count,
      render: (count: number) => (
        <Text>{count}</Text>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 150,
      align: 'center',
      render: (status: 'indexed' | 'processing' | 'failed') => (
        <StatusBadge status={mapStatusToBadgeStatus(status)} />
      ),
    },
    {
      title: '大小',
      dataIndex: 'file_size_bytes',
      key: 'file_size_bytes',
      width: 120,
      align: 'right',
      sorter: (a, b) => a.file_size_bytes - b.file_size_bytes,
      render: (bytes: number) => (
        <Text>{formatBytes(bytes)}</Text>
      ),
    },
    {
      title: '上传日期',
      dataIndex: 'upload_date',
      key: 'upload_date',
      width: 180,
      sorter: (a, b) => new Date(a.upload_date).getTime() - new Date(b.upload_date).getTime(),
      defaultSortOrder: 'descend',
      render: (date: string) => (
        <Text>{formatDate(date)}</Text>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 90,
      align: 'center',
      fixed: 'right',
      render: (_: unknown, record: DocumentRow) => (
        <Popconfirm
          title="删除文档"
          description={`确认删除 "${record.filename}"？`}
          onConfirm={() => handleDelete(record.id)}
          okText="删除"
          cancelText="取消"
          okButtonProps={{ danger: true }}
          placement="left"
        >
          <Button
            type="text"
            danger
            icon={<DeleteOutlined />}
            size="small"
            aria-label={`删除 ${record.filename}`}
          />
        </Popconfirm>
      ),
    },
  ];

  return (
    <div className="p-4 space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Input.Search
          placeholder="搜索文档..."
          allowClear
          onSearch={handleSearch}
          onChange={(e) => {
            if (!e.target.value) {
              setSearchText('');
            }
          }}
          style={{ maxWidth: 400 }}
          prefix={<SearchOutlined />}
          className="flex-1"
        />
        <Button
          icon={<ReloadOutlined />}
          onClick={handleRefresh}
          loading={documentsLoading}
          className="!rounded-lg"
        >
          刷新
        </Button>
      </div>

      {/* Error State */}
      {error && (
        <Alert
          message="加载文档出错"
          description={error}
          type="error"
          showIcon
          closable
          onClose={clearError}
          className="!rounded-lg"
        />
      )}

      {/* Table */}
      <Spin spinning={documentsLoading}>
        <Card className="!rounded-xl" bodyStyle={{ padding: 0 }}>
          <Table<DocumentRow>
            dataSource={filteredDocuments}
            columns={columns}
            rowKey="id"
            loading={false}
            size="middle"
            scroll={{ x: 900 }}
            pagination={{
              pageSize: 10,
              showSizeChanger: true,
              pageSizeOptions: ['10', '20', '50'],
              showTotal: (total, range) =>
                `${range[0]}-${range[1]} / ${total} 个文档`,
            }}
            locale={{
              emptyText: documentsLoading ? (
                <div className="py-8" />
              ) : searchText ? (
                <Empty description={`没有匹配 "${searchText}" 的文档`} />
              ) : (
                <Empty description="暂无上传文档，请前往上传页面添加文档。" />
              ),
            }}
            rowClassName={(_, index) =>
              index % 2 === 0 ? 'bg-white dark:bg-gray-900' : 'bg-gray-50 dark:bg-gray-800'
            }
          />
        </Card>
      </Spin>

      {/* Summary Footer */}
      {documents.length > 0 && !documentsLoading && (
        <Text type="secondary" className="text-sm block text-right">
          {filteredDocuments.length} / {documents.length} 个文档
          {searchText ? '（已筛选）' : ''}
        </Text>
      )}
    </div>
  );
}
