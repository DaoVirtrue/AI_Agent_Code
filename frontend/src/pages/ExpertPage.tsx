import { useEffect, useState, useCallback } from 'react';
import { Card, Input, Button, Typography, Space, Tag, Select, Table, Empty, message, Modal, Switch, Alert } from 'antd';
import { RobotOutlined, PlusOutlined, ThunderboltOutlined, SafetyOutlined } from '@ant-design/icons';
import { useAppStore } from '@/store';
import { listExperts, defineExpert, runExpert, listAvailableTools, listApprovals, decideApproval, type ExpertTool } from '@/api/experts';

const { TextArea } = Input;
const { Title, Text, Paragraph } = Typography;

export function ExpertPage() {
  const setBreadcrumbs = useAppStore((s) => s.setBreadcrumbs);
  const [experts, setExperts] = useState<any[]>([]);
  const [tools, setTools] = useState<ExpertTool[]>([]);
  const [approvals, setApprovals] = useState<any[]>([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [running, setRunning] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);

  // Create form state
  const [formName, setFormName] = useState('');
  const [formRole, setFormRole] = useState('');
  const [formPrompt, setFormPrompt] = useState('');
  const [formSkills, setFormSkills] = useState<string[]>([]);
  const [formKb, setFormKb] = useState<string[]>([]);
  const [formDesc, setFormDesc] = useState('');

  const refresh = useCallback(async () => {
    try {
      const [exp, toolList, appr] = await Promise.all([listExperts(), listAvailableTools(), listApprovals()]);
      setExperts(exp.items || []);
      setTools(toolList.tools || []);
      setApprovals(appr.pending || []);
    } catch {}
  }, []);

  useEffect(() => {
    setBreadcrumbs([{ title: '智能体专家' }]);
    refresh();
  }, [setBreadcrumbs, refresh]);

  const handleCreate = async () => {
    if (!formName.trim()) { message.warning('请输入专家名称'); return; }
    try {
      await defineExpert({
        name: formName.trim(),
        role: formRole,
        system_prompt: formPrompt,
        skills: formSkills,
        knowledge_bases: formKb,
        description: formDesc,
      });
      message.success(`专家「${formName}」已创建`);
      setCreateOpen(false);
      setFormName(''); setFormRole(''); setFormPrompt(''); setFormSkills([]); setFormKb([]); setFormDesc('');
      refresh();
    } catch (err: any) {
      message.error('创建失败: ' + (err?.message || '未知错误'));
    }
  };

  const handleRun = async (name: string) => {
    const task = prompt(`请输入给「${name}」的任务：`);
    if (!task) return;
    setRunning(name);
    setResult(null);
    try {
      const r = await runExpert(name, task);
      setResult(r);
      refresh(); // 刷新审批列表（可能产生新的授权请求）
    } catch (err: any) {
      message.error('运行失败: ' + (err?.message || '未知错误'));
    } finally {
      setRunning(null);
    }
  };

  const handleApprove = async (requestId: string, approved: boolean) => {
    try {
      await decideApproval(requestId, approved);
      message.success(approved ? '已批准' : '已拒绝');
      refresh();
    } catch (err: any) {
      message.error('操作失败: ' + (err?.message || '未知错误'));
    }
  };

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name', render: (t: string) => <Text strong>{t}</Text> },
    { title: '角色', dataIndex: 'role', key: 'role', ellipsis: true },
    { title: '技能', dataIndex: 'skills', key: 'skills', render: (s: string[]) => s?.length ? s.map(k => <Tag key={k} color="blue">{k}</Tag>) : <Text type="secondary">-</Text> },
    { title: '知识库', dataIndex: 'knowledge_bases', key: 'knowledge_bases', render: (k: string[]) => k?.length ? k.map(b => <Tag key={b} color="green">{b}</Tag>) : <Text type="secondary">-</Text> },
    { title: '操作', key: 'actions', render: (_: any, record: any) => (
      <Button type="primary" size="small" icon={<ThunderboltOutlined />} loading={running === record.name} onClick={() => handleRun(record.name)}>运行</Button>
    )},
  ];

  return (
    <div className="space-y-4 animate-fade-in">
      <Title level={4} className="!mb-0">智能体专家</Title>

      <Card
        title={<span className="flex items-center gap-2"><RobotOutlined /> 专属智能体</span>}
        extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>创建专家</Button>}
      >
        <Table dataSource={experts} rowKey="name" columns={columns} pagination={false}
          locale={{ emptyText: <Empty description="点击「创建专家」定义你的专属智能体" /> }} />
      </Card>

      {approvals.length > 0 && (
        <Card title={<span className="flex items-center gap-2"><SafetyOutlined /> 待授权操作</span>}>
          <Alert type="warning" showIcon className="mb-3" message="以下高危操作需要你明确授权后才能执行（每次授权）" />
          <div className="space-y-3">
            {approvals.map((a: any) => (
              <div key={a.request_id} className="border border-amber-300 dark:border-amber-700 rounded-lg p-3 bg-amber-50 dark:bg-amber-900/10">
                <div className="flex justify-between items-center">
                  <div>
                    <Tag color="orange">{a.tool_name}</Tag>
                    <Text className="ml-2">{a.reason}</Text>
                    <Text type="secondary" className="ml-2 text-xs">参数: {JSON.stringify(a.arguments)}</Text>
                  </div>
                  <Space>
                    <Button size="small" type="primary" onClick={() => handleApprove(a.request_id, true)}>批准</Button>
                    <Button size="small" danger onClick={() => handleApprove(a.request_id, false)}>拒绝</Button>
                  </Space>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {result && (
        <Card title="运行结果">
          <Text strong>输出：</Text>
          <Paragraph className="whitespace-pre-wrap mt-2 bg-gray-50 dark:bg-gray-800 p-3 rounded">{result.output}</Paragraph>
          {result.tool_calls?.length > 0 && (
            <div className="mt-2">
              <Text type="secondary">工具调用 {result.tool_calls.length} 次</Text>
            </div>
          )}
        </Card>
      )}

      <Modal title="创建专属智能体" open={createOpen} onOk={handleCreate} onCancel={() => setCreateOpen(false)} width={600} okText="创建" cancelText="取消">
        <Space direction="vertical" className="w-full" size="middle">
          <div>
            <Text strong className="block mb-1">专家名称 *</Text>
            <Input value={formName} onChange={e => setFormName(e.target.value)} placeholder="如：法务专家 / 数据分析师 / 我的助手" />
          </div>
          <div>
            <Text strong className="block mb-1">角色描述</Text>
            <Input value={formRole} onChange={e => setFormRole(e.target.value)} placeholder="如：你是资深法律顾问，擅长合同审核" />
          </div>
          <div>
            <Text strong className="block mb-1">系统提示词</Text>
            <TextArea rows={3} value={formPrompt} onChange={e => setFormPrompt(e.target.value)} placeholder="自定义行为指令..." />
          </div>
          <div>
            <Text strong className="block mb-1">可调用技能 / MCP 工具</Text>
            <Select mode="multiple" className="w-full" value={formSkills} onChange={setFormSkills}
              placeholder="选择技能" options={tools.map(t => ({ value: t.name, label: `${t.name}${t.requires_approval ? ' (需授权)' : ''}` }))} />
          </div>
          <div>
            <Text strong className="block mb-1">专属知识库</Text>
            <Select mode="tags" className="w-full" value={formKb} onChange={setFormKb} placeholder="输入知识库名，回车添加（如 default）" />
          </div>
          <div>
            <Text strong className="block mb-1">简介</Text>
            <Input value={formDesc} onChange={e => setFormDesc(e.target.value)} placeholder="一句话简介" />
          </div>
        </Space>
      </Modal>
    </div>
  );
}
