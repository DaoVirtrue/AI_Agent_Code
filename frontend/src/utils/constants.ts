export const API_BASE_URL = '/api';

export const MODEL_OPTIONS = [
  { value: 'gpt-4.1', label: 'GPT-4.1', provider: 'OpenAI', pricing: { input: 2.00, output: 8.00 } },
  { value: 'gpt-4o', label: 'GPT-4o', provider: 'OpenAI', pricing: { input: 2.50, output: 10.00 } },
  { value: 'claude-sonnet-4-20250514', label: 'Claude Sonnet 4', provider: 'Anthropic', pricing: { input: 3.00, output: 15.00 } },
  { value: 'deepseek-chat', label: 'DeepSeek V4', provider: 'DeepSeek', pricing: { input: 0.27, output: 1.10 } },
  { value: 'qwen3-max', label: 'Qwen3 Max', provider: 'Alibaba', pricing: { input: 2.00, output: 8.00 } },
];

export const AGENT_TYPES = [
  { value: 'chat', label: '对话型 Agent', description: '通用对话 Agent' },
  { value: 'rag', label: 'RAG Agent', description: 'RAG 检索增强生成 Agent' },
  { value: 'tool_use', label: '工具型 Agent', description: '具备工具调用能力的 Agent' },
  { value: 'code', label: '编程 Agent', description: '代码生成与分析 Agent' },
  { value: 'research', label: '研究 Agent', description: '多步骤研究 Agent' },
  { value: 'planner', label: '规划 Agent', description: '任务规划与分解 Agent' },
  { value: 'react', label: 'ReAct', description: '推理+行动循环 Agent' },
  { value: 'orchestrator', label: '编排器', description: '多 Agent 编排器' },
];

export const TIER_LABELS: Record<string, string> = {
  free: '免费版',
  pro: '专业版',
  enterprise: '企业版',
  admin: '管理员',
};

export const ROLE_LABELS: Record<string, string> = {
  admin: '管理员',
  developer: '开发者',
  viewer: '观察者',
};

export const DEFAULT_MODEL = 'deepseek-chat';
export const DEFAULT_TEMPERATURE = 0.7;
export const DEFAULT_MAX_TOKENS = 4096;
