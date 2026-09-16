import { useEffect, useState, useCallback } from 'react';
import { Card, Input, Button, Typography, Space, Tag, Table, Empty, message, Modal, Select } from 'antd';
import { ApiOutlined, PlusOutlined, SearchOutlined, DeleteOutlined } from '@ant-design/icons';
import { useAppStore } from '@/store';
import { listSkills, createSkill, deleteSkill, type Skill } from '@/api/skills';
import { listAvailableTools as listTools } from '@/api/experts';

const { TextArea } = Input;
const { Title, Text, Paragraph } = Typography;

export function SkillPage() {
  const setBreadcrumbs = useAppStore((s) => s.setBreadcrumbs);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [tools, setTools] = useState<any[]>([]);
  const [search, setSearch] = useState('');
  const [createOpen, setCreateOpen] = useState(false);

  // Create form
  const [formName, setFormName] = useState('');
  const [formDesc, setFormDesc] = useState('');
  const [formInstructions, setFormInstructions] = useState('');
  const [formTools, setFormTools] = useState<string[]>([]);

  const refresh = useCallback(async () => {
    try {
      const [skillRes, toolRes] = await Promise.all([listSkills(search), listTools()]);
      setSkills(skillRes.items || []);
      setTools(toolRes.tools || []);
    } catch {}
  }, [search]);

  useEffect(() => {
    setBreadcrumbs([{ title: '技能仓库' }]);
    refresh();
  }, [setBreadcrumbs, refresh]);

  const handleCreate = async () => {
    if (!formName.trim()) { message.warning('请输入技能名'); return; }
    try {
      await createSkill({
        name: formName.trim(),
        description: formDesc,
        instructions: formInstructions,
        tools: formTools,
      });
      message.success(`技能「${formName}」已创建`);
      setCreateOpen(false);
      setFormName(''); setFormDesc(''); setFormInstructions(''); setFormTools([]);
      refresh();
    } catch (err: any) {
      message.error('创建失败: ' + (err?.message || '未知错误'));
    }
  };

  const handleDelete = async (name: string) => {
    try {
      await deleteSkill(name);
      message.success('已删除');
      refresh();
    } catch (err: any) {
      message.error('删除失败: ' + (err?.message || '未知错误'));
    }
  };

  const toolLabel = (name: string) => tools.find(t => t.name === name)?.label || name;

  const columns = [
    { title: '技能名', dataIndex: 'name', key: 'name', render: (t: string) => <Text strong>{t}</Text> },
    { title: '说明', dataIndex: 'description', key: 'description', ellipsis: true },
    { title: '工具', dataIndex: 'tools', key: 'tools', render: (t: string[]) => t?.length ? t.map(k => <Tag key={k} color="blue">{toolLabel(k)}</Tag>) : <Text type="secondary">-</Text> },
    { title: '版本', dataIndex: 'version', key: 'version', render: (v: string) => <Tag>{v}</Tag> },
    { title: '操作', key: 'actions', render: (_: any, record: any) => (
      <Button type="text" danger size="small" icon={<DeleteOutlined />} onClick={() => handleDelete(record.name)}>删除</Button>
    )},
  ];

  return (
    <div className="space-y-4 animate-fade-in">
      <Title level={4} className="!mb-0">技能仓库</Title>

      <Card
        title={<span className="flex items-center gap-2"><ApiOutlined /> 可复用技能</span>}
        extra={
          <Space>
            <Input
              placeholder="搜索技能" prefix={<SearchOutlined />} allowClear
              value={search} onChange={e => setSearch(e.target.value)}
              onPressEnter={refresh} style={{ width: 180 }}
            />
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>上传技能</Button>
          </Space>
        }
      >
        <Table dataSource={skills} rowKey="name" columns={columns} pagination={false}
          locale={{ emptyText: <Empty description="暂无技能，点击「上传技能」创建你的可复用技能" /> }} />
      </Card>

      <Modal title="上传技能" open={createOpen} onOk={handleCreate} onCancel={() => setCreateOpen(false)} width={600} okText="创建" cancelText="取消">
        <Space direction="vertical" className="w-full" size="middle">
          <div>
            <Text strong className="block mb-1">技能名 *</Text>
            <Input value={formName} onChange={e => setFormName(e.target.value)} placeholder="如：代码审查 / 周报生成 / 数据分析" />
          </div>
          <div>
            <Text strong className="block mb-1">技能说明</Text>
            <Input value={formDesc} onChange={e => setFormDesc(e.target.value)} placeholder="一句话描述这个技能做什么" />
          </div>
          <div>
            <Text strong className="block mb-1">技能指令（提示词）</Text>
            <TextArea rows={4} value={formInstructions} onChange={e => setFormInstructions(e.target.value)}
              placeholder="技能的具体行为指令，会注入到系统提示词..." />
          </div>
          <div>
            <Text strong className="block mb-1">绑定工具</Text>
            <Select mode="multiple" className="w-full" value={formTools} onChange={setFormTools}
              placeholder="选择工具" options={tools.map(t => ({ value: t.name, label: t.label || t.name }))} />
          </div>
        </Space>
      </Modal>
    </div>
  );
}
