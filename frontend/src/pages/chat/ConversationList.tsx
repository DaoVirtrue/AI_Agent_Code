import { useMemo, useState, useCallback } from 'react';
import { List, Input, Button, Popconfirm, Typography } from 'antd';
import {
  SearchOutlined,
  PlusOutlined,
  DeleteOutlined,
  MessageOutlined,
} from '@ant-design/icons';
import { useChatStore } from '@/store';
import { formatDateRelative, truncateText } from '@/utils/format';

const { Text, Paragraph } = Typography;

export function ConversationList() {
  const {
    conversations,
    activeConversationId,
    createConversation,
    deleteConversation,
    setActiveConversation,
  } = useChatStore();

  const [searchText, setSearchText] = useState('');

  const filteredConversations = useMemo(() => {
    if (!searchText.trim()) return conversations;
    const lower = searchText.toLowerCase();
    return conversations.filter(
      (c) =>
        c.title.toLowerCase().includes(lower) ||
        c.messages.some((m) => m.content.toLowerCase().includes(lower))
    );
  }, [conversations, searchText]);

  const handleNewChat = useCallback(() => {
    createConversation();
  }, [createConversation]);

  const handleDelete = useCallback(
    (id: string, e?: React.MouseEvent) => {
      e?.stopPropagation();
      deleteConversation(id);
    },
    [deleteConversation]
  );

  const getLastMessage = (conv: (typeof conversations)[0]) => {
    const msgs = conv.messages;
    if (msgs.length === 0) return '暂无消息';
    const last = msgs[msgs.length - 1];
    return `${last.role === 'user' ? '我' : '助手'}: ${truncateText(last.content, 50)}`;
  };

  return (
    <div className="flex flex-col h-full bg-gray-50 dark:bg-dark-800 border-r border-gray-200 dark:border-gray-700">
      {/* Header */}
      <div className="p-3 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between mb-2">
          <Text strong className="text-base text-gray-900 dark:text-white">
            对话列表
          </Text>
          <Button
            type="primary"
            size="small"
            icon={<PlusOutlined />}
            onClick={handleNewChat}
            className="!rounded-lg"
          >
            新建对话
          </Button>
        </div>
        <Input
          placeholder="搜索对话..."
          prefix={<SearchOutlined className="text-gray-400" />}
          size="small"
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          allowClear
          className="!rounded-lg"
        />
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {filteredConversations.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400 p-4">
            <MessageOutlined style={{ fontSize: 32, marginBottom: 8 }} />
            <Text type="secondary" className="text-sm text-center">
              {searchText ? '没有匹配的对话' : '暂无对话'}
            </Text>
            {!searchText && (
              <Button type="link" onClick={handleNewChat} size="small" className="mt-1">
                开始新对话
              </Button>
            )}
          </div>
        ) : (
          <List
            dataSource={filteredConversations}
            split={true}
            renderItem={(item) => {
              const isActive = item.id === activeConversationId;
              return (
                <List.Item
                  key={item.id}
                  onClick={() => setActiveConversation(item.id)}
                  className={`cursor-pointer pl-5 pr-3 py-3 transition-colors hover:bg-gray-100 dark:hover:bg-dark-700 ${
                    isActive
                      ? 'bg-blue-50 dark:bg-blue-900/20 border-l-2 border-l-blue-500'
                      : 'border-l-2 border-l-transparent'
                  }`}
                  actions={[
                    <Popconfirm
                      key="delete"
                      title="确定删除此对话？"
                      description="此操作无法撤销。"
                      onConfirm={(e?: React.MouseEvent) => handleDelete(item.id, e)}
                      onCancel={(e?: React.MouseEvent) => e?.stopPropagation()}
                      okText="删除"
                      cancelText="取消"
                      placement="left"
                    >
                      <Button
                        type="text"
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Popconfirm>,
                  ]}
                >
                  <List.Item.Meta
                    title={
                      <Text
                        strong={isActive}
                        className={`text-sm ${isActive ? 'text-blue-600 dark:text-blue-400' : 'text-gray-900 dark:text-white'}`}
                      >
                        {truncateText(item.title, 30)}
                      </Text>
                    }
                    description={
                      <div className="flex flex-col gap-0.5">
                        <Text
                          type="secondary"
                          className="text-xs !leading-tight"
                          style={{ fontSize: 11 }}
                        >
                          {getLastMessage(item)}
                        </Text>
                        <Text
                          type="secondary"
                          className="text-xs"
                          style={{ fontSize: 10 }}
                        >
                          {formatDateRelative(item.updatedAt)}
                        </Text>
                      </div>
                    }
                  />
                </List.Item>
              );
            }}
          />
        )}
      </div>
    </div>
  );
}
