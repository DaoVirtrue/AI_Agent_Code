## 对话管理 (Conversation)

### 模块概述

对话管理模块为多轮对话 AI 应用提供完整的上下文理解和状态管理能力。它包含指代消解（解决"它"、"那个"等指代模糊）、上下文拼接（将多轮对话组装为 LLM 可消费的消息序列）、实体追踪（跨轮次跟踪人名/地名/产品等实体）、对话状态机（管理多步骤任务的状态转移）、槽位填充（收集结构化信息如日期/人数）、意图澄清引擎、人设管理（控制 AI 回复风格和角色），以及语气适配（根据对话历史动态调整回复语调）。

### 关键文件

- `coreference.py` - `CoreferenceResolver`，利用 LLM 解析指代关系，生成完全消解的查询
- `context_stitcher.py` - `ContextStitcher`，将多轮对话拼接为 `ConversationHistory` 消息序列
- `entity_tracker.py` - `EntityTracker`，跨轮次追踪和更新实体信息
- `fsm.py` - `DialogFSM`，对话状态机，定义状态转移规则（如收集信息->确认->提交）
- `slot_filling.py` - `SlotFiller`，定义和填充对话槽位，支持验证和追问
- `clarification.py` - `ClarificationEngine`，当用户意图不明确时主动提问澄清
- `persona.py` - `PersonaManager`，管理 AI 角色设定，控制语气、知识范围和行为边界
- `tone_adapter.py` - `ToneAdapter`，分析对话情绪并适配回复语气

### 模块连接

`ContextStitcher` 直接依赖 `context_management.ContextWindowManager` 限制上下文大小。`CoreferenceResolver` 和 `ClarificationEngine` 通过 `ai_gateway` 调用 LLM。对话状态和槽位数据存储在 `shared/redis` 中。各组件被 `api` 层的对话路由调用。

### 关键技术

LLM 指代消解、有限状态机（FSM）对话管理、槽位填充模式、实体链接追踪、情绪感知语气适配、Redis 会话状态存储。
