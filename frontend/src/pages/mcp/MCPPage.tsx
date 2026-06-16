import { useEffect, useState } from 'react';
import { Card, Table, Button, Drawer, Input, Form, Typography, Space, Tag, Empty, Spin, message } from 'antd';
import { PlusOutlined, LinkOutlined, ToolOutlined } from '@ant-design/icons';
import { useAppStore, useMCPStore } from '@/store';
import { StatusBadge } from '@/components/common/StatusBadge';

const { Title, Text } = Typography;
const { TextArea } = Input;

export function MCPPage() {
  const setBreadcrumbs = useAppStore((s) => s.setBreadcrumbs);
  const storeServers = useMCPStore((s) => s.servers);
  const { connectServer, disconnectServer, fetchServers } = useMCPStore();
  const [servers, setServers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [form] = Form.useForm();

  useEffect(() => {
    setBreadcrumbs([{ title: 'MCP' }]);
  }, [setBreadcrumbs]);

  useEffect(() => { fetchServers(); }, []);
  useEffect(() => { setServers(storeServers); setLoading(false); }, [storeServers]);
  const handleConnect = (name: string) => { connectServer(name); };
  const handleDisconnect = (name: string) => { disconnectServer(name); };

  const handleAddServer = () => {
    form.resetFields();
    setDrawerOpen(true);
  };

  const handleSubmit = () => {
    form.validateFields().then((values) => {
      const args = values.args ? values.args.split(',').map((s: string) => s.trim()).filter(Boolean) : [];
      const env: Record<string, string> = {};
      if (values.env) {
        values.env.split('\n').forEach((line: string) => {
          const [key, ...rest] = line.split('=');
          if (key && rest.length > 0) {
            env[key.trim()] = rest.join('=').trim();
          }
        });
      }
      // In production, call API to create server
      const newServer: MCPServer = {
        id: `mcp_${Date.now()}`,
        name: values.name,
        command: values.command,
        args,
        env,
        status: 'connected',
        tools: [],
      };
      setServers((prev) => [...prev, newServer]);
      setDrawerOpen(false);
      message.success('MCP 服务器已添加');
    });
  };

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string) => <Text strong>{text}</Text>,
    },
    {
      title: '命令',
      dataIndex: 'command',
      key: 'command',
      render: (text: string) => <Tag className="!font-mono !text-xs">{text}</Tag>,
    },
    {
      title: '参数',
      dataIndex: 'args',
      key: 'args',
      render: (args: string[]) => (
        <Space size={[2, 2]} wrap>
          {args?.map((a) => <Tag key={a} className="!text-xs">{a}</Tag>) || '-'}
        </Space>
      ),
    },
    {
      title: '环境变量',
      key: 'env',
      render: (_: any, record: MCPServer) => (
        <Text>{Object.keys(record.env || {}).length} 个变量</Text>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => <StatusBadge status={status as any} />,
    },
    {
      title: '工具',
      dataIndex: 'tools',
      key: 'tools',
      render: (tools: string[]) => (
        <Space size={[2, 2]} wrap>
          {tools?.map((t) => <Tag key={t} color="blue" className="!text-xs">{t}</Tag>) || (
            <Text type="secondary" className="text-xs">未暴露工具</Text>
          )}
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, record: MCPServer) => (
        <Space>
          <Button
            size="small"
            type="link"
            onClick={() => message.success(`${record.name} 已重启`)}
          >
            重启
          </Button>
          <Button
            size="small"
            type="link"
            danger
            onClick={() => {
              setServers((prev) => prev.filter((s) => s.id !== record.id));
              message.success(`${record.name} 已移除`);
            }}
          >
            移除
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div className="space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <Title level={4} className="!mb-0">MCP 服务器</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAddServer} className="!rounded-lg">
          添加服务器
        </Button>
      </div>

      <Text type="secondary" className="block text-sm">
        MCP (Model Context Protocol) 让 LLM 安全访问外部工具和数据源。在此管理 MCP 服务器连接。
      </Text>

      <Card>
        {loading ? (
          <div className="flex justify-center py-12"><Spin size="large" /></div>
        ) : servers.length === 0 ? (
          <div className="py-12">
            <Empty
              image={<LinkOutlined style={{ fontSize: 64, color: '#d9d9d9' }} />}
              description={
                <div>
                  <Text type="secondary">未配置 MCP 服务器</Text>
                  <br />
                  <Button type="link" onClick={handleAddServer} className="!mt-2">
                    添加您的第一个 MCP 服务器
                  </Button>
                </div>
              }
            />
          </div>
        ) : (
          <Table
            dataSource={servers}
            columns={columns}
            rowKey="id"
            pagination={{ pageSize: 10 }}
            scroll={{ x: 900 }}
          />
        )}
      </Card>

      <Drawer
        title="添加 MCP 服务器"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={480}
        extra={
          <Button type="primary" onClick={handleSubmit}>
            添加服务器
          </Button>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="服务器名称" rules={[{ required: true, message: '名称为必填项' }]}>
            <Input placeholder="例如：文件系统服务器" />
          </Form.Item>
          <Form.Item name="command" label="命令" rules={[{ required: true, message: '命令为必填项' }]}>
            <Input placeholder="例如：npx 或 python" />
          </Form.Item>
          <Form.Item name="args" label="参数" help="以逗号分隔的参数列表">
            <Input placeholder="例如：-y, @modelcontextprotocol/server-filesystem, /path" />
          </Form.Item>
          <Form.Item name="env" label="环境变量" help="每行一个：KEY=VALUE">
            <TextArea rows={4} placeholder="API_KEY=sk-...\nDEBUG=true" className="!font-mono" />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
}
