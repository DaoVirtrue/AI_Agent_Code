import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Card, Table, Typography, Row, Col, Statistic, Tag, Button, Space, Tabs, DatePicker, Select, Input } from 'antd';
import {
  TeamOutlined,
  ApiOutlined,
  AuditOutlined,
  KeyOutlined,
  UserOutlined,
  PlusOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { useAppStore, useAdminStore } from '@/store';
import { formatDate, formatNumber } from '@/utils/format';
import { TIER_LABELS } from '@/utils/constants';

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;

export function AdminPage() {
  const location = useLocation();
  const setBreadcrumbs = useAppStore((s) => s.setBreadcrumbs);
  const [activeTab, setActiveTab] = useState('overview');
  const [tenants, setTenants] = useState<TenantInfo[]>([]);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [loadingAudit, setLoadingAudit] = useState(false);
  const [auditDateRange, setAuditDateRange] = useState<[string, string] | null>(null);
  const [auditUser, setAuditUser] = useState('');
  const [auditAction, setAuditAction] = useState<string | undefined>(undefined);

  useEffect(() => {
    setBreadcrumbs([{ title: '管理' }]);
  }, [setBreadcrumbs]);

  useEffect(() => {
    // Set active tab based on URL
    if (location.pathname === '/admin/tenants') setActiveTab('tenants');
    else if (location.pathname === '/admin/audit') setActiveTab('audit');
    else if (location.pathname === '/admin/keys') setActiveTab('keys');
    else setActiveTab('overview');
  }, [location.pathname]);

  useEffect(() => {
    if (activeTab === 'tenants') loadTenants();
    if (activeTab === 'audit') loadAuditLogs();
  }, [activeTab]);

  const adminStore = useAdminStore();
  const storeTenants = adminStore.tenants;
  const storeAuditLogs = adminStore.auditLogs;
  const storeApiKeys = adminStore.apiKeys;

  const loadTenants = async () => {
    await adminStore.fetchTenants();
  };

  const loadAuditLogs = async () => {
    setLoadingAudit(true);
    await adminStore.fetchAuditLogs({ page: 1, pageSize: 20 });
    setLoadingAudit(false);
  };

  // Sync store state to local state
  const [localKeys, setLocalKeys] = useState<any[]>([]);
  useEffect(() => { setTenants(storeTenants); }, [storeTenants]);
  useEffect(() => { setAuditLogs(storeAuditLogs); }, [storeAuditLogs]);
  useEffect(() => { setLocalKeys(storeApiKeys); }, [storeApiKeys]);
  useEffect(() => { adminStore.fetchApiKeys(); }, []);

  const tenantColumns = [
    { title: '名称', dataIndex: 'name', key: 'name', render: (t: string) => <Text strong>{t}</Text> },
    { title: '等级', dataIndex: 'tier', key: 'tier', render: (tier: string) => <Tag color={tier === 'enterprise' ? 'purple' : tier === 'pro' ? 'blue' : 'default'}>{TIER_LABELS[tier] || tier}</Tag> },
    { title: '用户数', dataIndex: 'userCount', key: 'userCount', render: (v: number) => <Text>{v}</Text> },
    { title: '创建时间', dataIndex: 'createdAt', key: 'createdAt', render: (d: string) => formatDate(d) },
    { title: '操作', key: 'actions', render: () => <Button size="small" type="link">管理</Button> },
  ];

  const auditColumns = [
    { title: '时间', dataIndex: 'timestamp', key: 'timestamp', render: (d: string) => formatDate(d) },
    { title: '用户', dataIndex: 'user', key: 'user' },
    { title: '操作', dataIndex: 'action', key: 'action', render: (a: string) => <Tag>{a}</Tag> },
    { title: '资源', dataIndex: 'resource', key: 'resource' },
    { title: '状态', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={s === 'success' ? 'green' : 'red'}>{s === 'success' ? '成功' : s}</Tag> },
  ];

  const overviewTab = (
    <div className="space-y-6 animate-fade-in">
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic title="用户总数" value={181} prefix={<UserOutlined />} />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic title="租户" value={3} prefix={<TeamOutlined />} />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic title="今日 API 请求" value={1560} prefix={<ApiOutlined />} />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic title="API Keys" value={2} prefix={<KeyOutlined />} />
          </Card>
        </Col>
      </Row>
      <Card title="系统健康">
        <div className="space-y-2">
          <div className="flex justify-between items-center"><Text>API Gateway</Text><Tag color="green">正常运行</Tag></div>
          <div className="flex justify-between items-center"><Text>数据库</Text><Tag color="green">正常运行</Tag></div>
          <div className="flex justify-between items-center"><Text>Redis 缓存</Text><Tag color="green">正常运行</Tag></div>
          <div className="flex justify-between items-center"><Text>MCP 服务器</Text><Tag color="default">未配置</Tag></div>
        </div>
      </Card>
    </div>
  );

  const tenantsTab = (
    <Card title="租户" extra={<Button type="primary" size="small" icon={<PlusOutlined />}>添加租户</Button>}>
      <Table dataSource={tenants} columns={tenantColumns} rowKey="id" pagination={false} />
    </Card>
  );

  const auditTab = (
    <Card title="审计日志">
      <div className="flex gap-3 mb-4 flex-wrap">
        <RangePicker
          size="small"
          value={auditDateRange as any}
          onChange={(dates) => setAuditDateRange(dates as [string, string] | null)}
        />
        <Input
          placeholder="用户"
          size="small"
          className="w-32"
          value={auditUser}
          onChange={(e) => setAuditUser(e.target.value)}
        />
        <Select
          placeholder="操作"
          size="small"
          className="w-32"
          allowClear
          value={auditAction}
          onChange={setAuditAction}
          options={[
            { value: 'login', label: '登录' },
            { value: 'chat', label: '对话' },
            { value: 'admin', label: '管理' },
          ]}
        />
        <Button type="primary" size="small" icon={<SearchOutlined />}>搜索</Button>
      </div>
      <Table dataSource={auditLogs} columns={auditColumns} rowKey="id" loading={loadingAudit} pagination={{ pageSize: 15 }} />
    </Card>
  );

  const keysTab = (
    <Card title="API Keys" extra={<Button type="primary" size="small" icon={<PlusOutlined />}>生成 Key</Button>}>
      <Table
        dataSource={localKeys}
        columns={[
          { title: '名称', dataIndex: 'name', key: 'name', render: (t: string) => <Text strong>{t}</Text> },
          { title: '密钥', dataIndex: 'key', key: 'key', render: (k: string) => <Text code className="!text-xs">{k}</Text> },
          { title: '创建时间', dataIndex: 'created', key: 'created' },
          { title: '最后使用', dataIndex: 'lastUsed', key: 'lastUsed' },
          { title: '状态', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={s === 'active' ? 'green' : 'red'}>{s}</Tag> },
          { title: '操作', key: 'actions', render: () => <Button size="small" type="link" danger>吊销</Button> },
        ]}
        rowKey="id"
        pagination={false}
      />
    </Card>
  );

  const tabItems = [
    { key: 'overview', label: '概览', children: overviewTab },
    { key: 'tenants', label: '租户', children: tenantsTab },
    { key: 'audit', label: '审计日志', children: auditTab },
    { key: 'keys', label: 'API Keys', children: keysTab },
  ];

  return (
    <div className="space-y-4 animate-fade-in">
      <Title level={4} className="!mb-0">管理面板</Title>
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />
    </div>
  );
}
