"""系统管理路由：租户管理、审计日志和使用量报告。"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from src.api.dependencies import get_current_tenant, get_db, require_scope
from src.api.dependencies import TenantContext
from src.api.schemas.common import ErrorResponse, PaginatedResponse
from src.monitoring.audit import AuditLogger
from src.monitoring.logging_setup import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/admin", tags=["系统管理"])


# --- Tenant Management ---

@router.get(
    "/tenants",
    response_model=PaginatedResponse[dict],
    responses={200: {"description": "所有租户列表"}},
)
async def list_tenants(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_scope("admin:read")),
):
    """列出所有租户。需要 admin:read 权限。"""
    conditions = ["1=1"]
    params: dict = {"limit": page_size, "offset": (page - 1) * page_size}

    if search:
        conditions.append("(t.name ILIKE :search OR t.id ILIKE :search)")
        params["search"] = f"%{search}%"

    if is_active is not None:
        conditions.append("t.is_active = :is_active")
        params["is_active"] = is_active

    where_clause = " AND ".join(conditions)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) as total FROM tenants t WHERE {where_clause}"),
        params,
    )
    total = count_result.scalar()

    result = await db.execute(
        text(f"""
            SELECT t.id, t.name, t.email, t.is_active, t.max_rpm, t.max_tokens_monthly,
                   t.created_at, t.updated_at,
                   (SELECT COUNT(*) FROM api_keys WHERE tenant_id = t.id) as api_key_count
            FROM tenants t
            WHERE {where_clause}
            ORDER BY t.created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )

    tenants = []
    for row in result:
        tenants.append({
            "id": row.id,
            "name": row.name,
            "email": row.email,
            "is_active": row.is_active,
            "max_rpm": row.max_rpm,
            "max_tokens_monthly": row.max_tokens_monthly,
            "api_key_count": row.api_key_count,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        })

    return PaginatedResponse(
        items=tenants,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/tenants",
    response_model=dict,
    status_code=201,
    responses={201: {"description": "租户创建成功"}},
)
async def create_tenant(
    request: Request,
    name: str,
    email: str,
    max_rpm: int = 100,
    max_tokens_monthly: int = 1000000,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_scope("admin:write")),
):
    """创建新租户。需要 admin:write 权限。"""
    import uuid

    tenant_id = f"tenant-{uuid.uuid4().hex[:12]}"

    try:
        await db.execute(
            text("""
                INSERT INTO tenants (id, name, email, is_active, max_rpm, max_tokens_monthly)
                VALUES (:id, :name, :email, true, :max_rpm, :max_tokens_monthly)
            """),
            {
                "id": tenant_id,
                "name": name,
                "email": email,
                "max_rpm": max_rpm,
                "max_tokens_monthly": max_tokens_monthly,
            },
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error("Failed to create tenant", error=str(e))
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(
                code="TENANT_CREATION_FAILED",
                message=f"Failed to create tenant: {str(e)}",
            ).model_dump(),
        )

    logger.info("Tenant created", tenant_id=tenant_id, name=name)

    return {
        "id": tenant_id,
        "name": name,
        "email": email,
        "max_rpm": max_rpm,
        "max_tokens_monthly": max_tokens_monthly,
    }


@router.put(
    "/tenants/{tenant_id}",
    response_model=dict,
    responses={200: {"description": "租户更新成功"}},
)
async def update_tenant(
    tenant_id: str,
    request: Request,
    name: Optional[str] = None,
    email: Optional[str] = None,
    is_active: Optional[bool] = None,
    max_rpm: Optional[int] = None,
    max_tokens_monthly: Optional[int] = None,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_scope("admin:write")),
):
    """更新租户信息。需要 admin:write 权限。"""
    updates = []
    params = {"tenant_id": tenant_id}

    if name is not None:
        updates.append("name = :name")
        params["name"] = name
    if email is not None:
        updates.append("email = :email")
        params["email"] = email
    if is_active is not None:
        updates.append("is_active = :is_active")
        params["is_active"] = is_active
    if max_rpm is not None:
        updates.append("max_rpm = :max_rpm")
        params["max_rpm"] = max_rpm
    if max_tokens_monthly is not None:
        updates.append("max_tokens_monthly = :max_tokens_monthly")
        params["max_tokens_monthly"] = max_tokens_monthly

    if not updates:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                code="NO_UPDATES",
                message="No fields to update provided",
            ).model_dump(),
        )

    updates.append("updated_at = NOW()")
    set_clause = ", ".join(updates)

    result = await db.execute(
        text(f"UPDATE tenants SET {set_clause} WHERE id = :tenant_id"),
        params,
    )
    await db.commit()

    if result.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                code="TENANT_NOT_FOUND",
                message=f"Tenant {tenant_id} not found",
            ).model_dump(),
        )

    return {"status": "updated", "tenant_id": tenant_id}


# --- Audit Logs ---

@router.get(
    "/audit-logs",
    response_model=PaginatedResponse[dict],
    responses={200: {"description": "审计日志条目"}},
)
async def get_audit_logs(
    request: Request,
    page: int = 1,
    page_size: int = 50,
    tenant_id_filter: Optional[str] = None,
    event_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    tenant: TenantContext = Depends(get_current_tenant),
    _: None = Depends(require_scope("admin:read")),
):
    """查询审计日志。需要 admin:read 权限。

    支持按租户、事件类型和日期范围进行过滤。
    """
    audit_logger = AuditLogger()

    try:
        from_date = datetime.fromisoformat(date_from) if date_from else datetime.utcnow() - timedelta(days=7)
        to_date = datetime.fromisoformat(date_to) if date_to else datetime.utcnow()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                code="INVALID_DATE_FORMAT",
                message="date_from and date_to must be ISO format (YYYY-MM-DD)",
            ).model_dump(),
        )

    logs = await audit_logger.query(
        tenant_id=tenant_id_filter,
        date_from=from_date,
        date_to=to_date,
        event_type=event_type,
        limit=page_size * page,
    )

    total = len(logs)
    start = (page - 1) * page_size
    end = start + page_size

    return PaginatedResponse(
        items=logs[start:end],
        total=total,
        page=page,
        page_size=page_size,
    )


# --- Usage Reports ---

@router.get(
    "/usage-report",
    response_model=dict,
    responses={200: {"description": "按租户/Provider/模型的使用量报告"}},
)
async def get_usage_report(
    request: Request,
    period: str = "daily",
    date: Optional[str] = None,
    tenant_id_filter: Optional[str] = None,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_scope("admin:read")),
):
    """获取使用量报告，汇总 Token 消耗和费用。

    支持按日、周、月和自定义周期聚合。
    需要 admin:read 权限。
    """
    valid_periods = {"daily", "weekly", "monthly", "custom"}
    if period not in valid_periods:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                code="INVALID_PERIOD",
                message=f"Period must be one of: {', '.join(sorted(valid_periods))}",
            ).model_dump(),
        )

    # Determine date range
    report_date = datetime.fromisoformat(date) if date else datetime.utcnow()
    if period == "daily":
        date_from = report_date.replace(hour=0, minute=0, second=0, microsecond=0)
        date_to = date_from + timedelta(days=1)
    elif period == "weekly":
        date_from = report_date - timedelta(days=report_date.weekday())
        date_from = date_from.replace(hour=0, minute=0, second=0, microsecond=0)
        date_to = date_from + timedelta(days=7)
    elif period == "monthly":
        date_from = report_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if report_date.month == 12:
            date_to = report_date.replace(year=report_date.year + 1, month=1, day=1)
        else:
            date_to = report_date.replace(month=report_date.month + 1, day=1)
    else:
        date_from = report_date.replace(hour=0, minute=0, second=0, microsecond=0)
        date_to = date_from + timedelta(days=1)

    conditions = [
        "created_at >= :date_from",
        "created_at < :date_to",
    ]
    params = {"date_from": date_from, "date_to": date_to}

    if tenant_id_filter:
        conditions.append("tenant_id = :tenant_id_filter")
        params["tenant_id_filter"] = tenant_id_filter

    where_clause = " AND ".join(conditions)

    # Aggregate usage
    result = await db.execute(
        text(f"""
            SELECT
                tenant_id,
                provider,
                model,
                SUM(input_tokens) as total_input_tokens,
                SUM(output_tokens) as total_output_tokens,
                SUM(total_tokens) as total_tokens,
                SUM(cost_usd) as total_cost_usd,
                COUNT(*) as request_count
            FROM usage_records
            WHERE {where_clause}
            GROUP BY tenant_id, provider, model
            ORDER BY total_cost_usd DESC
        """),
        params,
    )

    breakdown = []
    total_tokens_sum = 0
    total_cost_sum = 0.0
    total_requests = 0

    for row in result:
        entry = {
            "tenant_id": row.tenant_id,
            "provider": row.provider,
            "model": row.model,
            "input_tokens": int(row.total_input_tokens),
            "output_tokens": int(row.total_output_tokens),
            "total_tokens": int(row.total_tokens),
            "cost_usd": float(row.total_cost_usd),
            "request_count": int(row.request_count),
        }
        breakdown.append(entry)
        total_tokens_sum += int(row.total_tokens)
        total_cost_sum += float(row.total_cost_usd)
        total_requests += int(row.request_count)

    return {
        "period": period,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "summary": {
            "total_tokens": total_tokens_sum,
            "total_cost_usd": round(total_cost_sum, 6),
            "total_requests": total_requests,
            "unique_tenants": len(set(r["tenant_id"] for r in breakdown)),
        },
        "breakdown": breakdown,
    }


# --- API Key Management ---

@router.post(
    "/tenants/{tenant_id}/api-keys",
    response_model=dict,
    status_code=201,
    responses={201: {"description": "API Key 生成成功"}},
)
async def generate_api_key(
    tenant_id: str,
    request: Request,
    user_id: str = "default",
    role: str = "developer",
    scopes: str = "read,write",
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_scope("admin:write")),
):
    """为租户生成新的 API Key。需要 admin:write 权限。"""
    import secrets
    import hashlib

    api_key = f"llm-{secrets.token_hex(24)}"
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    await db.execute(
        text("""
            INSERT INTO api_keys (tenant_id, user_id, role, scopes, key_hash, is_active)
            VALUES (:tenant_id, :user_id, :role, :scopes, :key_hash, true)
        """),
        {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "role": role,
            "scopes": scopes,
            "key_hash": key_hash,
        },
    )
    await db.commit()

    logger.info("API key generated", tenant_id=tenant_id, user_id=user_id)

    return {
        "api_key": api_key,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "role": role,
        "scopes": scopes.split(","),
        "note": "Store this key securely. It will not be shown again.",
    }


@router.get(
    "/system/stats",
    response_model=dict,
    responses={200: {"description": "系统全局统计"}},
)
async def system_stats(
    request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
    _: None = Depends(require_scope("admin:read")),
):
    """获取系统全局统计数据。需要 admin:read 权限。"""
    redis = request.app.state.redis
    mcp_pool = getattr(request.app.state, "mcp_pool", None)

    return {
        "version": "1.0.0",
        "uptime_seconds": getattr(request.app.state, "start_time", 0),
        "active_tenants": await redis.scard("active_tenants"),
        "mcp_servers_connected": len(await mcp_pool.get_servers()) if mcp_pool else 0,
        "cache_stats": {
            "redis_keys": await redis.dbsize(),
            "memory_used": await redis.info("memory"),
        },
    }
