import { useEffect, useState, useRef } from 'react';
import { Card, Select, Input, Button, Typography, Space, Empty, Tag, Descriptions } from 'antd';
import { RobotOutlined, SendOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useAppStore } from '@/store';
import { AGENT_TYPES, DEFAULT_MODEL, MODEL_OPTIONS } from '@/utils/constants';
import type { AgentStep } from '@/types';
import { formatDuration, formatNumber } from '@/utils/format';
import { StatusBadge } from '@/components/common/StatusBadge';

const { TextArea } = Input;
const { Title, Text, Paragraph } = Typography;

const MOCK_STEPS = [
  { type:'thought', content:'用户提出了一个问题。我需要先搜索相关知识库来获取背景信息。', toolName:'', toolInput:'', toolOutput:'' },
  { type:'action', content:'搜索相关知识库', toolName:'search_knowledge_base', toolInput:'{"query":"用户问题"}', toolOutput:'在知识库中找到3篇相关文档。' },
  { type:'observation', content:'知识库返回了丰富的结果。接下来需要深入分析这些信息。', toolName:'', toolInput:'', toolOutput:'' },
  { type:'action', content:'读取并分析参考文件', toolName:'read_file', toolInput:'{"path":"/docs/analysis.md"}', toolOutput:'文件包含详细的案例分析。' },
  { type:'observation', content:'获得了详细的参考资料。现在可以综合所有信息给出最终答案。', toolName:'', toolInput:'', toolOutput:'' },
];

const MOCK_RESULTS = [
  '## 分析结果\n\n根据知识库检索和深入分析，得出以下结论：\n\n1. **历史背景**：该问题涉及多个历史时期的复杂事件\n2. **关键因素**：多方面因素共同作用\n3. **现代意义**：对当今社会仍有深远影响',
  '## 综合报告\n\n经过多步骤推理和分析：\n\n| 维度 | 结论 |\n|------|------|\n| 准确性 | 基于可靠来源 |\n| 完整性 | 覆盖主要方面 |\n| 深度 | 多层次分析 |',
];

export function AgentPage() {
  const setBreadcrumbs = useAppStore((s) => s.setBreadcrumbs);
  const [agentType, setAgentType] = useState('react');
  const [model, setModel] = useState(DEFAULT_MODEL);
  const [input, setInput] = useState('');
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [running, setRunning] = useState(false);
  const [finalResult, setFinalResult] = useState('');
  const [finalStatus, setFinalStatus] = useState('');
  const timerRef = useRef<number>(0);

  useEffect(() => {
    setBreadcrumbs([{ title: 'Agent' }]);
    return () => clearTimeout(timerRef.current);
  }, [setBreadcrumbs]);

  const handleRun = async () => {
    if (!input.trim() || running) return;
    setRunning(true);
    setSteps([]);
    setFinalResult('');
    setFinalStatus('running');

    let stepNum = 0;
    for (const s of MOCK_STEPS) {
      await new Promise<void>(resolve => {
        timerRef.current = window.setTimeout(() => {
          setSteps(prev => [...prev, {
            step_number: ++stepNum, type: s.type,
            thought: s.type === 'thought' ? s.content : '',
            action: s.type === 'action' ? s.content : '',
            observation: s.type === 'observation' ? s.content : '',
            tool_name: s.toolName, tool_input: s.toolInput, tool_output: s.toolOutput,
            elapsed_ms: 500 + Math.random() * 800,
            tokens_used: 80 + Math.floor(Math.random() * 120),
          }]);
          resolve();
        }, 600 + Math.random() * 400);
      });
    }
    setFinalResult(MOCK_RESULTS[Math.floor(Math.random() * MOCK_RESULTS.length)]);
    setFinalStatus('completed');
    setRunning(false);
  };

  return (
    <div className="space-y-4 animate-fade-in">
      <Title level={4} className="!mb-0">Agent 运行器</Title>

      <Card title={<span className="flex items-center gap-2"><RobotOutlined /> 配置</span>}>
        <Space direction="vertical" className="w-full" size="middle">
          <div>
            <Text strong className="block mb-2">Agent 类型</Text>
            <Select value={agentType} onChange={setAgentType} className="w-full" options={AGENT_TYPES.map(a => ({ value: a.value, label: a.label }))} />
          </div>
          <div>
            <Text strong className="block mb-2">模型</Text>
            <Select value={model} onChange={setModel} className="w-full" options={MODEL_OPTIONS.map(m => ({ value: m.value, label: m.label }))} />
          </div>
          <div>
            <Text strong className="block mb-2">任务描述</Text>
            <TextArea rows={3} value={input} onChange={e => setInput(e.target.value)} placeholder="描述您需要 Agent 完成的任务..." />
          </div>
          <Button type="primary" icon={<SendOutlined />} onClick={handleRun} loading={running}
            disabled={!input.trim()} className="!rounded-lg"
            style={{ background: 'linear-gradient(135deg, #1677ff, #722ed1)', border: 'none' }}>
            运行 Agent
          </Button>
        </Space>
      </Card>

      {finalResult && (
        <div className="space-y-4">
          <Card title={<span className="flex items-center gap-2"><ThunderboltOutlined /> 执行日志</span>}>
            <div className="flex items-center gap-4 mb-4">
              <StatusBadge status={finalStatus as any} />
              <Text type="secondary">{finalStatus === 'completed' ? '已完成' : '运行中...'}</Text>
            </div>
            {steps.length === 0 ? (
              <Empty description="暂无执行步骤" />
            ) : (
              <div className="space-y-3">
                {steps.map((step: AgentStep, idx: number) => (
                  <div key={idx} className="border border-gray-200 dark:border-gray-700 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-2">
                      <Tag color={step.type === 'thought' ? 'blue' : step.type === 'action' ? 'green' : step.type === 'observation' ? 'orange' : 'purple'}>
                        {step.type === 'thought' ? '思考' : step.type === 'action' ? '行动' : step.type === 'observation' ? '观察' : '最终'}
                      </Tag>
                      <Text type="secondary" className="text-xs">步骤 {step.step_number}</Text>
                      {step.tool_name && <Tag>{step.tool_name}</Tag>}
                    </div>
                    <Paragraph className="!mb-0 text-sm">{step.type === 'thought' ? step.thought : step.type === 'action' ? step.action : step.observation}</Paragraph>
                  </div>
                ))}
              </div>
            )}
          </Card>
          <Card title="最终输出">
            <Paragraph className="!mb-0 whitespace-pre-wrap text-sm leading-relaxed">
              {finalResult}
            </Paragraph>
          </Card>
        </div>
      )}

      {!finalResult && !running && (
        <div className="flex items-center justify-center min-h-[200px]">
          <Empty description="配置并运行 Agent 以查看结果" />
        </div>
      )}
    </div>
  );
}
