import {
  Table,
  Tag,
  Button,
  Space,
  Popconfirm,
  Empty,
  Spin,
  Typography,
  message,
} from 'antd';
import {
  LinkOutlined,
  DisconnectOutlined,
  ReloadOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ApiOutlined,
} from '@ant-design/icons';
import { useEffect } from 'react';
import { useMCPStore } from '@/store/mcpStore';
import { StatusBadge } from '@/components/common/StatusBadge';

const { Text } = Typography;

const statusToBadgeStatus = (
  status: 'connected' | 'disconnected' | 'error',
): 'healthy' | 'unknown' | 'failed' => {
  switch (status) {
    case 'connected':
      return 'healthy';
    case 'disconnected':
      return 'unknown';
    case 'error':
      return 'failed';
    default:
      return 'unknown';
  }
};

const transportColorMap: Record<string, string> = {
  stdio: 'blue',
  sse: 'green',
  http: 'orange',
};

export default function ServerList() {
  const {
    servers,
    serversLoading,
    fetchServers,
    connectServer,
    disconnectServer,
    error,
    clearError,
  } = useMCPStore();

  useEffect(() => {
    fetchServers();
  }, [fetchServers]);

  useEffect(() => {
    if (error) {
      message.error(error);
      clearError();
    }
  }, [error, clearError]);

  const handleConnect = async (name: string) => {
    try {
      await connectServer(name);
      message.success(`已连接到 ${name}`);
    } catch {
      message.error(`连接 ${name} 失败`);
    }
  };

  const handleDisconnect = async (name: string) => {
    try {
      await disconnectServer(name);
      message.success(`已断开与 ${name} 的连接`);
    } catch {
      message.error(`断开 ${name} 连接失败`);
    }
  };

  const columns = [
    {
      title: '服务器名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string) => (
        <div className="flex items-center gap-2">
          <ApiOutlined className="text-blue-500" />
          <Text strong>{name}</Text>
        </div>
      ),
    },
    {
      title: '传输方式',
      dataIndex: 'transport',
      key: 'transport',
      width: 140,
      render: (transport: string) => (
        <Tag color={transportColorMap[transport] || 'default'}>
          {transport.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 150,
      render: (status: 'connected' | 'disconnected' | 'error') => (
        <StatusBadge status={statusToBadgeStatus(status)} />
      ),
    },
    {
      title: '工具数',
      dataIndex: 'toolCount',
      key: 'toolCount',
      width: 120,
      align: 'center' as const,
      render: (count: number) => (
        <Tag color={count > 0 ? 'purple' : 'default'} className="!px-3">
          {count ?? 0}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 260,
      render: (_: unknown, record: { name: string; status: string }) => (
        <Space size="small">
          <Button
            type="primary"
            ghost
            icon={<LinkOutlined />}
            size="small"
            disabled={record.status === 'connected'}
            onClick={() => handleConnect(record.name)}
            className="!rounded-lg"
          >
            连接
          </Button>
          <Popconfirm
            title="断开此服务器？"
            description={`确认断开与 ${record.name} 的连接？`}
            onConfirm={() => handleDisconnect(record.name)}
            okText="是"
            cancelText="否"
            okButtonProps={{ danger: true }}
          >
            <Button
              danger
              icon={<DisconnectOutlined />}
              size="small"
              disabled={record.status === 'disconnected'}
              className="!rounded-lg"
            >
              断开
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const expandedRowRender = (record: {
    name: string;
    transport: string;
    status: string;
    id?: string;
  }) => (
    <div className="py-3 px-8">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <Text type="secondary" className="text-xs uppercase tracking-wide">
            服务器 ID
          </Text>
          <div>
            <Text code>{record.id || record.name}</Text>
          </div>
        </div>
        <div>
          <Text type="secondary" className="text-xs uppercase tracking-wide">
            传输方式
          </Text>
          <div>
            <Tag color={transportColorMap[record.transport] || 'default'}>
              {record.transport?.toUpperCase()}
            </Tag>
          </div>
        </div>
        <div>
          <Text type="secondary" className="text-xs uppercase tracking-wide">
            状态
          </Text>
          <div className="flex items-center gap-2 mt-1">
            {record.status === 'connected' ? (
              <CheckCircleOutlined className="text-green-500" />
            ) : record.status === 'error' ? (
              <CloseCircleOutlined className="text-red-500" />
            ) : (
              <CloseCircleOutlined className="text-gray-400" />
            )}
            <Text>{record.status}</Text>
          </div>
        </div>
      </div>
      <div className="mt-3">
        <Text type="secondary" className="text-xs uppercase tracking-wide">
          环境变量
        </Text>
        <div className="mt-1">
          <Text type="secondary">按服务器部署配置</Text>
        </div>
      </div>
    </div>
  );

  if (serversLoading && servers.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Spin size="large" tip="加载服务器中..." />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end">
        <Button
          icon={<ReloadOutlined />}
          onClick={() => fetchServers()}
          loading={serversLoading}
          size="small"
          className="!rounded-lg"
        >
          刷新
        </Button>
      </div>

      <Table
        dataSource={servers}
        columns={columns}
        rowKey={(record) => record.id || record.name}
        loading={serversLoading}
        locale={{
          emptyText: (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="未配置 MCP 服务器"
            />
          ),
        }}
        pagination={false}
        expandable={{
          expandedRowRender,
          rowExpandable: () => true,
        }}
        className="mcp-server-table"
        rowClassName={(record) =>
          record.status === 'connected'
            ? 'bg-green-50/30 dark:bg-green-950/10'
            : record.status === 'error'
              ? 'bg-red-50/30 dark:bg-red-950/10'
              : ''
        }
      />
    </div>
  );
}
