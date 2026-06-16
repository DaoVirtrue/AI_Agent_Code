import { useState, useEffect } from 'react';
import { Tabs, Card, Typography } from 'antd';
import { FileTextOutlined, EditOutlined, ExperimentOutlined } from '@ant-design/icons';
import { useAppStore } from '@/store';
import { usePromptsStore } from '@/store/promptsStore';
import TemplateList from './TemplateList';
import TemplateEditor from './TemplateEditor';
import ABTestResults from './ABTestResults';
import type { TemplateResponse } from '@/types';

const { Title, Text } = Typography;

export function PromptsPage() {
  const setBreadcrumbs = useAppStore((s) => s.setBreadcrumbs);
  const fetchTemplates = usePromptsStore((s) => s.fetchTemplates);
  const [activeTab, setActiveTab] = useState<string>('templates');

  useEffect(() => {
    setBreadcrumbs([{ title: 'Prompt 管理' }]);
  }, [setBreadcrumbs]);

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  const handleSelectTemplate = (_template: TemplateResponse) => {
    setActiveTab('editor');
  };

  const tabItems = [
    {
      key: 'templates',
      label: (
        <span className="flex items-center gap-2">
          <FileTextOutlined />
          <span>模板列表</span>
        </span>
      ),
      children: (
        <TemplateList
          onSelectTemplate={handleSelectTemplate}
          onSwitchTab={() => setActiveTab('editor')}
        />
      ),
    },
    {
      key: 'editor',
      label: (
        <span className="flex items-center gap-2">
          <EditOutlined />
          <span>模板编辑</span>
        </span>
      ),
      children: <TemplateEditor />,
    },
    {
      key: 'experiments',
      label: (
        <span className="flex items-center gap-2">
          <ExperimentOutlined />
          <span>A/B 实验</span>
        </span>
      ),
      children: <ABTestResults />,
    },
  ];

  return (
    <div className="p-6 space-y-6 max-w-[1600px] mx-auto animate-fade-in">
      <div>
        <Title level={3} className="!mb-1 dark:text-white">
          Prompt 工程
        </Title>
        <Text type="secondary">
          设计、测试并优化 Prompt 模板，支持 A/B 实验
        </Text>
      </div>

      <Card className="!rounded-xl">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={tabItems}
          size="large"
          className="prompts-tabs"
        />
      </Card>
    </div>
  );
}

export default PromptsPage;
