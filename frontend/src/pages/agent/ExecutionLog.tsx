import { Timeline, Tag, Typography, Spin, Empty } from 'antd';
import {
  CheckCircleOutlined,
  LoadingOutlined,
  BulbOutlined,
  ToolOutlined,
  EyeOutlined,
} from '@ant-design/icons';
import { useEffect, useRef } from 'react';
import { useAgentStore } from '@/store/agentStore';
import { formatDateRelative } from '@/utils/format';
import type { AgentStep } from '@/types/agent';

const { Text } = Typography;

interface StepDisplayConfig {
  icon: React.ReactNode;
  color: string;
  label: string;
}

const STEP_CONFIG: Record<string, StepDisplayConfig> = {
  thought: {
    icon: <BulbOutlined />,
    color: 'orange',
    label: '思考',
  },
  action: {
    icon: <ToolOutlined />,
    color: 'blue',
    label: '行动',
  },
  observation: {
    icon: <EyeOutlined />,
    color: 'green',
    label: '观察',
  },
  final: {
    icon: <CheckCircleOutlined />,
    color: 'green',
    label: '最终答案',
  },
};

function getDotColor(type: string, content: string): string {
  const hasError = content.toLowerCase().includes('error');
  if (hasError) return '#ff4d4f';

  switch (type) {
    case 'thought':
      return '#fa8c16';
    case 'action':
      return '#1677ff';
    case 'observation':
      return '#52c41a';
    case 'final':
      return '#52c41a';
    default:
      return '#8c8c8c';
  }
}

function isErrorType(type: string, content: string): boolean {
  return content.toLowerCase().includes('error');
}

function renderStepContent(step: AgentStep): React.ReactNode {
  const config = STEP_CONFIG[step.type] || {
    icon: <BulbOutlined />,
    color: 'default',
    label: step.type,
  };
  const hasError = isErrorType(step.type, step.content);
  const tagColor = hasError ? 'red' : config.color;

  return (
    <div className="py-1">
      {/* Step header with type badge and metadata */}
      <div className="flex items-center gap-2 mb-1.5 flex-wrap">
        <Tag
          color={tagColor}
          icon={config.icon}
          className="flex items-center gap-1"
        >
          {config.label}
        </Tag>
        <Text type="secondary" className="text-xs">
          步骤 {step.step_number}
        </Text>
        {step.timestamp && (
          <Text type="secondary" className="text-xs">
            {formatDateRelative(step.timestamp)}
          </Text>
        )}
        {step.token_usage && (
          <Tag className="text-xs" color="default">
            {step.token_usage.total_tokens} tokens
          </Tag>
        )}
      </div>

      {/* Tool name and input for action steps */}
      {step.type === 'action' && step.tool_name && (
        <div className="mb-2">
          <Text code className="text-xs">
            tool: {step.tool_name}
          </Text>
          {step.tool_input && Object.keys(step.tool_input).length > 0 && (
            <Text
              code
              className="text-xs bg-gray-50 dark:bg-dark-800 p-1.5 rounded block mt-1 whitespace-pre-wrap break-all"
            >
              {JSON.stringify(step.tool_input, null, 2)}
            </Text>
          )}
        </div>
      )}

      {/* Step content */}
      <div
        className={
          step.type === 'thought'
            ? 'italic text-gray-500 dark:text-gray-400 text-sm leading-relaxed'
            : 'text-sm leading-relaxed'
        }
      >
        <Text>{step.content}</Text>
      </div>
    </div>
  );
}

export default function ExecutionLog() {
  const { steps, isRunning, elapsedMs } = useAgentStore();
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new steps arrive
  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [steps.length]);

  // Empty state
  if (steps.length === 0 && !isRunning) {
    return (
      <Empty
        description="暂无执行步骤"
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        className="py-10"
      />
    );
  }

  // Build timeline items
  const timelineItems = steps.map((step, index) => {
    const hasError = isErrorType(step.type, step.content);
    return {
      key: `step-${step.step_number}-${index}`,
      dot: (
        <div
          className="w-3 h-3 rounded-full border-2 border-white dark:border-dark-800 shadow-sm flex-shrink-0"
          style={{ backgroundColor: getDotColor(step.type, step.content) }}
        />
      ),
      children: renderStepContent(step),
      color: hasError ? 'red' : undefined,
    };
  });

  // Append a running indicator if agent is still processing
  if (isRunning) {
    timelineItems.push({
      key: 'running-indicator',
      dot: <LoadingOutlined className="text-blue-500 text-base" />,
      children: (
        <div className="flex items-center gap-2 py-1">
          <Spin
            indicator={<LoadingOutlined style={{ fontSize: 16 }} spin />}
            size="small"
          />
          <Text type="secondary" italic className="text-sm">
            执行中...
          </Text>
          {elapsedMs > 0 && (
            <Text type="secondary" className="text-xs">
              (已运行 {(elapsedMs / 1000).toFixed(1)}秒)
            </Text>
          )}
        </div>
      ),
    });
  }

  return (
    <div
      ref={containerRef}
      className="max-h-[500px] overflow-y-auto pr-2 scrollbar-thin"
    >
      <Timeline items={timelineItems} className="pt-1" />
      <div ref={bottomRef} />
    </div>
  );
}
