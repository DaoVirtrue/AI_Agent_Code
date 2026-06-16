import {
  Card,
  Row,
  Col,
  Tag,
  Button,
  Modal,
  Input,
  Form,
  Typography,
  Empty,
  Spin,
  Space,
  Collapse,
  InputNumber,
  Switch,
  message,
  Descriptions,
  Badge,
  Tooltip,
} from 'antd';
import {
  ToolOutlined,
  PlayCircleOutlined,
  CodeOutlined,
  ApiOutlined,
  ExperimentOutlined,
  ExpandOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { useState, useEffect, useMemo } from 'react';
import { useMCPStore } from '@/store/mcpStore';

const { Title, Text, Paragraph } = Typography;

const typeToInput = (property: {
  type?: string;
  description?: string;
  [key: string]: unknown;
}) => {
  const t = property.type || 'string';
  if (t === 'number' || t === 'integer') return 'number';
  if (t === 'boolean') return 'boolean';
  if (t === 'object') return 'textarea';
  return 'string';
};

const serverColorMap: Record<string, string> = {
  'search-server': 'blue',
  'tools-server': 'geekblue',
  sandbox: 'orange',
  'data-server': 'purple',
  filesystem: 'green',
  'fetch-server': 'cyan',
};

const getServerColor = (server: string): string => {
  return serverColorMap[server] || 'default';
};

export default function ToolExplorer() {
  const {
    tools,
    toolsLoading,
    testResult,
    testLoading,
    fetchTools,
    testTool,
    clearTestResult,
    error,
    clearError,
  } = useMCPStore();

  const [searchText, setSearchText] = useState('');
  const [testModalOpen, setTestModalOpen] = useState(false);
  const [selectedTool, setSelectedTool] = useState<{
    name: string;
    server: string;
    description: string;
    inputSchema: Record<string, unknown>;
  } | null>(null);
  const [form] = Form.useForm();

  useEffect(() => {
    fetchTools();
  }, [fetchTools]);

  useEffect(() => {
    if (error) {
      message.error(error);
      clearError();
    }
  }, [error, clearError]);

  const filteredTools = useMemo(() => {
    if (!searchText.trim()) return tools;
    const lower = searchText.toLowerCase();
    return tools.filter(
      (tool) =>
        tool.name.toLowerCase().includes(lower) ||
        tool.description.toLowerCase().includes(lower) ||
        tool.server.toLowerCase().includes(lower),
    );
  }, [tools, searchText]);

  const handleOpenTestModal = (tool: {
    name: string;
    server: string;
    description: string;
    inputSchema: Record<string, unknown>;
  }) => {
    setSelectedTool(tool);
    clearTestResult();
    form.resetFields();

    const properties =
      (tool.inputSchema.properties as Record<
        string,
        { type?: string; default?: unknown }
      >) || {};

    const initialValues: Record<string, unknown> = {};
    Object.entries(properties).forEach(([key, prop]) => {
      if (prop.default !== undefined) {
        initialValues[key] = prop.default;
      } else if (prop.type === 'boolean') {
        initialValues[key] = false;
      } else {
        initialValues[key] = '';
      }
    });
    form.setFieldsValue(initialValues);

    setTestModalOpen(true);
  };

  const handleExecuteTest = async () => {
    if (!selectedTool) return;
    try {
      const values = await form.validateFields();
      await testTool(selectedTool.server, selectedTool.name, values);
    } catch {
      // validation error — form will show field-level messages
    }
  };

  const handleCloseModal = () => {
    setTestModalOpen(false);
    setSelectedTool(null);
    clearTestResult();
    form.resetFields();
  };

  const parsedTestResult = useMemo(() => {
    if (!testResult) return null;
    try {
      return JSON.parse(testResult);
    } catch {
      return { raw: testResult };
    }
  }, [testResult]);

  const renderFormFields = () => {
    if (!selectedTool) return null;

    const properties =
      (selectedTool.inputSchema.properties as Record<
        string,
        { type?: string; description?: string; default?: unknown; enum?: unknown[] }
      >) || {};

    if (Object.keys(properties).length === 0) {
      return (
        <Text type="secondary">
          此工具没有输入参数。点击执行进行测试。
        </Text>
      );
    }

    return Object.entries(properties).map(([key, prop]) => {
      const inputType = typeToInput(prop);
      const label = (
        <span className="flex items-center gap-1">
          {key}
          {prop.description && (
            <Tooltip title={prop.description}>
              <Text
                type="secondary"
                className="text-xs cursor-help border-b border-dashed border-gray-400"
              >
                ?
              </Text>
            </Tooltip>
          )}
        </span>
      );

      const rules = [{ required: true, message: `${key} 为必填项` }];

      switch (inputType) {
        case 'number':
          return (
            <Form.Item key={key} name={key} label={label} rules={rules}>
              <InputNumber
                placeholder={`输入 ${key}`}
                className="!w-full"
              />
            </Form.Item>
          );
        case 'boolean':
          return (
            <Form.Item
              key={key}
              name={key}
              label={label}
              valuePropName="checked"
              rules={rules}
            >
              <Switch />
            </Form.Item>
          );
        case 'textarea':
          return (
            <Form.Item key={key} name={key} label={label} rules={rules}>
              <Input.TextArea
                rows={4}
                placeholder={`输入 ${key} (JSON)`}
              />
            </Form.Item>
          );
        default:
          return (
            <Form.Item key={key} name={key} label={label} rules={rules}>
              <Input placeholder={`输入 ${key}`} />
            </Form.Item>
          );
      }
    });
  };

  const renderToolCard = (tool: {
    name: string;
    server: string;
    description: string;
    inputSchema: Record<string, unknown>;
  }) => {
    const properties =
      (tool.inputSchema.properties as Record<
        string,
        { type?: string; description?: string }
      >) || {};
    const hasSchema = Object.keys(properties).length > 0;

    return (
      <Card
        hoverable
        className="!rounded-xl h-full border border-gray-200 dark:border-gray-700 hover:shadow-md transition-shadow duration-200"
        styles={{ body: { padding: '20px', display: 'flex', flexDirection: 'column', height: '100%' } }}
      >
        <div className="flex items-center gap-2 mb-2">
          <ToolOutlined className="text-blue-500 text-lg" />
          <Title level={5} className="!mb-0" ellipsis={{ tooltip: tool.name }}>
            {tool.name}
          </Title>
        </div>

        <Tag
          icon={<ApiOutlined />}
          color={getServerColor(tool.server)}
          className="w-fit mb-2"
        >
          {tool.server}
        </Tag>

        <Paragraph
          type="secondary"
          ellipsis={{ rows: 2, expandable: true, symbol: '更多' }}
          className="!mb-3 flex-1"
        >
          {tool.description || '暂无描述'}
        </Paragraph>

        {hasSchema && (
          <Collapse
            ghost
            size="small"
            className="!mb-3"
            expandIconPosition="end"
            items={[
              {
                key: 'schema',
                label: (
                  <Text className="text-xs flex items-center gap-1">
                    <CodeOutlined />
                    输入结构
                  </Text>
                ),
                children: (
                  <pre className="text-xs bg-gray-50 dark:bg-gray-800 p-3 rounded-lg overflow-x-auto max-h-48">
                    <code>
                      {JSON.stringify(tool.inputSchema, null, 2)}
                    </code>
                  </pre>
                ),
              },
            ]}
          />
        )}

        <Button
          type="primary"
          ghost
          icon={<ExperimentOutlined />}
          block
          onClick={() => handleOpenTestModal(tool)}
          className="!rounded-lg mt-auto"
        >
          测试工具
        </Button>
      </Card>
    );
  };

  if (toolsLoading && tools.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <Spin size="large" tip="加载工具中..." />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Search bar */}
      <div className="flex items-center gap-3">
        <Input
          prefix={<SearchOutlined className="text-gray-400" />}
          placeholder="搜索工具..."
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          allowClear
          className="!rounded-lg max-w-md"
          size="large"
        />
        <Text type="secondary" className="text-sm whitespace-nowrap">
          {filteredTools.length} / {tools.length} 个工具
        </Text>
      </div>

      {/* Tool cards grid */}
      {filteredTools.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            searchText
              ? `没有匹配 "${searchText}" 的工具`
              : '暂无可用工具'
          }
        />
      ) : (
        <Spin spinning={toolsLoading}>
          <Row gutter={[16, 16]}>
            {filteredTools.map((tool) => (
              <Col key={`${tool.server}-${tool.name}`} xs={24} sm={12} lg={8}>
                {renderToolCard(tool)}
              </Col>
            ))}
          </Row>
        </Spin>
      )}

      {/* Test Tool Modal */}
      <Modal
        title={
          selectedTool ? (
            <Space>
              <ExperimentOutlined className="text-blue-500" />
              <span>测试: {selectedTool.name}</span>
            </Space>
          ) : (
            '测试工具'
          )
        }
        open={testModalOpen}
        onCancel={handleCloseModal}
        footer={[
          <Button key="close" onClick={handleCloseModal}>
            关闭
          </Button>,
          <Button
            key="execute"
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={testLoading}
            onClick={handleExecuteTest}
            disabled={!selectedTool}
          >
            执行
          </Button>,
        ]}
        width={700}
        destroyOnClose
      >
        {selectedTool && (
          <div className="space-y-5">
            {/* Tool Info */}
            <div className="bg-gray-50 dark:bg-gray-800 p-3 rounded-lg">
              <Descriptions size="small" column={2}>
                <Descriptions.Item label="工具">
                  <Text strong>{selectedTool.name}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="服务器">
                  <Tag
                    icon={<ApiOutlined />}
                    color={getServerColor(selectedTool.server)}
                  >
                    {selectedTool.server}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="描述" span={2}>
                  <Text type="secondary">
                    {selectedTool.description || '无描述'}
                  </Text>
                </Descriptions.Item>
              </Descriptions>
            </div>

            {/* Dynamic Form */}
            <div>
              <Text strong className="block mb-3">
                参数
              </Text>
              <Form
                form={form}
                layout="vertical"
                size="middle"
                onFinish={handleExecuteTest}
              >
                {renderFormFields()}
              </Form>
            </div>

            {/* Test Result */}
            {parsedTestResult && (
              <div>
                <Text strong className="block mb-2">
                  结果
                </Text>
                <div className="bg-gray-50 dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700">
                  <div className="flex items-center gap-2 mb-3">
                    <Text className="text-sm">状态:</Text>
                    {parsedTestResult.status === 'success' ? (
                      <Tag color="green">成功</Tag>
                    ) : (
                      <Tag color="red">错误</Tag>
                    )}
                    {parsedTestResult.tool && (
                      <Text type="secondary" className="text-xs">
                        工具: {parsedTestResult.tool}
                      </Text>
                    )}
                  </div>

                  <Collapse
                    ghost
                    size="small"
                    items={[
                      {
                        key: 'raw',
                        label: (
                          <span className="flex items-center gap-1 text-xs">
                            <ExpandOutlined />
                            原始响应
                          </span>
                        ),
                        children: (
                          <pre className="text-xs bg-gray-100 dark:bg-gray-900 p-3 rounded overflow-x-auto max-h-64">
                            <code>{testResult}</code>
                          </pre>
                        ),
                      },
                    ]}
                  />

                  {parsedTestResult.result && (
                    <div className="mt-3">
                      <Text className="text-sm block mb-1">
                        输出:
                      </Text>
                      <pre className="text-xs bg-gray-100 dark:bg-gray-900 p-3 rounded overflow-x-auto max-h-48">
                        <code>
                          {typeof parsedTestResult.result === 'string'
                            ? parsedTestResult.result
                            : JSON.stringify(parsedTestResult.result, null, 2)}
                        </code>
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
