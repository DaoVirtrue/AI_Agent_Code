import { useEffect, useState } from 'react';
import { Card, Table, Button, Drawer, Form, Input, Typography, Space, Tag, Empty, Spin, message, Tabs, Tooltip, Alert } from 'antd';
import { PlusOutlined, LinkOutlined, ToolOutlined, ReloadOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { useAppStore, useMCPStore } from '@/store';
import { StatusBadge } from '@/components/common/StatusBadge';
import type { MCPToolDef } from '@/api/mcp';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

export function MCPPage() {
  const setBreadcrumbs = useAppStore((s) => s.setBreadcrumbs);
  const {
    servers, serversLoading, tools, toolsLoading, testResult, testLoading,
    fetchServers, fetchTools, connectServer, disconnectServer, testTool, clearTestResult,
  } = useMCPStore();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [testOpen, setTestOpen] = useState(false);
  const [testTarget, setTestTarget] = useState<MCPToolDef | null>(null);
  const [form] = Form.useForm();
  const [testForm] = Form.useForm();

  useEffect(() => {
    setBreadcrumbs([{ title: 'MCP' }]);
    fetchServers();
    fetchTools();
  }, [setBreadcrumbs]);

  const handleAddServer = async () => {
    const values = await form.validateFields();
    try {
      await connectServer(values.name, values.url);
      message.success(`MCP 服务器「${values.name}」已添加`);
      setDrawerOpen(false);
      form.resetFields();
    } catch (e: any) {
      message.error('添加失败: ' + (e?.message || '未知错误'));
    }
  };

  const openTest = (tool: MCPToolDef) => {
    setTestTarget(tool);
    testForm.resetFields();
    clearTestResult();
    setTestOpen(true);
  };

  const handleTest = async () => {
    if (!testTarget) return;
    const params = (await testForm.validateFields()).args ? JSON.parse((await testForm.validateFields()).args) : {};
    await testTool(testTarget.server_name, testTarget.name, params);
  };

  const serverColumns = [
    {
      title: '名称', dataIndex: 'name', key: 'name',
      render: (t: string) => <Text strong>{t}</Text>,
    },
    {
      title: '传输', dataIndex: 'transport', key: 'transport',
      render: (t: string) => <Tag className="!font-mono !text-xs">{t}</Tag>,
    },
    {
      title: '说明', dataIndex: 'description', key: 'description', ellipsis: true,
      render: (t: string) => <Text type="secondary">{t || '-'}</Text>,
    },
    {
      title: '工具数', dataIndex: 'toolCount', key: 'toolCount',
      render: (v: number) => <Tag color="blue">{v ?? 0}</Tag>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (status: string) => <StatusBadge status={status as any} />,
    },
    {
      title: '操作', key: 'actions',
      render: (_: any, record: any) => (
        <Button size="small" type="link" danger onClick={() => { disconnectServer(record.name); message.success(`已断开 ${record.name}`); }}>
          断开
        </Button>
      ),
    },
  ];

  const toolColumns = [
    {
      title: '工具名', dataIndex: 'name', key: 'name',
      render: (t: string) => <Text strong className="font-mono">{t}</Text>,
    },
    {
      title: '所属服务器', dataIndex: 'server_name', key: 'server_name',
      render: (t: string) => <Tag color="geekblue">{t}</Tag>,
    },
    {
      title: '说明', dataIndex: 'description', key: 'description', ellipsis: true,
      render: (t: string) => <Text type="secondary">{t || '-'}</Text>,
    },
    {
      title: '操作', key: 'actions',
      render: (_: any, record: MCPToolDef) => (
        <Button size="small" icon={<PlayCircleOutlined />} onClick={() => openTest(record)}>测试调用</Button>
      ),
    },
  ];

  return (
    <div className="space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <Title level={4} className="!mb-0">MCP 服务器</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => { fetchServers(); fetchTools(); }}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setDrawerOpen(true)} className="!rounded-lg">
            添加服务器
          </Button>
        </Space>
      </div>

      <Text type="secondary" className="block text-sm">
        MCP (Model Context Protocol) 让 LLM 安全访问外部工具和数据源。下方列出平台已连接的 MCP 服务器及暴露的工具，可在 AI 工作台选择启用。
      </Text>

      <Tabs
        items={[
          {
            key: 'servers',
            label: <span><LinkOutlined /> 服务器</span>,
            children: (
              <Card>
                {serversLoading ? (
                  <div className="flex justify-center py-12"><Spin size="large" /></div>
                ) : servers.length === 0 ? (
                  <Empty description="未配置 MCP 服务器，点击右上角「添加服务器」" />
                ) : (
                  <Table dataSource={servers} columns={serverColumns} rowKey="id" pagination={false} scroll={{ x: 720 }} />
                )}
              </Card>
            ),
          },
          {
            key: 'tools',
            label: <span><ToolOutlined /> 工具</span>,
            children: (
              <Card>
                {toolsLoading ? (
                  <div className="flex justify-center py-12"><Spin size="large" /></div>
                ) : tools.length === 0 ? (
                  <Empty description="暂无工具，连接 MCP 服务器后自动发现工具" />
                ) : (
                  <Table dataSource={tools} columns={toolColumns} rowKey={(r: any) => `${r.server_name}:${r.name}`} pagination={{ pageSize: 10 }} scroll={{ x: 720 }} />
                )}
              </Card>
            ),
          },
        ]}
      />

      <Drawer
        title="添加 MCP 服务器"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={440}
        extra={<Button type="primary" onClick={handleAddServer}>添加</Button>}
      >
        <Alert type="info" showIcon className="mb-3" message="示例：文件系统 / 网络工具，输入名称与地址即可注册" />
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="服务器名称" rules={[{ required: true, message: '名称为必填项' }]}>
            <Input placeholder="例如：文件系统" />
          </Form.Item>
          <Form.Item name="url" label="地址" rules={[{ required: true, message: '地址为必填项' }]}>
            <Input placeholder="例如：sse://filesystem 或 stdio://web" />
          </Form.Item>
        </Form>
      </Drawer>

      <Drawer
        title={`测试调用：${testTarget?.name || ''}`}
        open={testOpen}
        onClose={() => setTestOpen(false)}
        width={560}
        extra={<Button type="primary" onClick={handleTest} loading={testLoading}>执行</Button>}
      >
        {testTarget && (
          <div className="space-y-4">
            <Text type="secondary">{testTarget.description || '无描述'}</Text>
            <Form form={testForm} layout="vertical">
              <Form.Item name="args" label="参数 (JSON)" initialValue="{}">
                <TextArea rows={5} placeholder='例如 {"query": "SELECT 1"}' className="!font-mono" />
              </Form.Item>
            </Form>
            {testResult && (
              <div>
                <Text strong className="block mb-1">返回结果</Text>
                <pre className="bg-gray-900 text-green-300 rounded-lg p-3 text-xs overflow-auto max-h-64 whitespace-pre-wrap">{testResult}</pre>
              </div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
}
