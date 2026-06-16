import {
  Table, DatePicker, Select, Input, Space, Tag, Typography,
  Card, Collapse, Button, Tooltip, Spin, Empty, message,
} from 'antd';
import {
  SearchOutlined, FilterOutlined, ReloadOutlined,
  ExpandAltOutlined, CompressOutlined,
} from '@ant-design/icons';
import { useEffect, useState, useCallback } from 'react';
import { useAdminStore } from '@/store/adminStore';
import { formatDate, formatDateRelative } from '@/utils/format';
import type { ColumnsType } from 'antd/es/table';

const { RangePicker } = DatePicker;
const { Text, Paragraph } = Typography;

interface AuditRecord {
  id: string;
  timestamp: string;
  tenant: string;
  user: string;
  action: string;
  details: string | object;
  status: string;
}

const actionColorMap: Record<string, string> = {
  login: 'green',
  create_key: 'blue',
  rate_limited: 'red',
  update_tenant: 'orange',
  api_call: 'default',
  delete: 'red',
};

const statusColorMap: Record<string, string> = {
  success: 'green',
  blocked: 'red',
  error: 'red',
};

const actionOptions = [
  { value: 'all', label: '全部事件' },
  { value: 'login', label: '登录' },
  { value: 'create_key', label: '创建密钥' },
  { value: 'rate_limited', label: '限流' },
  { value: 'update_tenant', label: '更新租户' },
  { value: 'api_call', label: 'API 调用' },
  { value: 'delete', label: '删除' },
];

const AuditLog = () => {
  const {
    auditLogs, auditLoading, auditTotal, auditPage, auditPageSize,
    tenants, error,
    fetchAuditLogs, fetchTenants, clearError,
  } = useAdminStore();

  const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([]);
  const [dateRange, setDateRange] = useState<[any, any] | null>(null);
  const [eventType, setEventType] = useState<string>('all');
  const [tenantFilter, setTenantFilter] = useState<string | undefined>(undefined);
  const [searchText, setSearchText] = useState<string>('');

  const loadLogs = useCallback(
    (params: Record<string, unknown> = {}) => {
      fetchAuditLogs({
        page: auditPage,
        pageSize: auditPageSize,
        ...params,
      });
    },
    [fetchAuditLogs, auditPage, auditPageSize],
  );

  useEffect(() => {
    fetchTenants();
  }, [fetchTenants]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  useEffect(() => {
    if (error) {
      message.error(error);
      clearError();
    }
  }, [error, clearError]);

  const handleApplyFilters = () => {
    const params: Record<string, unknown> = {};
    params.page = 1;

    if (dateRange?.[0] && dateRange?.[1]) {
      params.startDate = dateRange[0].toISOString();
      params.endDate = dateRange[1].toISOString();
    }
    if (eventType && eventType !== 'all') {
      params.action = eventType;
    }
    if (tenantFilter) {
      params.tenant = tenantFilter;
    }
    if (searchText.trim()) {
      params.search = searchText.trim();
    }

    loadLogs(params);
  };

  const handleTableChange = (pagination: { current?: number; pageSize?: number }) => {
    const params: Record<string, unknown> = {
      page: pagination.current,
      pageSize: pagination.pageSize,
    };

    if (dateRange?.[0] && dateRange?.[1]) {
      params.startDate = dateRange[0].toISOString();
      params.endDate = dateRange[1].toISOString();
    }
    if (eventType && eventType !== 'all') {
      params.action = eventType;
    }
    if (tenantFilter) {
      params.tenant = tenantFilter;
    }
    if (searchText.trim()) {
      params.search = searchText.trim();
    }

    loadLogs(params);
  };

  const handleClearFilters = () => {
    setDateRange(null);
    setEventType('all');
    setTenantFilter(undefined);
    setSearchText('');
    loadLogs({ page: 1 });
  };

  const renderDetails = (details: string | object) => {
    if (!details) return <Text type="secondary">无详情信息。</Text>;

    let parsed: unknown = details;
    if (typeof details === 'string') {
      try {
        parsed = JSON.parse(details);
      } catch {
        parsed = details;
      }
    }

    if (typeof parsed === 'object' && parsed !== null) {
      return (
        <pre className="bg-gray-50 p-3 rounded-md text-xs overflow-auto max-h-60 whitespace-pre-wrap">
          {JSON.stringify(parsed, null, 2)}
        </pre>
      );
    }

    return <Text>{String(parsed)}</Text>;
  };

  const columns: ColumnsType<AuditRecord> = [
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 180,
      render: (ts: string) => (
        <Tooltip title={formatDateRelative(ts)}>
          <Text>{formatDate(ts)}</Text>
        </Tooltip>
      ),
      sorter: (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
      defaultSortOrder: 'descend',
    },
    {
      title: '租户',
      dataIndex: 'tenant',
      key: 'tenant',
      width: 140,
      render: (tenant: string) => <Tag>{tenant}</Tag>,
    },
    {
      title: '用户',
      dataIndex: 'user',
      key: 'user',
      width: 160,
      render: (user: string) => <Text strong>{user}</Text>,
    },
    {
      title: '操作',
      dataIndex: 'action',
      key: 'action',
      width: 140,
      render: (action: string) => (
        <Tag color={actionColorMap[action] || 'default'}>{action}</Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={statusColorMap[status] || 'default'}>{status}</Tag>
      ),
    },
  ];

  const expandedRowRender = (record: AuditRecord) => (
    <div>
      <Paragraph type="secondary" className="!mb-2">
        详情:
      </Paragraph>
      {renderDetails(record.details)}
    </div>
  );

  const onExpand = (expanded: boolean, record: AuditRecord) => {
    if (expanded) {
      setExpandedRowKeys((prev) => [...prev, record.id]);
    } else {
      setExpandedRowKeys((prev) => prev.filter((key) => key !== record.id));
    }
  };

  return (
    <div className="pt-4">
      {/* Filter Bar */}
      <Card size="small" className="mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <RangePicker
            value={dateRange as any}
            onChange={(dates) => setDateRange(dates as [any, any] | null)}
            placeholder={['开始日期', '结束日期']}
            allowClear
          />

          <Select
            value={eventType}
            onChange={setEventType}
            options={actionOptions}
            style={{ minWidth: 140 }}
            placeholder="事件类型"
          />

          <Select
            value={tenantFilter}
            onChange={setTenantFilter}
            allowClear
            placeholder="选择租户"
            style={{ minWidth: 160 }}
            options={[
              ...(tenants || []).map((t: { id: string; name: string; slug: string }) => ({
                value: t.slug || t.name,
                label: t.name,
              })),
            ]}
            showSearch
            optionFilterProp="label"
          />

          <Input.Search
            placeholder="搜索日志..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onSearch={handleApplyFilters}
            enterButton={<SearchOutlined />}
            style={{ maxWidth: 260 }}
            allowClear
          />

          <Space>
            <Button
              type="primary"
              icon={<FilterOutlined />}
              onClick={handleApplyFilters}
            >
              应用筛选
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={handleClearFilters}
            >
              清除
            </Button>
          </Space>
        </div>
      </Card>

      {/* Expand / Collapse All */}
      <div className="flex items-center justify-between mb-3">
        <Text type="secondary">
          共找到 {auditTotal} 条日志
        </Text>
        <Space>
          <Button
            size="small"
            icon={<ExpandAltOutlined />}
            onClick={() => {
              const allIds = (auditLogs || []).map((log: AuditRecord) => log.id);
              setExpandedRowKeys(allIds);
            }}
            disabled={(auditLogs || []).length === 0}
          >
            展开全部
          </Button>
          <Button
            size="small"
            icon={<CompressOutlined />}
            onClick={() => setExpandedRowKeys([])}
            disabled={expandedRowKeys.length === 0}
          >
            收起全部
          </Button>
        </Space>
      </div>

      {/* Table */}
      <Spin spinning={auditLoading}>
        {(auditLogs || []).length === 0 && !auditLoading ? (
          <Empty description="暂无审计日志。" className="py-12" />
        ) : (
          <Table
            columns={columns}
            dataSource={auditLogs}
            rowKey="id"
            expandable={{
              expandedRowRender,
              expandedRowKeys,
              onExpand,
              rowExpandable: (record: AuditRecord) =>
                !!record.details &&
                (typeof record.details === 'string'
                  ? record.details.length > 0
                  : Object.keys(record.details || {}).length > 0),
            }}
            pagination={{
              current: auditPage,
              pageSize: auditPageSize,
              total: auditTotal,
              showSizeChanger: true,
              showTotal: (total, range) =>
                `${range[0]}-${range[1]} / ${total} 条`,
            }}
            onChange={handleTableChange}
            scroll={{ x: 900 }}
          />
        )}
      </Spin>
    </div>
  );
};

export default AuditLog;
