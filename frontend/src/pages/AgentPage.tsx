import { useEffect } from 'react';
import { Card, Select, Input, Button, Typography, Space, Empty, Tag } from 'antd';
import { RobotOutlined, SendOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useAppStore } from '@/store';
import { useAgentStore } from '@/store/agentStore';
import { AGENT_TYPES, DEFAULT_MODEL, MODEL_OPTIONS } from '@/utils/constants';
import type { AgentStep } from '@/types';
import { StatusBadge } from '@/components/common/StatusBadge';

const { TextArea } = Input;
const { Title, Text, Paragraph } = Typography;

export function AgentPage() {
  const setBreadcrumbs = useAppStore((s) => s.setBreadcrumbs);
  const {
    agentType, task, model, maxSteps, isRunning, steps, finalResult, finalStatus,
    totalSteps, elapsedMs, tokenUsage, costUsd, loopDetected, error,
    setAgentType, setTask, setModel, setMaxSteps, runAgent, clearResult,
  } = useAgentStore();

  useEffect(() => {
    setBreadcrumbs([{ title: 'Agent' }]);
  }, [setBreadcrumbs]);

  return (
    <div className="space-y-4 animate-fade-in">
      <Title level={4} className="!mb-0">Agent 运行器</Title>

      <Card title={<span className="flex items-center gap-2"><RobotOutlined /> 配置</span>}>
        <Space direction="vertical" className="w-full" size="middle">
          <div>
            <Text strong className="block mb-2">Agent 类型</Text>
            <Select
              value={agentType}
              onChange={setAgentType}
              className="w-full"
              options={AGENT_TYPES.map((a) => ({ value: a.value, label: a.label }))}
            />
          </div>
          <div>
            <Text strong className="block mb-2">模型</Text>
            <Select
              value={model}
              onChange={setModel}
              className="w-full"
              options={MODEL_OPTIONS.map((m) => ({ value: m.value, label: m.label }))}
            />
          </div>
          <div>
            <Text strong className="block mb-2">最大步数</Text>
            <Input
              type="number"
              value={maxSteps}
              onChange={(e) => setMaxSteps(Number(e.target.value))}
              min={1}
              max={100}
            />
          </div>
          <div>
            <Text strong className="block mb-2">任务描述</Text>
            <TextArea
              rows={3}
              value={task}
              onChange={(e) => setTask(e.target.value)}
              placeholder="描述您需要 Agent 完成的任务..."
            />
          </div>
          <Space>
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={runAgent}
              loading={isRunning}
              disabled={!task.trim()}
              className="!rounded-lg"
              style={{ background: 'linear-gradient(135deg, #1677ff, #722ed1)', border: 'none' }}
            >
              运行 Agent
            </Button>
            <Button onClick={clearResult} disabled={isRunning}>清空</Button>
          </Space>
        </Space>
      </Card>

      {(finalResult || error) && (
        <div className="space-y-4">
          <Card title={<span className="flex items-center gap-2"><ThunderboltOutlined /> 执行日志</span>}>
            <div className="flex items-center gap-4 mb-4">
              <StatusBadge status={finalStatus as any} />
              <Text type="secondary">
                总步数 {totalSteps} · 耗时 {elapsedMs}ms · 成本 ${costUsd.toFixed(6)}
                {loopDetected && <Tag color="orange">检测到循环</Tag>}
              </Text>
            </div>
            {tokenUsage && (
              <Text type="secondary" className="block mb-2">
                Tokens: {tokenUsage.prompt_tokens} prompt / {tokenUsage.completion_tokens} completion
              </Text>
            )}
            {steps.length === 0 ? (
              <Empty description="暂无执行步骤" />
            ) : (
              <div className="space-y-3">
                {steps.map((step: AgentStep, idx: number) => (
                  <div key={idx} className="border border-gray-200 dark:border-gray-700 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-2">
                      <Tag color={step.action === 'error' ? 'red' : step.action === 'final_answer' ? 'purple' : step.tool_name ? 'green' : 'blue'}>
                        {step.action}
                      </Tag>
                      <Text type="secondary" className="text-xs">步骤 {step.step_number}</Text>
                      {step.tool_name && <Tag>{step.tool_name}</Tag>}
                    </div>
                    {step.thought && <Paragraph className="!mb-1 text-sm text-gray-500">思考: {step.thought}</Paragraph>}
                    <Paragraph className="!mb-0 text-sm">{step.observation || step.tool_output}</Paragraph>
                  </div>
                ))}
              </div>
            )}
          </Card>
          <Card title="最终输出">
            <Paragraph className="!mb-0 whitespace-pre-wrap text-sm leading-relaxed">
              {finalResult || error}
            </Paragraph>
          </Card>
        </div>
      )}

      {!finalResult && !error && !isRunning && (
        <div className="flex items-center justify-center min-h-[200px]">
          <Empty description="配置并运行 Agent 以查看结果" />
        </div>
      )}
    </div>
  );
}
