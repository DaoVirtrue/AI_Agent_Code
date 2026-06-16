import { useEffect, useState } from 'react';
import { Card, Input, Button, Typography, Space, Empty, List, Form, message, Tag, Tabs } from 'antd';
import { FileTextOutlined, PlayCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { useAppStore } from '@/store';
import type { TemplateResponse } from '@/types';
import { formatNumber } from '@/utils/format';

const { TextArea } = Input;
const { Title, Text, Paragraph } = Typography;

const MOCK_TEMPLATES: TemplateResponse[] = [
  { id: 'tpl_1', name: '代码审查助手', content: '你是一个专业的代码审查专家。请审查以下 {{language}} 代码：\n\n```{{language}}\n{{code}}\n```\n\n请关注：代码质量、潜在bug、性能优化建议。', variables: ['language', 'code'], version: 3, tags: ['开发', '代码'], created_at: '2025-06-01', updated_at: '2025-06-10', created_by: 'admin' },
  { id: 'tpl_2', name: '技术文档生成器', content: '请为以下 {{component}} 生成技术文档。\n\n功能描述：{{description}}\n接口定义：{{api_spec}}\n\n包含：概述、使用方法、参数说明、示例代码。', variables: ['component', 'description', 'api_spec'], version: 2, tags: ['文档', '技术'], created_at: '2025-05-15', updated_at: '2025-06-08', created_by: 'admin' },
  { id: 'tpl_3', name: '客户邮件回复', content: '你是客服代表。请根据以下信息回复客户邮件：\n\n客户名称：{{customer_name}}\n问题描述：{{issue}}\n解决方案：{{solution}}\n\n语气：专业、友好、简洁。', variables: ['customer_name', 'issue', 'solution'], version: 1, tags: ['客服', '邮件'], created_at: '2025-04-20', updated_at: '2025-04-20', created_by: 'admin' },
];

export function PromptsPage() {
  const setBreadcrumbs = useAppStore((s) => s.setBreadcrumbs);
  const [templates, setTemplates] = useState<TemplateResponse[]>(MOCK_TEMPLATES);
  const [selectedTemplate, setSelectedTemplate] = useState<TemplateResponse | null>(null);
  const [activeTab, setActiveTab] = useState('templates');
  const [variableValues, setVariableValues] = useState<Record<string, string>>({});
  const [renderedResult, setRenderedResult] = useState('');
  const [tokenCount, setTokenCount] = useState<number | null>(null);
  const [rendering, setRendering] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newContent, setNewContent] = useState('');
  const [newVariables, setNewVariables] = useState('');
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    setBreadcrumbs([{ title: 'Prompts' }]);
  }, [setBreadcrumbs]);

  const handleSelectTemplate = (tpl: TemplateResponse) => {
    setSelectedTemplate(tpl);
    setRenderedResult(null);
    setTokenCount(null);
    setActiveTab('editor');
    const vars: Record<string, string> = {};
    tpl.variables.forEach(v => { vars[v] = ''; });
    setVariableValues(vars);
  };

  const handleRender = async () => {
    if (!selectedTemplate) return;
    setRendering(true);
    await new Promise(r => setTimeout(r, 300));
    let result = selectedTemplate.content;
    for (const [k, v] of Object.entries(variableValues)) {
      result = result.replace(new RegExp(`\\{\\{${k}\\}\\}`, 'g'), v || `[${k}]`);
    }
    setRenderedResult(result);
    setTokenCount(Math.floor(result.length / 2.5));
    message.success('渲染成功');
    setRendering(false);
  };

  const handleCreate = async () => {
    if (!newName.trim() || !newContent.trim()) return;
    setCreating(true);
    await new Promise(r => setTimeout(r, 300));
    const vars = newVariables.split(',').map(v => v.trim()).filter(Boolean);
    const created: TemplateResponse = {
      id: `tpl_${Date.now()}`, name: newName.trim(), content: newContent.trim(),
      variables: vars, version: 1, tags: [], created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(), created_by: 'admin',
    };
    setTemplates(prev => [created, ...prev]);
    setShowCreate(false); setNewName(''); setNewContent(''); setNewVariables('');
    message.success('模板已创建');
    setCreating(false);
  };

  const templatesTab = (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <Text type="secondary">共 {templates.length} 个模板</Text>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { setShowCreate(true); setActiveTab('create'); }}>新建模板</Button>
      </div>
      {templates.length === 0 ? (
        <Empty description="暂无模板" />
      ) : (
        <List dataSource={templates} renderItem={item => (
          <Card hoverable size="small" className="mb-2" onClick={() => handleSelectTemplate(item)}>
            <div className="flex justify-between items-center">
              <div><Text strong>{item.name}</Text><br /><Text type="secondary" className="text-xs">v{item.version} · {item.variables.length} 个变量</Text></div>
              <Tag>{item.tags?.[0] || '通用'}</Tag>
            </div>
          </Card>
        )} />
      )}
    </div>
  );

  const editorTab = selectedTemplate ? (
    <div className="space-y-4">
      <Card title={selectedTemplate.name}>
        <Paragraph className="!mb-0 text-sm bg-gray-50 dark:bg-gray-800 p-3 rounded font-mono whitespace-pre-wrap">{selectedTemplate.content}</Paragraph>
      </Card>
      <Card title="变量测试">
        <Space direction="vertical" className="w-full">
          {selectedTemplate.variables.map(v => (
            <div key={v}><Text strong>{v}</Text><Input value={variableValues[v] || ''} onChange={e => setVariableValues(prev => ({ ...prev, [v]: e.target.value }))} placeholder={`输入 ${v} 的值`} /></div>
          ))}
          <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleRender} loading={rendering}>渲染预览</Button>
        </Space>
      </Card>
      {renderedResult && (
        <Card title={<span>渲染结果 {tokenCount && <Tag color="blue">{formatNumber(tokenCount, 0)} tokens</Tag>}</span>}>
          <Paragraph className="!mb-0 whitespace-pre-wrap bg-gray-50 p-3 rounded text-sm">{renderedResult}</Paragraph>
        </Card>
      )}
    </div>
  ) : (
    <Empty description="从模板列表选择一个模板开始编辑" />
  );

  const createTab = (
    <Card title="新建模板">
      <Form layout="vertical">
        <Form.Item label="模板名称" required><Input value={newName} onChange={e => setNewName(e.target.value)} placeholder="例如：代码审查助手" /></Form.Item>
        <Form.Item label="模板内容" required><TextArea rows={6} value={newContent} onChange={e => setNewContent(e.target.value)} placeholder='使用 {{变量名}} 作为占位符，例如：请审查以下 {{language}} 代码' /></Form.Item>
        <Form.Item label="变量（逗号分隔）"><Input value={newVariables} onChange={e => setNewVariables(e.target.value)} placeholder="language, code" /></Form.Item>
        <Space><Button type="primary" onClick={handleCreate} loading={creating}>创建</Button><Button onClick={() => { setShowCreate(false); setActiveTab('templates'); }}>取消</Button></Space>
      </Form>
    </Card>
  );

  const tabItems = [
    { key: 'templates', label: '模板', children: templatesTab },
    { key: 'editor', label: '编辑器', children: editorTab },
    ...(showCreate ? [{ key: 'create', label: '新建', children: createTab }] : []),
  ];

  return (
    <div className="space-y-4 animate-fade-in">
      <Title level={4} className="!mb-0">Prompt 工程</Title>
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />
    </div>
  );
}
