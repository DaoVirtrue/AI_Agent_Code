## RAG 系统 (RAG System)

### 模块概述

RAG 系统实现完整的检索增强生成（Retrieval-Augmented Generation）pipeline，支持从多格式文档（PDF、DOCX、HTML、Markdown、CSV、JSON）的摄入到智能检索生成的全流程。涵盖 OCR、表格提取、多种分块策略、嵌入向量化、多向量数据库支持（Milvus、Chroma、FAISS）、稠密+稀疏混合检索、查询预处理（重写/扩展/分解/HyDE/路由）、多级缓存、RAGAS 质量评估、高级 RAG 策略（CRAG、Self-RAG、GraphRAG、AgenticRAG）以及事实验证和幻觉检测等质量保障机制。

### 关键文件

- `pipeline.py` - `RAGPipeline`，基于 LangGraph 的完整 RAG 管线编排
- `ingestion/` - 文档解析器 (`DocumentParser`)、OCR 引擎、表格提取、文本清洗
- `chunking/` - 多种分块器：固定大小、递归、语义、Markdown 感知
- `embedding/` - 嵌入模型注册表与批量嵌入 `BatchEmbedder`
- `indexing/` - 向量库适配：`MilvusStore`、`ChromaStore`、`FAISSStore`
- `retrieval/` - 稠密检索、稀疏检索、混合检索 + RRF 融合、Cross-Encoder 重排序
- `query_processing/` - 查询重写、扩展、分解、HyDE 生成、查询路由
- `caching/` - 四级缓存：精确、语义、摘要、预计算 + 缓存编排器
- `evaluation/` - RAGAS 评估适配器，计算 Faithfulness、Relevancy 等指标
- `advanced/` - CRAG、Self-RAG、Adaptive RAG、GraphRAG、AgenticRAG 策略
- `quality/` - 事实验证、源归属、幻觉检测、答案投票
- `incremental.py` - 增量索引，仅更新变化文档

### 模块连接

RAG pipeline 通过 `api/rag_routes` 暴露搜索和问答接口。与 `embedding` 和 `ai_gateway`（LLM 调用）紧密协作。`quality` 模块对接 `evaluation` 上报评估结果。缓存层依赖 `shared/redis`。

### 关键技术

LangGraph 有向图编排、Milvus/Chroma/FAISS 向量库、稠密+稀疏+RRF 混合检索、Cross-Encoder 重排序、RAGAS 评估框架、HyDE 假设文档嵌入、GraphRAG 图谱增强、语义缓存。
