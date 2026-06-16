import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useChatStore } from '@/store/chatStore';

// Mock the chat API: chatStore calls sendChatMessageStream from @/api/chat
vi.mock('@/api/chat', () => ({
  sendChatMessage: vi.fn(),
  sendChatMessageStream: vi.fn(),
}));

import { sendChatMessageStream } from '@/api/chat';

// Helper: reset store to clean state before each test
function resetStore() {
  useChatStore.setState({
    conversations: [],
    activeConversationId: null,
    isStreaming: false,
    isLoading: false,
    error: null,
  });
}

describe('useChatStore - 聊天状态管理', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetStore();
  });

  describe('initial state - 初始状态', () => {
    it('初始时 conversations 为空数组', () => {
      const state = useChatStore.getState();
      expect(state.conversations).toEqual([]);
    });

    it('初始时 activeConversationId 为 null', () => {
      const state = useChatStore.getState();
      expect(state.activeConversationId).toBeNull();
    });

    it('初始时 isStreaming 为 false', () => {
      const state = useChatStore.getState();
      expect(state.isStreaming).toBe(false);
    });

    it('初始时 isLoading 为 false', () => {
      const state = useChatStore.getState();
      expect(state.isLoading).toBe(false);
    });

    it('初始时 error 为 null', () => {
      const state = useChatStore.getState();
      expect(state.error).toBeNull();
    });
  });

  describe('createConversation - 创建会话', () => {
    it('创建新的会话并添加到 conversations 数组', () => {
      const id = useChatStore.getState().createConversation('Test Chat');

      const state = useChatStore.getState();
      expect(state.conversations.length).toBe(1);
      expect(state.conversations[0].title).toBe('Test Chat');
      expect(state.conversations[0].id).toBe(id);
      expect(state.conversations[0].messages).toEqual([]);
    });

    it('创建会话时自动设置为活跃会话', () => {
      const id = useChatStore.getState().createConversation('My Chat');

      const state = useChatStore.getState();
      expect(state.activeConversationId).toBe(id);
    });

    it('未指定标题时使用默认标题 "New Chat"', () => {
      useChatStore.getState().createConversation();

      expect(useChatStore.getState().conversations[0].title).toBe('New Chat');
    });

    it('可指定模型', () => {
      useChatStore.getState().createConversation('GPT Chat', 'gpt-4');

      expect(useChatStore.getState().conversations[0].model).toBe('gpt-4');
    });

    it('创建多个会话时新会话位于数组最前面', () => {
      useChatStore.getState().createConversation('First');
      useChatStore.getState().createConversation('Second');

      const conversations = useChatStore.getState().conversations;
      expect(conversations.length).toBe(2);
      expect(conversations[0].title).toBe('Second');
      expect(conversations[1].title).toBe('First');
    });

    it('创建会话时清除之前的错误', () => {
      useChatStore.setState({ error: 'Previous error' });

      useChatStore.getState().createConversation('New');

      expect(useChatStore.getState().error).toBeNull();
    });
  });

  describe('deleteConversation - 删除会话', () => {
    it('删除指定会话', () => {
      const id1 = useChatStore.getState().createConversation('Chat A');
      const id2 = useChatStore.getState().createConversation('Chat B');

      useChatStore.getState().deleteConversation(id1);

      const state = useChatStore.getState();
      expect(state.conversations.length).toBe(1);
      expect(state.conversations[0].id).toBe(id2);
    });

    it('删除活跃会话时将活跃会话切换到第一个剩余会话', () => {
      const id1 = useChatStore.getState().createConversation('Chat 1');
      const id2 = useChatStore.getState().createConversation('Chat 2');

      // id2 is active (created last = first in array)
      expect(useChatStore.getState().activeConversationId).toBe(id2);

      useChatStore.getState().deleteConversation(id2);

      expect(useChatStore.getState().activeConversationId).toBe(id1);
    });

    it('删除最后一个会话时将活跃会话设置为 null', () => {
      const id = useChatStore.getState().createConversation('Only Chat');

      useChatStore.getState().deleteConversation(id);

      expect(useChatStore.getState().activeConversationId).toBeNull();
      expect(useChatStore.getState().conversations.length).toBe(0);
    });

    it('删除非活跃会话时不影响活跃会话', () => {
      const id1 = useChatStore.getState().createConversation('Active');
      const id2 = useChatStore.getState().createConversation('Inactive');
      // id2 is active (most recent), set id1 as active
      useChatStore.getState().setActiveConversation(id1);

      useChatStore.getState().deleteConversation(id2);

      expect(useChatStore.getState().activeConversationId).toBe(id1);
    });
  });

  describe('setActiveConversation - 切换活跃会话', () => {
    it('切换活跃会话到指定 ID', () => {
      const id1 = useChatStore.getState().createConversation('Chat X');
      const id2 = useChatStore.getState().createConversation('Chat Y');

      useChatStore.getState().setActiveConversation(id1);

      expect(useChatStore.getState().activeConversationId).toBe(id1);
    });

    it('切换会话时清除错误信息', () => {
      useChatStore.setState({ error: 'Some error' });
      const id = useChatStore.getState().createConversation('Chat');

      useChatStore.getState().setActiveConversation(id);

      expect(useChatStore.getState().error).toBeNull();
    });
  });

  describe('activeConversation getter', () => {
    it('返回当前活跃的会话对象', () => {
      const id = useChatStore.getState().createConversation('Getter Test');

      const active = useChatStore.getState().activeConversation;

      expect(active).toBeDefined();
      expect(active!.id).toBe(id);
      expect(active!.title).toBe('Getter Test');
    });

    it('当没有活跃会话时返回 undefined', () => {
      const active = useChatStore.getState().activeConversation;

      expect(active).toBeUndefined();
    });
  });

  describe('sendMessage - 发送消息', () => {
    it('发送消息后添加用户消息到会話中', async () => {
      // Set up a mock that streams a simple response
      vi.mocked(sendChatMessageStream).mockImplementation(
        async (_request, onChunk, onDone, _onError, _signal) => {
          onChunk('Hello ');
          onChunk('World');
          onDone();
        }
      );

      const convId = useChatStore.getState().createConversation('Stream Test');
      await useChatStore.getState().sendMessage('Hello');

      const state = useChatStore.getState();
      const conv = state.conversations.find((c) => c.id === convId);
      expect(conv).toBeDefined();
      // Should have user message + assistant message
      expect(conv!.messages.length).toBeGreaterThanOrEqual(2);
      // First message should be from user
      const userMsg = conv!.messages.find((m) => m.role === 'user');
      expect(userMsg).toBeDefined();
      expect(userMsg!.content).toBe('Hello');
    });

    it('流式响应完成后 assistant 消息包含完整内容', async () => {
      vi.mocked(sendChatMessageStream).mockImplementation(
        async (_request, onChunk, onDone, _onError, _signal) => {
          onChunk('The ');
          onChunk('answer ');
          onChunk('is 42');
          onDone();
        }
      );

      const convId = useChatStore.getState().createConversation('Content Test');
      await useChatStore.getState().sendMessage('What is the answer?');

      const conv = useChatStore.getState().conversations.find((c) => c.id === convId);
      const assistantMsg = conv!.messages.find((m) => m.role === 'assistant');
      expect(assistantMsg).toBeDefined();
      expect(assistantMsg!.content).toBe('The answer is 42');
    });

    it('流式响应完成后 isStreaming 恢复为 false', async () => {
      vi.mocked(sendChatMessageStream).mockImplementation(
        async (_request, onChunk, onDone, _onError, _signal) => {
          onChunk('Hi');
          onDone();
        }
      );

      useChatStore.getState().createConversation();
      await useChatStore.getState().sendMessage('Hi');

      expect(useChatStore.getState().isStreaming).toBe(false);
    });

    it('当没有活跃会话时自动创建新会话', async () => {
      vi.mocked(sendChatMessageStream).mockImplementation(
        async (_request, onChunk, onDone, _onError, _signal) => {
          onChunk('Auto-created');
          onDone();
        }
      );

      // No conversation created - sendMessage should auto-create
      await useChatStore.getState().sendMessage('First message');

      const state = useChatStore.getState();
      expect(state.conversations.length).toBe(1);
      expect(state.activeConversationId).not.toBeNull();
      expect(state.conversations[0].title).toBe('First message');
    });

    it('sendMessage 在流式进行中时不会发送重复消息', async () => {
      // Set store as streaming
      useChatStore.getState().createConversation('Busy');
      useChatStore.setState({ isStreaming: true });

      await useChatStore.getState().sendMessage('Should be ignored');

      // The mock should not have been called since isStreaming was true
      expect(sendChatMessageStream).not.toHaveBeenCalled();
    });

    it('sendMessage 忽略空内容消息', async () => {
      useChatStore.getState().createConversation('Empty');

      await useChatStore.getState().sendMessage('   ');

      // Should return early due to !content.trim()
      expect(sendChatMessageStream).not.toHaveBeenCalled();
    });

    it('sendMessage 在发生错误时设置 error 状态', async () => {
      vi.mocked(sendChatMessageStream).mockRejectedValue(
        new Error('Stream connection failed')
      );

      useChatStore.getState().createConversation('Error Test');
      await useChatStore.getState().sendMessage('Break it');

      expect(useChatStore.getState().error).toBe('Stream connection failed');
      expect(useChatStore.getState().isStreaming).toBe(false);
    });

    it('sendMessage 处理流式响应中的错误回调', async () => {
      vi.mocked(sendChatMessageStream).mockImplementation(
        async (_request, _onChunk, _onDone, onError, _signal) => {
          onError(new Error('Chunk processing error'));
        }
      );

      const convId = useChatStore.getState().createConversation('Error Chat');
      await useChatStore.getState().sendMessage('Test error');

      expect(useChatStore.getState().error).toBe('Chunk processing error');
      expect(useChatStore.getState().isStreaming).toBe(false);
    });

    it('sendMessage 当第一条消息时用消息内容前50个字符作为会话标题', async () => {
      vi.mocked(sendChatMessageStream).mockImplementation(
        async (_request, onChunk, onDone, _onError, _signal) => {
          onChunk('OK');
          onDone();
        }
      );

      const title = 'This is a very long message that should be truncated in the title';
      useChatStore.getState().createConversation();
      await useChatStore.getState().sendMessage(title);

      const conv = useChatStore.getState().conversations[0];
      expect(conv.title).toBe(title.slice(0, 50) + '...');
    });
  });

  describe('clearError - 清除错误', () => {
    it('清除当前的错误信息', () => {
      useChatStore.setState({ error: 'Chat error' });

      useChatStore.getState().clearError();

      expect(useChatStore.getState().error).toBeNull();
    });
  });
});
