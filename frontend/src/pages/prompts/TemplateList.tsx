import { useState, useMemo, useCallback } from 'react';
import {
  Input,
  Card,
  Tag,
  Button,
  Empty,
  Spin,
  Modal,
  Form,
  Select,
  Space,
  Row,
  Col,
  Typography,
  Tooltip,
  message,
} from 'antd';
import {
  SearchOutlined,
  PlusOutlined,
  ClockCircleOutlined,
  TagOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import { usePromptsStore } from '@/store/promptsStore';
import { formatDate } from '@/utils/format';
import { truncateText } from '@/utils/format';
import type { TemplateResponse, TemplateCreate } from '@/types';

const { Title, Paragraph } = Typography;
const { TextArea } = Input;

const CATEGORY_OPTIONS = [
  { value: 'general', label: '通用' },
  { value: 'coding', label: '编程' },
  { value: 'analysis', label: '分析' },
  { value: 'writing', label: '写作' },
  { value: 'chat', label: '聊天' },
  { value: 'custom', label: '自定义' },
];

const CATEGORY_COLORS: Record<string, string> = {
  general: 'blue',
  coding: 'green',
  analysis: 'purple',
  writing: 'orange',
  chat: 'cyan',
  custom: 'magenta',
};

const TAG_COLORS: string[] = [
  'blue',
  'green',
  'purple',
  'orange',
  'cyan',
  'magenta',
  'red',
  'gold',
  'lime',
  'geekblue',
];

interface TemplateListProps {
  onSelectTemplate?: (template: TemplateResponse) => void;
  onSwitchTab?: () => void;
}

export function TemplateList({ onSelectTemplate, onSwitchTab }: TemplateListProps) {
  const templates = usePromptsStore((s) => s.templates);
  const templatesLoading = usePromptsStore((s) => s.templatesLoading);
  const fetchTemplates = usePromptsStore((s) => s.fetchTemplates);
  const createNewTemplate = usePromptsStore((s) => s.createNewTemplate);
  const selectTemplate = usePromptsStore((s) => s.selectTemplate);

  const [searchText, setSearchText] = useState('');
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [form] = Form.useForm();

  const categories = useMemo(() => {
    const cats = new Set<string>();
    templates.forEach((t) => {
      if (t.category) cats.add(t.category);
    });
    return Array.from(cats);
  }, [templates]);

  const filteredTemplates = useMemo(() => {
    let result = [...templates];

    if (searchText.trim()) {
      const lower = searchText.toLowerCase().trim();
      result = result.filter(
        (t) =>
          t.name.toLowerCase().includes(lower) ||
          (t.description && t.description.toLowerCase().includes(lower)) ||
          (t.tags && t.tags.some((tag) => tag.toLowerCase().includes(lower)))
      );
    }

    if (selectedCategories.length > 0) {
      result = result.filter(
        (t) => t.category && selectedCategories.includes(t.category)
      );
    }

    return result;
  }, [templates, searchText, selectedCategories]);

  const handleTemplateClick = useCallback(
    (template: TemplateResponse) => {
      selectTemplate(template);
      onSelectTemplate?.(template);
      onSwitchTab?.();
    },
    [selectTemplate, onSelectTemplate, onSwitchTab]
  );

  const handleCreate = () => {
    form.resetFields();
    setIsModalOpen(true);
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setIsSubmitting(true);

      const tags = values.tags || [];
      const variables = extractVariables(values.content || '');

      const data: TemplateCreate = {
        name: values.name,
        description: values.description || '',
        content: values.content,
        variables,
        category: values.category || 'general',
        tags,
      };

      const created = await createNewTemplate(data);
      if (created) {
        message.success('模板创建成功');
        setIsModalOpen(false);
        form.resetFields();
        await fetchTemplates();
      }
    } catch (err: any) {
      if (err?.message && err.message !== 'Validation failed') {
        message.error(err.message);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const renderCard = (template: TemplateResponse) => {
    const categoryColor = template.category
      ? CATEGORY_COLORS[template.category] || 'default'
      : 'default';

    return (
      <Col xs={24} sm={12} lg={8} key={template.id}>
        <Card
          hoverable
          className="!rounded-xl h-full transition-all duration-200 hover:shadow-md"
          onClick={() => handleTemplateClick(template)}
          styles={{ body: { height: '100%', display: 'flex', flexDirection: 'column' } }}
        >
          <div className="flex flex-col h-full">
            <div className="flex items-start justify-between mb-2">
              <div className="flex-1 min-w-0">
                <Title level={5} className="!mb-1 truncate dark:text-white">
                  <FileTextOutlined className="mr-2 text-blue-500" />
                  {template.name}
                </Title>
              </div>
              {template.category && (
                <Tag color={categoryColor} className="!ml-2 flex-shrink-0">
                  {template.category}
                </Tag>
              )}
            </div>

            <Paragraph
              type="secondary"
              ellipsis={{ rows: 2 }}
              className="!mb-3 flex-1"
            >
              {template.description || '暂无描述'}
            </Paragraph>

            {template.variables && template.variables.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-1">
                {template.variables.slice(0, 4).map((v) => (
                  <Tag key={v} color="blue" className="text-xs">
                    {`{{${v}}}`}
                  </Tag>
                ))}
                {template.variables.length > 4 && (
                  <Tooltip
                    title={template.variables.slice(4).map((v) => `{{${v}}}`).join(', ')}
                  >
                    <Tag className="text-xs cursor-pointer">
                      +{template.variables.length - 4} 更多
                    </Tag>
                  </Tooltip>
                )}
              </div>
            )}

            <div className="flex items-center justify-between mt-auto pt-3 border-t border-gray-100 dark:border-gray-700">
              <Space size={4} wrap>
                {template.tags &&
                  template.tags.slice(0, 3).map((tag, i) => (
                    <Tag
                      key={tag}
                      color={TAG_COLORS[i % TAG_COLORS.length]}
                      className="text-xs"
                    >
                      <TagOutlined className="mr-1" />
                      {truncateText(tag, 12)}
                    </Tag>
                  ))}
                {template.tags && template.tags.length > 3 && (
                  <Tooltip title={template.tags.slice(3).join(', ')}>
                    <Tag className="text-xs">+{template.tags.length - 3}</Tag>
                  </Tooltip>
                )}
              </Space>

              <Tag color="blue" className="text-xs flex-shrink-0">
                v{template.version}
              </Tag>
            </div>

            <div className="flex items-center gap-1 mt-2 text-xs text-gray-400 dark:text-gray-500">
              <ClockCircleOutlined />
              <span>{formatDate(template.updated_at)}</span>
            </div>
          </div>
        </Card>
      </Col>
    );
  };

  if (templatesLoading && templates.length === 0) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spin size="large" tip="加载模板中..." />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <Space wrap className="flex-1">
          <Input.Search
            placeholder="搜索模板..."
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onSearch={(val) => setSearchText(val)}
            allowClear
            className="!w-64"
          />
          {categories.length > 0 && (
            <Select
              mode="multiple"
              placeholder="按分类筛选"
              value={selectedCategories}
              onChange={setSelectedCategories}
              allowClear
              className="!min-w-[180px]"
              options={CATEGORY_OPTIONS.filter((o) => categories.includes(o.value))}
              maxTagCount={2}
            />
          )}
        </Space>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={handleCreate}
          className="!rounded-lg"
        >
          新建模板
        </Button>
      </div>

      {filteredTemplates.length === 0 && !templatesLoading ? (
        <Empty
          description={
            searchText || selectedCategories.length > 0
              ? '没有匹配搜索条件的模板'
              : '暂无模板，创建第一个模板开始使用。'
          }
          className="py-16"
        >
          {!searchText && selectedCategories.length === 0 && (
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
              创建模板
            </Button>
          )}
        </Empty>
      ) : (
        <Row gutter={[16, 16]}>
          {filteredTemplates.map(renderCard)}
        </Row>
      )}

      <Modal
        title="新建模板"
        open={isModalOpen}
        onOk={handleSave}
        onCancel={() => setIsModalOpen(false)}
        confirmLoading={isSubmitting}
        okText="创建"
        width={680}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          className="mt-4"
          initialValues={{ category: 'general' }}
        >
          <Form.Item
            name="name"
            label="模板名称"
            rules={[
              { required: true, message: '请输入模板名称' },
              {
                pattern: /^[a-zA-Z0-9_-]+$/,
                message: '仅允许字母、数字、连字符和下划线',
              },
            ]}
          >
            <Input placeholder="例如: summarize_text" />
          </Form.Item>

          <Form.Item name="description" label="描述">
            <TextArea rows={2} placeholder="简要描述模板的用途" />
          </Form.Item>

          <Form.Item name="category" label="分类">
            <Select options={CATEGORY_OPTIONS} />
          </Form.Item>

          <Form.Item
            name="content"
            label="模板内容"
            rules={[{ required: true, message: '请输入模板内容' }]}
            extra="使用 {{变量名}} 进行动态变量替换"
          >
            <TextArea
              rows={8}
              placeholder={
                'You are a helpful assistant. Please {{action}} the following:\n\n{{input}}\n\nRespond in a {{tone}} tone.'
              }
            />
          </Form.Item>

          <Form.Item
            name="tags"
            label="标签"
            extra="按 Enter 添加每个标签"
          >
            <Select
              mode="tags"
              placeholder="添加标签..."
              tokenSeparators={[',']}
              className="!w-full"
            />
          </Form.Item>
        </Form>
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

export default TemplateList;
