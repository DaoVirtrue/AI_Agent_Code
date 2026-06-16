import { Radio, Tooltip } from 'antd';
import {
  RobotOutlined,
  BranchesOutlined,
  SyncOutlined,
  BulbOutlined,
  AppstoreOutlined,
  CodeOutlined,
  SearchOutlined,
  ToolOutlined,
  MessageOutlined,
} from '@ant-design/icons';
import { useAgentStore } from '@/store/agentStore';
import { AGENT_TYPES } from '@/utils/constants';

interface AgentOption {
  value: string;
  label: string;
  icon: React.ReactNode;
  description: string;
}

const AGENT_ICON_MAP: Record<string, React.ReactNode> = {
  chat: <MessageOutlined />,
  rag: <SearchOutlined />,
  tool_use: <ToolOutlined />,
  code: <CodeOutlined />,
  research: <BulbOutlined />,
  planner: <BranchesOutlined />,
  react: <RobotOutlined />,
  orchestrator: <AppstoreOutlined />,
};

function getAgentOptions(): AgentOption[] {
  return AGENT_TYPES.map((agent) => ({
    value: agent.value,
    label: agent.label,
    icon: AGENT_ICON_MAP[agent.value] || <AppstoreOutlined />,
    description: agent.description,
  }));
}

export default function AgentSelector() {
  const { agentType, setAgentType } = useAgentStore();
  const options = getAgentOptions();

  return (
    <Radio.Group
      value={agentType}
      onChange={(e) => setAgentType(e.target.value)}
      optionType="button"
      buttonStyle="solid"
      size="large"
      className="w-full"
    >
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {options.map((option) => (
          <Tooltip key={option.value} title={option.description} placement="top">
            <Radio.Button
              value={option.value}
              className="w-full h-full py-2 px-1 text-center"
              style={{ whiteSpace: 'normal', wordBreak: 'break-word', minHeight: 48 }}
            >
              <div className="flex flex-col items-center justify-center gap-0.5">
                <span className="text-base">{option.icon}</span>
                <span className="text-xs leading-tight">{option.label}</span>
              </div>
            </Radio.Button>
          </Tooltip>
        ))}
      </div>
    </Radio.Group>
  );
}
