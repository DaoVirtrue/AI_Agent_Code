import { Input } from 'antd';
import { useAgentStore } from '@/store/agentStore';

const { TextArea } = Input;

export default function TaskInput() {
  const { task, setTask } = useAgentStore();

  return (
    <div className="w-full">
      <TextArea
        value={task}
        onChange={(e) => setTask(e.target.value)}
        placeholder={'请详细描述您的任务...\n\n示例：调研多 Agent 系统的最新 AI 论文，并生成一份总结报告。'}
        rows={6}
        maxLength={50000}
        showCount
        autoSize={{ minRows: 4, maxRows: 12 }}
        className="w-full font-mono text-sm resize-none"
      />
    </div>
  );
}
