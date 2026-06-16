import { Tabs, List, Timeline, Tag, Descriptions, Empty, Typography } from 'antd';
const { Text } = Typography;
import {
  FileTextOutlined,
  NodeIndexOutlined,
  DollarOutlined,
} from '@ant-design/icons';
import { useChatStore } from '@/store';
import { formatNumber, formatCurrency } from '@/utils/format';

export function ContextPanel() {
  const conversations = useChatStore((s) => s.conversations);
  const activeId = useChatStore((s) => s.activeConversationId);
  const activeConversation = conversations.find(c => c.id === activeId);

  const lastUserMsg = activeConversation?.messages?.filter((m: any) => m.role === 'user').pop()?.content || '';
  const sources = (() => {
    // Always compute from localStorage for accurate real-time scoring
    try {
      const docs = JSON.parse(localStorage.getItem('llm_platform_rag_documents') || '[]');
      const kw = lastUserMsg.split(/[\s,，。！？、；：]+/).flatMap((k: string) => {
        if (k.length <= 3) return [k];
        const parts = k.match(/[a-zA-Z]+|[一-龥]{1,4}/g) || [k];
        return parts.filter((p: string) => p.length > 1);
      }).filter((k: string) => k.length > 1);
      if (kw.length === 0) return [];
      return docs.flatMap((d: any) =>
        (d.chunks || []).map((c: string, i: number) => {
          const lower = c.toLowerCase();
          let matches = 0;
          kw.forEach((k: string) => { if (lower.includes(k.toLowerCase())) matches++; });
          return { chunk_id: `${d.document_id}_${i}`, document_name: d.filename, content: c.substring(0, 200), score: matches / kw.length };
        })
      ).filter((s: any) => s.score >= 0.3).sort((a: any, b: any) => b.score - a.score).slice(0, 8);
    } catch { return []; }
  })();
  const lastMessage = activeConversation?.messages?.filter((m) => m.role === 'assistant').pop();
  const tokenUsage = lastMessage?.tokenUsage || null;
  const activeTab = tokenUsage ? 'tokens' : 'sources';

  const tabItems = [
    {
      key: 'sources',
      label: (
        <span className="flex items-center gap-1">
          <FileTextOutlined />
          引用来源
        </span>
      ),
      children: (
        <div className="p-2 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 260px)' }}>
          {sources.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="对话时将自动检索知识库" className="mt-8" />
          ) : (
            <List dataSource={sources} renderItem={(s: any) => (
              <List.Item className="!px-2 !py-3">
                <div className="w-full"><div className="flex justify-between mb-1"><Text strong className="text-sm">{s.document_name}</Text><Tag color="blue">{Math.round((s.score||0)*100)}%</Tag></div><Text className="text-xs text-gray-500 line-clamp-2">{s.content?.substring(0,150)}</Text></div>
              </List.Item>
            )} />
          )}
        </div>
      ),
    },
    {
      key: 'agentSteps',
      label: (
        <span className="flex items-center gap-1">
          <NodeIndexOutlined />
          Agent 步骤
        </span>
      ),
      children: (
        <div className="p-2 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 260px)' }}>
          {(!activeConversation?.agentSteps || activeConversation.agentSteps.length === 0) ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="发送复杂问题后，AI 的思维链将在此显示" className="mt-8" />
          ) : (
            <Timeline
              items={(activeConversation?.agentSteps || []).map((step: any) => {
                let color = 'blue';
                if (step.type === 'thought') color = 'blue';
                else if (step.type === 'action') color = 'green';
                else if (step.type === 'observation') color = 'orange';
                else if (step.type === 'final') color = 'purple';

                return {
                  color,
                  children: (
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <Tag color={color} className="!text-xs !leading-tight capitalize">
                          {step.type}
                        </Tag>
                        {step.step_number != null && (
                          <span className="text-xs text-gray-400">步骤 {step.step_number}</span>
                        )}
                      </div>
                      {step.tool_name && (
                        <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-0.5">
                          工具: {step.tool_name}
                        </p>
                      )}
                      <p className="text-xs text-gray-500 dark:text-gray-400 m-0 whitespace-pre-wrap">
                        {step.content}
                      </p>
                    </div>
                  ),
                };
              })}
            />
          )}
        </div>
      ),
    },
    {
      key: 'tokens',
      label: (
        <span className="flex items-center gap-1">
          <DollarOutlined />
          Token 统计
        </span>
      ),
      children: (
        <div className="p-4">
          {!tokenUsage ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="对话后将在此显示引用来源和 Token 用量"
              className="mt-8"
            />
          ) : (
            <Descriptions
              column={1}
              size="small"
              bordered
              colon={false}
              labelStyle={{ fontWeight: 500, fontSize: 13, width: '50%', whiteSpace: 'normal' }}
              contentStyle={{ fontSize: 13, width: '50%', whiteSpace: 'normal', wordBreak: 'break-all' }}
            >
              <Descriptions.Item label="输入 Token">{formatNumber(tokenUsage.prompt_tokens, 0)} <span className="text-xs text-gray-400">($0.27/1M)</span></Descriptions.Item>
              <Descriptions.Item label="输出 Token">{formatNumber(tokenUsage.completion_tokens, 0)} <span className="text-xs text-gray-400">($1.10/1M)</span></Descriptions.Item>
              <Descriptions.Item label="Token 总计"><span className="font-semibold">{formatNumber(tokenUsage.total_tokens, 0)}</span></Descriptions.Item>
              <Descriptions.Item label="输入费用">${((tokenUsage.prompt_tokens||0) * 0.27 / 1000000).toFixed(6)}</Descriptions.Item>
              <Descriptions.Item label="输出费用">${((tokenUsage.completion_tokens||0) * 1.10 / 1000000).toFixed(6)}</Descriptions.Item>
              <Descriptions.Item label="总费用 (USD)"><span className="font-semibold text-green-600">${(((tokenUsage.prompt_tokens||0) * 0.27 + (tokenUsage.completion_tokens||0) * 1.10) / 1000000).toFixed(6)}</span></Descriptions.Item>
              <Descriptions.Item label="模型"><span className="text-xs">{lastMessage?.model || 'DeepSeek V4'}</span></Descriptions.Item>
            </Descriptions>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="h-full bg-gray-50 dark:bg-dark-800 border-l border-gray-200 dark:border-gray-700 flex flex-col">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <span className="text-sm font-semibold text-gray-900 dark:text-white">上下文</span>
      </div>

      {/* Tabs */}
      <div className="flex-1 overflow-hidden">
        <Tabs
          items={tabItems}
          defaultActiveKey={activeTab}
          size="small"
          tabBarStyle={{
            paddingLeft: 12,
            paddingRight: 12,
            marginBottom: 0,
          }}
          className="h-full"
          style={{ height: '100%' }}
        />
      </div>
    </div>
  );
}
