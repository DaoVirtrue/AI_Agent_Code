## 安全模块 (Security)

### 模块概述

安全模块为 LLM 平台提供多层安全防护体系，覆盖 LLM 应用面临的独特安全威胁。它包括多层级提示词注入防御（覆盖直接注入、间接注入、越狱攻击）、基于角色的访问控制（RBAC）和基于属性的访问控制（ABAC）、AI 内容安全过滤（检测暴力/色情/仇恨/自残等有害内容），以及全面的个人身份信息（PII）检测和脱敏（支持身份证、手机号、邮箱、银行卡等敏感数据）。所有安全机制在请求处理链路的不同阶段协同工作。

### 关键文件

- `injection_defense.py` - `InjectionDefense`，四层注入防御：正则规则->分隔符隔离->角色边界定义->LLM 二次检测
- `rbac_manager.py` - `RBACManager`，角色-权限管理，支持角色继承和租户隔离
- `abac_manager.py` - `ABACManager`，属性访问控制，基于用户/资源/环境属性动态决策
- `content_safety.py` - `ContentSafetyFilter`，多类别有害内容检测，支持自定义敏感词库
- `pii_detector.py` - `PIIDetector`，基于正则+NLP 的 PII 检测，支持脱敏和审计告警

### 模块连接

`injection_defense` 在 `ai_gateway` 入口和 `prompt_engineering` 渲染后两次检查输入。`rbac_manager` 和 `abac_manager` 通过 `shared/security.py` 的 FastAPI 依赖注入到 `api` 层保护所有路由。`content_safety` 在输入和输出两端检查。`pii_detector` 同时在 `streaming` 的流式扫描器和后端存储写入前调用。

### 关键技术

多层正则+LLM 注入防御、RBAC/ABAC 双模型访问控制、敏感词库 + 分类器联合过滤、正则+NER 双重 PII 检测、SHA-256 密钥哈希、ContextVar 请求级租户上下文。
