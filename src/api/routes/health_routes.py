"""健康检查路由：存活检测、就绪检测和完整健康状态。"""

from fastapi import APIRouter, Request

from src.api.schemas.common import HealthResponse
from src.observability.health import HealthChecker
from src.observability.logging_setup import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["健康检查"])

_health_checker: HealthChecker | None = None


def _get_health_checker(request: Request) -> HealthChecker:
    """Get or create the health checker instance."""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker(
            redis=request.app.state.redis,
            db_session_factory=request.app.state.db_session_factory,
            model_registry=getattr(request.app.state, "provider_registry", None),
        )
    return _health_checker


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={200: {"description": "完整健康检查"}, 503: {"description": "服务不健康"}},
)
async def health(
    request: Request,
):
    """完整健康检查，返回所有依赖服务的状态。

    返回整体健康状态和各项检查结果：
    - 数据库连接
    - Redis 连接
    - Milvus/向量存储
    - LLM provider API
    - MCP 服务器连接
    """
    checker = _get_health_checker(request)
    full_check = await checker.full_check()

    overall_status = "healthy"
    if not all(full_check.values()):
        # If critical dependencies fail, mark as unhealthy
        critical_checks = ["database", "redis"]
        if any(not full_check.get(c, False) for c in critical_checks):
            overall_status = "unhealthy"
        else:
            overall_status = "degraded"

    return HealthResponse(
        status=overall_status,
        version="1.0.0",
        checks={k: bool(v) for k, v in full_check.items()},
    )


@router.get(
    "/ready",
    response_model=dict,
    responses={200: {"description": "服务已就绪"}, 503: {"description": "服务未就绪"}},
)
async def ready(
    request: Request,
):
    """Kubernetes 就绪探测。

    通过验证所有关键依赖是否可用，检查服务是否已准备好接受流量。
    未就绪时返回 503。
    """
    from fastapi.responses import JSONResponse

    checker = _get_health_checker(request)

    db_ok = await checker.check_db()
    redis_ok = await checker.check_redis()

    ready_status = db_ok and redis_ok

    if not ready_status:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "checks": {
                    "database": db_ok,
                    "redis": redis_ok,
                },
            },
        )

    return {
        "status": "ready",
        "checks": {
            "database": db_ok,
            "redis": redis_ok,
        },
    }


@router.get(
    "/live",
    response_model=dict,
    responses={200: {"description": "服务存活"}},
)
async def live():
    """Kubernetes 存活探测。

    最小化检查，仅验证应用进程是否正在运行。
    只要服务器能响应即返回 200。
    """
    return {
        "status": "alive",
        "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
    }


@router.get(
    "/metrics",
    responses={200: {"description": "Prometheus 指标端点"}},
)
async def metrics():
    """Prometheus 指标端点。

    以标准格式暴露所有已注册的 Prometheus 指标。
    """
    from fastapi.responses import Response
    from src.observability.metrics import get_metrics

    metrics_text = get_metrics()
    return Response(content=metrics_text, media_type="text/plain; charset=utf-8")
