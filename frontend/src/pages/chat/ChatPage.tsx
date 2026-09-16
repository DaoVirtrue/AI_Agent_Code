import { useEffect, useCallback } from 'react';
import { Allotment } from 'allotment';
import 'allotment/dist/style.css';
import { useChatStore, useAppStore } from '@/store';
import { ConversationList } from './ConversationList';
import { ChatMessages } from './ChatMessages';
import { ChatInput } from './ChatInput';
import { ContextPanel } from './ContextPanel';
import { Empty } from 'antd';
import { MessageOutlined } from '@ant-design/icons';

export function ChatPage() {
  const activeConversationId = useChatStore((s) => s.activeConversationId);
  const conversations = useChatStore((s) => s.conversations);
  const activeConversation = conversations.find(c => c.id === activeConversationId);
  const setBreadcrumbs = useAppStore((s) => s.setBreadcrumbs);

  useEffect(() => {
    setBreadcrumbs([{ title: '对话' }]);
  }, [setBreadcrumbs]);

  const handleSend = useCallback(
    async (content: string, model: string, expertName?: string) => {
      const store = useChatStore.getState();
      await store.sendMessage(content, model || 'deepseek-chat', expertName);
    },
    []
  );

  return (
    <div className="h-[calc(100vh-120px)] rounded-xl overflow-hidden border border-gray-200 dark:border-gray-700 bg-white dark:bg-dark-900 animate-fade-in">
      <Allotment defaultSizes={[18, 54, 28]} minSize={180}>
        {/* Left Panel: Conversation List */}
        <Allotment.Pane>
          <ConversationList />
        </Allotment.Pane>

        {/* Center Panel: Messages + Input */}
        <Allotment.Pane>
          <div className="flex flex-col h-full">
            <div className="flex-1 min-h-0">
              {activeConversationId && activeConversation ? (
                <ChatMessages />
              ) : (
                <div className="flex items-center justify-center h-full">
                  <Empty
                    image={<MessageOutlined style={{ fontSize: 64, color: '#d9d9d9' }} />}
                    description={<span className="text-gray-400">输入消息开始对话</span>}
                  />
                </div>
              )}
            </div>
            <ChatInput onSend={handleSend} />
          </div>
        </Allotment.Pane>

        {/* Right Panel: Context */}
        <Allotment.Pane>
          <ContextPanel />
        </Allotment.Pane>
      </Allotment>
    </div>
  );
}
