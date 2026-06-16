"""Prompt 工程路由：模板管理、渲染、实验评估和 DSPy 优化。"""

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.dependencies import get_current_tenant, get_token_counter
from src.api.dependencies import TenantContext
from src.api.schemas.prompt import (
    RenderRequest,
    RenderResponse,
    TemplateCreate,
    TemplateResponse,
    ExperimentRequest,
)
from src.api.schemas.common import ErrorResponse, PaginatedResponse
from src.monitoring.logging_setup import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/prompts", tags=["Prompt 工程"])


@router.post(
    "/render",
    response_model=RenderResponse,
    responses={
        200: {"description": "Prompt 渲染成功"},
        404: {"model": ErrorResponse},
    },
)
async def render(
    request_body: RenderRequest,
    request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
    token_counter=Depends(get_token_counter),
):
    """使用给定变量渲染 Prompt 模板。

    按名称（及可选版本）获取模板，将所有 {{variable}} 占位符替换为实际值，
    返回渲染后的 Prompt 及其 Token 计数。
    """
    prompt_manager = getattr(request.app.state, "prompt_manager", None)
    if not prompt_manager:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                code="PROMPT_SERVICE_UNAVAILABLE",
                message="Prompt manager not initialized",
            ).model_dump(),
        )

    try:
        template = await prompt_manager.get_template(
            name=request_body.template_name,
            version=request_body.version,
            tenant_id=tenant.tenant_id,
        )
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                code="TEMPLATE_NOT_FOUND",
                message=f"Template '{request_body.template_name}' not found",
            ).model_dump(),
        )

    # Validate all required variables are provided
    missing_vars = set(template.variables) - set(request_body.variables.keys())
    if missing_vars:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                code="MISSING_VARIABLES",
                message=f"Missing required variables: {list(missing_vars)}",
                details={"missing_variables": list(missing_vars)},
            ).model_dump(),
        )

    # Render the template by replacing {{var}} placeholders
    rendered = template.content
    for var_name, var_value in request_body.variables.items():
        rendered = rendered.replace(f"{{{{{var_name}}}}}", str(var_value))

    # Check for any remaining unrendered variables
    import re
    remaining = re.findall(r'\{\{(\w+)\}\}', rendered)
    if remaining:
        logger.warning(
            "Template contains unrendered variables",
            template=request_body.template_name,
            remaining=remaining,
        )

    # Count tokens
    token_count = await token_counter.count_tokens(
        model="gpt-4o",  # Default model for counting
        text=rendered,
    )

    return RenderResponse(
        rendered=rendered,
        token_count=token_count,
        template_name=request_body.template_name,
        version=template.version,
        variable_count=len(template.variables),
    )


@router.get(
    "/templates",
    response_model=PaginatedResponse[TemplateResponse],
    responses={200: {"description": "Prompt 模板列表"}},
)
async def list_templates(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """列出当前租户的所有 Prompt 模板。

    支持按标签和文本搜索进行过滤。
    """
    prompt_manager = getattr(request.app.state, "prompt_manager", None)
    if not prompt_manager:
        return PaginatedResponse(items=[], total=0, page=page, page_size=page_size)

    templates = await prompt_manager.list_templates(
        tenant_id=tenant.tenant_id,
        tag=tag,
        search=search,
    )

    # Paginate
    total = len(templates)
    start = (page - 1) * page_size
    end = start + page_size
    items = templates[start:end]

    template_responses = [
        TemplateResponse(
            name=t.name,
            content=t.content,
            description=t.description,
            version=t.version,
            tags=t.tags,
            variables=t.variables,
            created_at=t.created_at.isoformat() if hasattr(t, 'created_at') and t.created_at else None,
            updated_at=t.updated_at.isoformat() if hasattr(t, 'updated_at') and t.updated_at else None,
            created_by=getattr(t, 'created_by', None),
        )
        for t in items
    ]

    return PaginatedResponse(
        items=template_responses,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/templates",
    response_model=TemplateResponse,
    status_code=201,
    responses={
        201: {"description": "模板创建成功"},
        409: {"model": ErrorResponse},
    },
)
async def create_template(
    request_body: TemplateCreate,
    request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """创建新的 Prompt 模板。

    模板内容使用 {{variable}} 语法作为占位符。
    """
    prompt_manager = getattr(request.app.state, "prompt_manager", None)
    if not prompt_manager:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                code="PROMPT_SERVICE_UNAVAILABLE",
                message="Prompt manager not initialized",
            ).model_dump(),
        )

    # Auto-detect variables if not provided
    import re
    variables = request_body.variables or re.findall(r'\{\{(\w+)\}\}', request_body.content)

    try:
        template = await prompt_manager.create_template(
            name=request_body.name,
            content=request_body.content,
            description=request_body.description,
            tags=request_body.tags,
            variables=variables,
            tenant_id=tenant.tenant_id,
            created_by=tenant.user_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(
                code="TEMPLATE_EXISTS",
                message=str(e),
            ).model_dump(),
        )

    return TemplateResponse(
        name=template.name,
        content=template.content,
        description=template.description,
        version=template.version,
        tags=template.tags,
        variables=template.variables,
        created_at=template.created_at.isoformat() if hasattr(template, 'created_at') and template.created_at else None,
        updated_at=template.updated_at.isoformat() if hasattr(template, 'updated_at') and template.updated_at else None,
        created_by=template.created_by,
    )


@router.get(
    "/templates/{name}/versions",
    response_model=list[dict],
    responses={
        200: {"description": "模板版本历史"},
        404: {"model": ErrorResponse},
    },
)
async def get_versions(
    name: str,
    request: Request,
    limit: int = 20,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """获取指定模板的版本历史。"""
    prompt_manager = getattr(request.app.state, "prompt_manager", None)
    if not prompt_manager:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                code="PROMPT_SERVICE_UNAVAILABLE",
                message="Prompt manager not initialized",
            ).model_dump(),
        )

    try:
        versions = await prompt_manager.get_versions(
            name=name,
            tenant_id=tenant.tenant_id,
            limit=limit,
        )
        return versions
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                code="TEMPLATE_NOT_FOUND",
                message=f"Template '{name}' not found",
            ).model_dump(),
        )


@router.post(
    "/templates/{name}/rollback",
    response_model=TemplateResponse,
    responses={
        200: {"description": "模板回滚成功"},
        404: {"model": ErrorResponse},
    },
)
async def rollback(
    name: str,
    request: Request,
    version: int,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """将模板回滚到之前的版本。"""
    prompt_manager = getattr(request.app.state, "prompt_manager", None)
    if not prompt_manager:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                code="PROMPT_SERVICE_UNAVAILABLE",
                message="Prompt manager not initialized",
            ).model_dump(),
        )

    try:
        template = await prompt_manager.rollback(
            name=name,
            version=version,
            tenant_id=tenant.tenant_id,
        )
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                code="TEMPLATE_NOT_FOUND",
                message=f"Template '{name}' or version {version} not found",
            ).model_dump(),
        )

    return TemplateResponse(
        name=template.name,
        content=template.content,
        description=template.description,
        version=template.version,
        tags=template.tags,
        variables=template.variables,
        created_at=template.created_at.isoformat() if hasattr(template, 'created_at') and template.created_at else None,
        updated_at=template.updated_at.isoformat() if hasattr(template, 'updated_at') and template.updated_at else None,
        created_by=getattr(template, 'created_by', None),
    )


@router.post(
    "/experiments",
    response_model=dict,
    status_code=201,
    responses={201: {"description": "实验创建成功"}},
)
async def create_experiment(
    request_body: ExperimentRequest,
    request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """创建 Prompt 评估实验。

    通过为相同的测试输入生成输出，并使用指定的评估器进行评估，
    比较多个模板版本的效果。
    """
    experiment_manager = getattr(request.app.state, "experiment_manager", None)
    if not experiment_manager:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                code="EXPERIMENT_SERVICE_UNAVAILABLE",
                message="Experiment manager not initialized",
            ).model_dump(),
        )

    experiment_id = await experiment_manager.create(
        name=request_body.name,
        template_names=request_body.template_names,
        test_inputs=request_body.test_inputs,
        evaluator=request_body.evaluator,
        model=request_body.model,
        tenant_id=tenant.tenant_id,
    )

    return {"experiment_id": experiment_id, "status": "created"}


@router.get(
    "/experiments/{experiment_id}/results",
    response_model=dict,
    responses={
        200: {"description": "实验结果"},
        404: {"model": ErrorResponse},
    },
)
async def get_experiment_results(
    experiment_id: str,
    request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """获取 Prompt 实验结果。"""
    experiment_manager = getattr(request.app.state, "experiment_manager", None)
    if not experiment_manager:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                code="EXPERIMENT_SERVICE_UNAVAILABLE",
                message="Experiment manager not initialized",
            ).model_dump(),
        )

    try:
        results = await experiment_manager.get_results(
            experiment_id=experiment_id,
            tenant_id=tenant.tenant_id,
        )
        return results
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                code="EXPERIMENT_NOT_FOUND",
                message=f"Experiment {experiment_id} not found",
            ).model_dump(),
        )


@router.post(
    "/dspy/optimize",
    response_model=dict,
    responses={200: {"description": "DSPy 优化已启动"}},
)
async def optimize_with_dspy(
    request: Request,
    template_name: str,
    metric: str = "accuracy",
    max_iterations: int = 20,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """使用 DSPy 优化 Prompt 模板。

    利用 DSPy 的自动 Prompt 优化功能，基于指定的指标和黄金数据集
    改进模板。
    """
    dspy_optimizer = getattr(request.app.state, "dspy_optimizer", None)
    if not dspy_optimizer:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                code="DSPY_SERVICE_UNAVAILABLE",
                message="DSPy optimizer not initialized",
            ).model_dump(),
        )

    try:
        result = await dspy_optimizer.optimize(
            template_name=template_name,
            metric=metric,
            max_iterations=max_iterations,
            tenant_id=tenant.tenant_id,
        )
        return result
    except Exception as e:
        logger.error("DSPy optimization failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                code="DSPY_OPTIMIZATION_FAILED",
                message=f"DSPy optimization failed: {str(e)}",
            ).model_dump(),
        )
