import { useEffect, useRef } from 'react';
import { Avatar, Typography, Skeleton, Button, message } from 'antd';
import { UserOutlined, RobotOutlined, CopyOutlined, DownloadOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { useChatStore } from '@/store';

const { Text } = Typography;

function copyText(text: string) {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(() => message.success('已复制'));
  } else {
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    message.success('已复制');
  }
}

function downloadText(text: string, filename: string) {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  message.success('已导出下载');
}

export function ChatMessages() {
  const activeConversationId = useChatStore((s) => s.activeConversationId);
  const conversations = useChatStore((s) => s.conversations);
  const activeConversation = conversations.find(c => c.id === activeConversationId);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeConversation?.messages, isStreaming]);

  if (!activeConversation) {
    return null;
  }

  const messages = activeConversation.messages;

  return (
    <div
      ref={containerRef}
      className="h-full overflow-y-auto px-4 py-4 space-y-4 bg-white dark:bg-dark-900"
    >
      {messages.length === 0 && (
        <div className="flex flex-col items-center justify-center h-full text-center">
          <div
            className="flex items-center justify-center rounded-full mb-4"
            style={{
              width: 64,
              height: 64,
              background: 'linear-gradient(135deg, #1677ff, #722ed1)',
            }}
          >
            <RobotOutlined style={{ fontSize: 32, color: '#fff' }} />
          </div>
          <Text className="text-lg font-semibold text-gray-700 dark:text-gray-300">
            开始一段对话
          </Text>
          <Text type="secondary" className="mt-1 max-w-sm">
            发送消息开始聊天，AI 助手将实时回复。
          </Text>
        </div>
      )}

      {messages.map((message, index) => {
        const isUser = message.role === 'user';
        const isLastAssistant =
          !isUser && index === messages.length - 1 && isStreaming;

        return (
          <div
            key={message.id || index}
            className={`flex gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'} animate-slide-up`}
          >
            {/* Avatar */}
            <Avatar
              icon={isUser ? <UserOutlined /> : <RobotOutlined />}
              className="flex-shrink-0"
              style={{
                backgroundColor: isUser ? '#1677ff' : '#722ed1',
              }}
              size={36}
            />

            {/* Message Bubble */}
            <div className={`flex flex-col max-w-[75%] ${isUser ? 'items-end' : 'items-start'}`}>
              {/* Model name for assistant */}
              {!isUser && message.model && (
                <Text
                  className="text-xs mb-1 px-1"
                  type="secondary"
                  style={{ fontSize: 11 }}
                >
                  {message.model}
                  {message.latencyMs != null && (
                    <span className="ml-2">({message.latencyMs}ms)</span>
                  )}
                </Text>
              )}

              {/* Bubble */}
              <div
                className={`px-4 py-2.5 ${
                  isUser
                    ? 'bg-blue-500 text-white rounded-2xl rounded-br-md'
                    : 'bg-gray-100 dark:bg-dark-700 text-gray-900 dark:text-white rounded-2xl rounded-bl-md'
                }`}
              >
                {isUser ? (
                  <p className="m-0 whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
                ) : (
                  <div className="markdown-content text-sm">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      rehypePlugins={[rehypeHighlight]}
                    >
                      {message.content}
                    </ReactMarkdown>
                    {isLastAssistant && (
                      <span className="inline-block w-2 h-4 bg-blue-500 animate-pulse ml-0.5 align-text-bottom rounded-sm" />
                    )}
                  </div>
                )}
              </div>

              {/* Action buttons: copy + download (assistant messages only) */}
              {!isUser && message.content && (
                <div className="flex items-center gap-1 mt-1">
                  <Button
                    size="small"
                    type="text"
                    icon={<CopyOutlined />}
                    onClick={() => copyText(message.content || '')}
                    style={{ fontSize: 11, color: '#888' }}
                  >
                    复制
                  </Button>
                  <Button
                    size="small"
                    type="text"
                    icon={<DownloadOutlined />}
                    onClick={() => downloadText(message.content || '', `chat_${message.id || Date.now()}.md`)}
                    style={{ fontSize: 11, color: '#888' }}
                  >
                    导出
                  </Button>
                </div>
              )}

              {/* Timestamp */}
              {message.timestamp && (
                <Text
                  className="text-xs mt-1 px-1"
                  type="secondary"
                  style={{ fontSize: 10 }}
                >
                  {new Date(message.timestamp).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </Text>
              )}
            </div>
          </div>
        );
      })}

      {/* Streaming skeleton for initial loading (before any tokens arrive) */}
      {isStreaming && messages.length > 0 && messages[messages.length - 1].role === 'user' && (
        <div className="flex gap-3 animate-fade-in">
          <Avatar
            icon={<RobotOutlined />}
            className="flex-shrink-0"
            style={{ backgroundColor: '#722ed1' }}
            size={36}
          />
          <div className="bg-gray-100 dark:bg-dark-700 rounded-2xl rounded-bl-md px-4 py-3">
            <Skeleton active paragraph={{ rows: 1, width: [200] }} title={false} />
          </div>
        </div>
      )}

      <div ref={messagesEndRef} />
    </div>
  );
}
