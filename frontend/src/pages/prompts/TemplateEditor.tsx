import { useState, useEffect, useMemo } from 'react';
import {
  Card,
  Button,
  Input,
  Space,
  Tag,
  Modal,
  Typography,
  Empty,
  Timeline,
  Spin,
  Badge,
  Tooltip,
  Row,
  Col,
  message,
} from 'antd';
import {
  SaveOutlined,
  PlayCircleOutlined,
  HistoryOutlined,
  CodeOutlined,
  EyeOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import Editor from '@monaco-editor/react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { usePromptsStore } from '@/store/promptsStore';
import { formatDate, formatNumber } from '@/utils/format';

const { Title, Text } = Typography;

export function TemplateEditor() {
  const selectedTemplate = usePromptsStore((s) => s.selectedTemplate);
  const renderedOutput = usePromptsStore((s) => s.renderedOutput);
  const renderedTokens = usePromptsStore((s) => s.renderedTokens);
  const renderLoading = usePromptsStore((s) => s.renderLoading);
  const versions = usePromptsStore((s) => s.versions);
  const versionsLoading = usePromptsStore((s) => s.versionsLoading);

  const updateExistingTemplate = usePromptsStore((s) => s.updateExistingTemplate);
  const renderTemplate = usePromptsStore((s) => s.renderTemplate);
  const fetchVersions = usePromptsStore((s) => s.fetchVersions);

  const [localContent, setLocalContent] = useState('');
  const [variableValues, setVariableValues] = useState<Record<string, string>>({});
  const [isVersionModalOpen, setIsVersionModalOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [previewMode, setPreviewMode] = useState<'raw' | 'markdown'>('markdown');

  useEffect(() => {
    if (selectedTemplate) {
      setLocalContent(selectedTemplate.content);
      const vars: Record<string, string> = {};
      selectedTemplate.variables.forEach((v) => {
        vars[v] = variableValues[v] || '';
      });
      setVariableValues(vars);
    }
  }, [selectedTemplate?.id]);

  const handleSave = async () => {
    if (!selectedTemplate) return;
    setIsSaving(true);
    try {
      await updateExistingTemplate(selectedTemplate.id, {
        content: localContent,
        variables: extractVariables(localContent),
      });
      message.success('模板保存成功');
    } catch (err: any) {
      message.error(err?.message || '保存模板失败');
    } finally {
      setIsSaving(false);
    }
  };

  const handleRender = async () => {
    if (!selectedTemplate) return;
    await renderTemplate(selectedTemplate.id, variableValues);
  };

  const handleOpenVersionHistory = async () => {
    if (!selectedTemplate) return;
    setIsVersionModalOpen(true);
    await fetchVersions(selectedTemplate.id);
  };

  const handleVariableChange = (variable: string, value: string) => {
    setVariableValues((prev) => ({ ...prev, [variable]: value }));
  };

  const categoryColor = useMemo(() => {
    const colors: Record<string, string> = {
      general: 'blue',
      coding: 'green',
      analysis: 'purple',
      writing: 'orange',
      chat: 'cyan',
      custom: 'magenta',
    };
    return selectedTemplate?.category
      ? colors[selectedTemplate.category] || 'default'
      : 'default';
  }, [selectedTemplate?.category]);

  if (!selectedTemplate) {
    return (
      <Empty
        description={
          <span className="text-gray-400">
            请从模板列表标签页选择模板进行编辑
          </span>
        }
        className="py-16"
      />
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3 flex-wrap">
          <Space align="center">
            <FileTextOutlined className="text-lg text-blue-500" />
            <Title level={4} className="!mb-0 dark:text-white">
              {selectedTemplate.name}
            </Title>
          </Space>
          <Tag color="blue">v{selectedTemplate.version}</Tag>
          {selectedTemplate.category && (
            <Tag color={categoryColor}>{selectedTemplate.category}</Tag>
          )}
          {selectedTemplate.tags &&
            selectedTemplate.tags.map((tag) => (
              <Tag key={tag} className="text-xs">
                {tag}
              </Tag>
            ))}
        </div>
        <Space>
          <Button
            icon={<HistoryOutlined />}
            onClick={handleOpenVersionHistory}
            className="!rounded-lg"
          >
            版本历史
          </Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            onClick={handleSave}
            loading={isSaving}
            className="!rounded-lg"
          >
            保存
          </Button>
        </Space>
      </div>

      {/* Two-panel layout */}
      <Row gutter={[16, 16]}>
        {/* Left panel: Editor */}
        <Col xs={24} lg={14}>
          <Card
            title={
              <Space>
                <CodeOutlined />
                <span>模板编辑</span>
              </Space>
            }
            className="!rounded-xl h-full"
          >
            <Editor
              height="500px"
              language="plaintext"
              theme="vs-dark"
              value={localContent}
              onChange={(value) => setLocalContent(value || '')}
              options={{
                minimap: { enabled: false },
                fontSize: 14,
                wordWrap: 'on',
                lineNumbers: 'on',
                scrollBeyondLastLine: false,
                automaticLayout: true,
                tabSize: 2,
              }}
            />
          </Card>
        </Col>

        {/* Right panel: Variables + Preview */}
        <Col xs={24} lg={10}>
          <div className="space-y-4">
            {/* Variables */}
            <Card
              title={
                <Space>
                  <EyeOutlined />
                  <span>变量测试</span>
                </Space>
              }
              className="!rounded-xl"
            >
              {selectedTemplate.variables.length === 0 ? (
                <Text type="secondary" className="text-sm">
                  未检测到变量。在模板内容中使用 {'{{变量名}}'} 来创建变量。
                </Text>
              ) : (
                <div className="space-y-3">
                  {selectedTemplate.variables.map((variable) => (
                    <div key={variable}>
                      <div className="flex items-center gap-1 mb-1">
                        <Tag color="blue" className="text-xs">
                          {`{{${variable}}}`}
                        </Tag>
                      </div>
                      <Input
                        value={variableValues[variable] || ''}
                        onChange={(e) =>
                          handleVariableChange(variable, e.target.value)
                        }
                        placeholder={`${variable} 的值`}
                        className="!rounded-lg"
                      />
                    </div>
                  ))}
                </div>
              )}

              <div className="mt-4 flex gap-2">
                <Button
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  onClick={handleRender}
                  loading={renderLoading}
                  className="!rounded-lg"
                  block
                  disabled={selectedTemplate.variables.length === 0}
                >
                  渲染预览
                </Button>
              </div>
            </Card>

            {/* Render Preview */}
            {renderedOutput && (
              <Card
                title={
                  <div className="flex items-center justify-between w-full">
                    <Space>
                      <EyeOutlined />
                      <span>预览</span>
                    </Space>
                    <Space size="small">
                      <Button
                        size="small"
                        type={previewMode === 'raw' ? 'primary' : 'default'}
                        onClick={() => setPreviewMode('raw')}
                      >
                        原始
                      </Button>
                      <Button
                        size="small"
                        type={previewMode === 'markdown' ? 'primary' : 'default'}
                        onClick={() => setPreviewMode('markdown')}
                      >
                        Markdown
                      </Button>
                      <Tooltip title={`${renderedTokens} tokens`}>
                        <Tag icon={<CodeOutlined />} color="green" className="!m-0">
                          {formatNumber(renderedTokens, 0)} tokens
                        </Tag>
                      </Tooltip>
                    </Space>
                  </div>
                }
                className="!rounded-xl"
              >
                <div className="max-h-[500px] overflow-y-auto">
                  {previewMode === 'markdown' ? (
                    <div className="markdown-content prose prose-sm dark:prose-invert max-w-none">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {renderedOutput}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    <pre className="whitespace-pre-wrap text-sm bg-gray-50 dark:bg-gray-800 p-3 rounded-lg !m-0 font-mono">
                      {renderedOutput}
                    </pre>
                  )}
                </div>
              </Card>
            )}
          </div>
        </Col>
      </Row>

      {/* Version History Modal */}
      <Modal
        title={
          <Space>
            <HistoryOutlined />
            <span>版本历史 — {selectedTemplate.name}</span>
          </Space>
        }
        open={isVersionModalOpen}
        onCancel={() => setIsVersionModalOpen(false)}
        footer={null}
        width={560}
      >
        <div className="py-4">
          {versionsLoading ? (
            <div className="flex justify-center py-8">
              <Spin tip="加载版本中..." />
            </div>
          ) : versions.length === 0 ? (
            <Empty description="暂无版本历史" />
          ) : (
            <Timeline
              items={versions.map((v) => ({
                color: v.version === selectedTemplate.version ? 'blue' : 'gray',
                dot:
                  v.version === selectedTemplate.version ? (
                    <Badge status="processing" color="blue" />
                  ) : undefined,
                children: (
                  <div className="flex items-center justify-between">
                    <Space>
                      <Tag color={v.version === selectedTemplate.version ? 'blue' : 'default'}>
                        v{v.version}
                      </Tag>
                      {v.version === selectedTemplate.version && (
                        <Tag color="green" className="text-xs">
                          当前
                        </Tag>
                      )}
                    </Space>
                    <Text type="secondary" className="text-xs">
                      {formatDate(v.created_at)}
                    </Text>
                  </div>
                ),
              }))}
            />
          )}
        </div>
      </Modal>
    </div>
  );
}

function extractVariables(content: string): string[] {
  const regex = /\{\{(\w+)\}\}/g;
  const vars = new Set<string>();
  let match: RegExpExecArray | null;
  while ((match = regex.exec(content)) !== null) {
    vars.add(match[1]);
  }
  return Array.from(vars);
}

export default TemplateEditor;
