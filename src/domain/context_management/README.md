## 上下文管理 (Context Management)

### 模块概述

上下文管理模块解决 LLM 有限上下文窗口与长对话/大文档之间的核心矛盾。它提供多种上下文窗口管理策略，包括滑动窗口截断、对话历史摘要、五区域上下文分配、Lost-in-the-Middle 重排序、Prompt 缓存（利用 Anthropic/OpenAI 缓存机制降低延迟和成本），以及基于 LLMLingua 的提示词压缩，确保关键信息不被截断或淹没。

### 关键文件

- `window_manager.py` - `ContextWindowManager`，统一的上下文窗口调度入口
- `sliding_window.py` - `SlidingWindowTruncator`，先进先出的滑动窗口截断
- `summarizer.py` - `HistorySummarizer`，利用 LLM 将历史对话压缩为精炼摘要
- `hybrid_strategy.py` - `HybridStrategy`，组合摘要与截断的混合策略
- `five_zone_window.py` - `FiveZoneWindow`，将上下文窗口按重要度划分为五区域（系统/安全/核心/参考/缓冲区）
- `lost_in_middle.py` - `LostInMiddleReorder`，解决 LLM 对中间位置信息注意力衰减的问题
- `prompt_cache/` - 针对 Anthropic 和 OpenAI 的 Prompt 缓存策略实现
- `compressors/` - 基于 LLMLingua 的提示词压缩器

### 模块连接

`ContextWindowManager` 是 `conversation.ContextStitcher` 和 `rag_system` pipeline 的依赖，在构造请求前对上下文进行裁剪和重组。`prompt_cache` 模块被 `ai_gateway` 调用标记可缓存内容以降低成本和延迟。

### 关键技术

滑动窗口算法、LLM 摘要生成、Five-Zone 优先级分配、Lost-in-the-Middle 注意力重排序、Anthropic/OpenAI Prompt Caching API、LLMLingua 压缩。
