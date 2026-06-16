## 流式架构 (Streaming)

### 模块概述

流式架构模块负责 LLM 回答的实时流式传输和处理。它提供 Server-Sent Events (SSE) 格式化、Token 级流式引擎、背压控制（防止客户端消费过慢导致服务器内存溢出）、JSON 流式缓冲（处理不完整 JSON 的增量解析）、首 Token 延迟（TTFT）和 Token 间延迟（ITL）的实时追踪、流式中断处理（用户取消/超时/安全检测触发）、基于增量正则的流式 PII 扫描，以及集成了流式 RAG 检索的服务层。

### 关键文件

- `sse_formatter.py` - `SSEFormatter`，将平台内部事件格式化为标准 SSE 格式（`data:` 行 + `event:` 类型）
- `token_stream_engine.py` - `TokenStreamEngine`，管理 Token 流的缓冲、分块和异步迭代
- `backpressure.py` - `BackpressureController`，监控下游消费速率，触发限流或丢弃策略
- `json_buffer.py` - `JSONStreamBuffer`，增量解析不完整的流式 JSON（如工具调用参数）
- `latency_tracker.py` - `LatencyTracker`，统计 TTFT（首 Token 延迟）和 ITL（Token 间延迟）
- `stream_interrupter.py` - `StreamInterruptionHandler`，处理用户取消、超时截断、安全检测中断三种场景
- `stream_scanner.py` - `IncrementalRegexScanner` 和 `StreamingSecurityMonitor`，在流式传输过程中实时扫描 PII 和敏感内容
- `streaming_rag_service.py` - `StreamingRAGService`，集成流式 RAG 检索 + 流式 LLM 生成的一体化服务

### 模块连接

`streaming` 层位于 `api` 路由和 `ai_gateway` 之间：路由接收请求后，由 `StreamingRAGService` 或 `TokenStreamEngine` 管理流式响应，通过 `SSEFormatter` 输出到客户端。`stream_scanner` 调用 `security.pii_detector` 进行流式内容检查。`latency_tracker` 向 `monitoring` 上报 TTFT/ITL 指标。

### 关键技术

Server-Sent Events (SSE) 协议、异步生成器 (AsyncGenerator)、背压控制（生产者-消费者速率匹配）、增量正则匹配流式扫描、JSON 增量解析缓冲区、TTFT/ITL 实时统计。
