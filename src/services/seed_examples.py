"""启动时 seed 示例数据 —— 业务专家 / 智能体专家 / MCP / RAG / 技能 的例子。

让面试演示「开箱即用」：登录后每个页面都有真实可选的示例，而非空列表。
所有 seed 函数都是幂等的（已存在则跳过），可安全重复执行。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

DEFAULT_TENANT = "default"


async def _resolve_tenant_id(app) -> str:
    """解析 demo 租户的真实 id（数据库 UUID），找不到时回退 'default'。

    认证依赖 get_current_tenant 注入的是数据库 tenant.id（UUID 字符串），
    而 seed 若用硬编码 'default' 就会种到错误租户、前端看不到示例。
    """
    try:
        factory = getattr(app.state, "db_session_factory", None)
        if factory is not None:
            from sqlalchemy import select
            from src.repositories.models.tenant import Tenant

            async with factory() as session:
                result = await session.execute(
                    select(Tenant).where(Tenant.slug == "demo").limit(1)
                )
                tenant = result.scalar_one_or_none()
                if tenant is not None:
                    return str(tenant.id)
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("Resolve demo tenant id failed: %s", exc)
    return DEFAULT_TENANT


async def seed_examples(app) -> None:
    """Seed 全部示例数据（技能 / 专家 / RAG 文档 / MCP 服务器）。"""
    tenant_id = await _resolve_tenant_id(app)
    await _seed_skills(app)
    await _seed_experts(app, tenant_id)
    await _seed_rag_documents(app, tenant_id)
    await _seed_mcp_servers(app)
    logger.info("Example data seeded (tenant=%s)", tenant_id)


# ---------------------------------------------------------------------------
# 技能
# ---------------------------------------------------------------------------

_SKILLS = [
    {
        "name": "代码审查",
        "description": "审查代码的质量、安全性与性能，输出可执行建议",
        "instructions": (
            "你是资深代码审查专家。请从以下维度审查代码：\n"
            "1. 正确性：是否存在逻辑错误、边界条件遗漏\n"
            "2. 安全性：注入、越权、敏感信息泄露\n"
            "3. 性能：冗余计算、N+1 查询、内存泄漏\n"
            "4. 可维护性：命名、重复、复杂度\n"
            "输出格式：按严重程度分级（阻断/警告/建议），每条附定位与改法。"
        ),
        "tools": [],
    },
    {
        "name": "周报生成",
        "description": "根据工作要点自动生成结构化周报",
        "instructions": (
            "你是周报助手。根据用户提供的本周工作要点，生成结构化周报：\n"
            "1. 本周完成\n2. 进行中\n3. 问题与风险\n4. 下周计划\n"
            "语言简洁、突出结果与数据，避免流水账。"
        ),
        "tools": [],
    },
    {
        "name": "数据分析",
        "description": "分析数据并给出洞察与可视化建议",
        "instructions": (
            "你是数据分析师。对用户提供的数据进行探索性分析：\n"
            "1. 数据概览与质量检查\n2. 关键指标与趋势\n3. 异常与相关性\n"
            "4. 可行动的洞察与建议\n优先用计算器/数据库查询工具获取或校验数据。"
        ),
        "tools": ["calculator", "database_query"],
    },
    {
        "name": "文档翻译",
        "description": "中英互译，保持专业术语一致",
        "instructions": (
            "你是专业翻译。将用户内容在中英之间互译，要求：\n"
            "1. 保留专业术语的一致性\n2. 语气贴合原文语境\n"
            "3. 对专有名词/缩写给出说明\n直接输出译文，附少量必要的译注。"
        ),
        "tools": [],
    },
]


async def _seed_skills(app) -> None:
    from src.services.skill_store import SkillDefinition

    store = app.state.skill_store
    created = 0
    for s in _SKILLS:
        if store.get(s["name"]) is None:
            store.create(SkillDefinition(
                name=s["name"],
                description=s["description"],
                instructions=s["instructions"],
                tools=s["tools"],
                author="system",
                version="1.0.0",
            ))
            created += 1
    if created:
        logger.info("Seeded %d example skills", created)


# ---------------------------------------------------------------------------
# 业务专家 / 智能体专家
# ---------------------------------------------------------------------------

_EXPERTS = [
    {
        "name": "法务专家",
        "role": "资深法律顾问，擅长合同审核、合规审查与风险提示",
        "system_prompt": "回答务必严谨，引用条款时说明依据，无法确定时明确告知不确定性。",
        "skills": ["document.generate"],
        "knowledge_bases": ["公司制度"],
        "description": "合同审核与合规咨询",
    },
    {
        "name": "数据分析师",
        "role": "数据科学家，擅长探索性分析与指标解读",
        "system_prompt": "先理解口径，再给结论；结论必须可复现，区分事实与推断。",
        "skills": ["calculator", "database_query"],
        "knowledge_bases": ["产品FAQ"],
        "description": "数据洞察与指标分析",
    },
    {
        "name": "技术写作助手",
        "role": "技术文档撰写专家，擅长把复杂技术讲清楚",
        "system_prompt": "面向读者写作，给出结构清晰的文档草稿，术语首次出现时解释。",
        "skills": ["document.generate"],
        "knowledge_bases": [],
        "description": "技术文档与方案撰写",
    },
]


async def _seed_experts(app, tenant_id: str) -> None:
    from src.agents.expert import ExpertConfig

    registry = app.state.expert_registry
    created = 0
    for e in _EXPERTS:
        if registry.get(e["name"], tenant_id=tenant_id) is None:
            registry.register(ExpertConfig(
                name=e["name"],
                role=e["role"],
                system_prompt=e["system_prompt"],
                skills=e["skills"],
                knowledge_bases=e["knowledge_bases"],
                description=e["description"],
            ), tenant_id=tenant_id)
            created += 1
    if created:
        logger.info("Seeded %d example experts", created)


# ---------------------------------------------------------------------------
# RAG 知识库文档
# ---------------------------------------------------------------------------

_RAG_DOCS = [
    {
        "knowledge_base": "公司制度",
        "filename": "员工报销制度.md",
        "content": (
            "# 员工报销制度\n\n"
            "## 报销范围\n公司为员工因公产生的交通、住宿、餐饮与办公用品费用提供报销。\n\n"
            "## 报销流程\n1. 员工在费用发生后 30 天内提交报销单，附发票原件。\n"
            "2. 直属主管在 3 个工作日内审批。\n3. 财务在 5 个工作日内复核并打款。\n\n"
            "## 报销额度\n- 市内交通：实报实销，上限 200 元/天。\n"
            "- 住宿：一线城市上限 600 元/晚，其他 400 元/晚。\n"
            "- 餐饮：上限 100 元/天，宴请需提前申请。\n\n"
            "## 注意事项\n发票抬头必须为公司全称，缺失或过期发票不予报销。"
        ),
    },
    {
        "knowledge_base": "公司制度",
        "filename": "考勤管理制度.md",
        "content": (
            "# 考勤管理制度\n\n"
            "## 工作时间\n标准工作时间为周一至周五 9:00-18:00，午休 12:00-13:30。\n\n"
            "## 打卡\n员工需在上下班时各打卡一次，漏卡需在 3 个工作日内申请补卡。\n\n"
            "## 请假\n- 事假需提前 1 天申请，由主管审批。\n"
            "- 病假需提供医院证明，3 天以上由 HR 复核。\n- 年假需提前 3 天申请。\n\n"
            "## 迟到早退\n月度累计迟到 3 次以内口头提醒，超过 5 次计入绩效考核。"
        ),
    },
    {
        "knowledge_base": "产品FAQ",
        "filename": "产品常见问题.md",
        "content": (
            "# 产品常见问题 FAQ\n\n"
            "## 数据是否安全？\n数据在传输与存储中均加密，支持私有化部署，敏感数据不出内网。\n\n"
            "## 支持哪些模型？\n平台接入 DeepSeek、GPT、Claude、Qwen 等主流模型，可统一网关切换。\n\n"
            "## RAG 是什么？\nRAG（检索增强生成）先检索相关文档片段，再让模型基于片段生成回答，降低幻觉。\n\n"
            "## 如何接入 MCP？\n通过 MCP（Model Context Protocol）接入外部工具，如文件系统、数据库、网络搜索。\n\n"
            "## 是否支持多租户？\n支持租户隔离、独立密钥、配额与审计日志，满足企业级权限管理。"
        ),
    },
]


async def _seed_rag_documents(app, tenant_id: str) -> None:
    pipeline = getattr(app.state, "rag_pipeline", None)
    if pipeline is None:
        logger.warning("RAG pipeline not available, skip document seed")
        return

    import uuid

    existing = {d.get("filename") for d in (await pipeline.list_documents(tenant_id=tenant_id)).get("items", [])}
    seeded = 0
    for doc in _RAG_DOCS:
        if doc["filename"] in existing:
            continue
        await pipeline.index_document(
            document_id=f"seed-{uuid.uuid4().hex[:8]}",
            filename=doc["filename"],
            content=doc["content"].encode("utf-8"),
            content_type="text/markdown",
            metadata={"knowledge_base": doc["knowledge_base"], "source": "示例"},
            tenant_id=tenant_id,
        )
        seeded += 1
    if seeded:
        logger.info("Seeded %d example RAG documents", seeded)


# ---------------------------------------------------------------------------
# MCP 服务器（示例）
# ---------------------------------------------------------------------------

_MCP_SERVERS = [
    {
        "name": "文件系统",
        "url": "stdio://filesystem",
        "transport": "stdio",
        "description": "在沙箱目录内读写文件、列目录、执行代码",
        "tools": ["file_operations", "code_executor"],
    },
    {
        "name": "网络工具",
        "url": "sse://web",
        "transport": "sse",
        "description": "网络搜索与网页抓取",
        "tools": ["web_search", "web_fetch"],
    },
    {
        "name": "llm-platform",
        "url": "builtin://llm-platform",
        "transport": "builtin",
        "description": "平台内置：命令行 / 文档生成 / 图片 OCR / 计算 / 数据库查询",
        "tools": ["cli.execute", "document.generate", "document.ocr", "calculator", "database_query"],
    },
]


async def _seed_mcp_servers(app) -> None:
    pool = getattr(app.state, "mcp_pool", None)
    if pool is None:
        logger.warning("MCP pool not available, skip MCP seed")
        return

    existing = {s["name"] for s in await pool.get_servers(DEFAULT_TENANT)}
    for srv in _MCP_SERVERS:
        if srv["name"] in existing:
            continue
        pool.register_server(
            name=srv["name"],
            url=srv["url"],
            transport=srv["transport"],
            description=srv["description"],
            tools=srv["tools"],
            status="connected",
        )
    logger.info("Seeded example MCP servers")
