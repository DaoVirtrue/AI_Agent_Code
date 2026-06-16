"""所有端点共用的通用 API Schema。"""

from typing import Optional, TypeVar, Generic
from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorResponse(BaseModel):
    """标准错误响应格式。"""

    code: str = Field(..., description="机器可读的错误代码", examples=["INVALID_API_KEY", "RATE_LIMITED", "MODEL_NOT_FOUND"])
    message: str = Field(..., description="人类可读的错误信息")
    details: Optional[dict] = Field(None, description="附加的错误上下文信息")

    class Config:
        json_schema_extra = {
            "example": {
                "code": "RATE_LIMITED",
                "message": "Rate limit exceeded for tenant 'org-123'. Retry after 30 seconds.",
                "details": {"retry_after_seconds": 30, "limit": 100, "current": 105},
            }
        }


class PaginatedResponse(BaseModel, Generic[T]):
    """通用分页响应包装器。"""

    items: list[T] = Field(..., description="当前页的数据列表")
    total: int = Field(..., description="所有页的数据总数", ge=0)
    page: int = Field(..., description="当前页码（从 1 开始）", ge=1)
    page_size: int = Field(..., description="每页数据条数", ge=1, le=1000)

    @property
    def pages(self) -> int:
        """总页数。"""
        return max(1, (self.total + self.page_size - 1) // self.page_size)

    @property
    def has_next(self) -> bool:
        """是否有下一页。"""
        return self.page < self.pages

    @property
    def has_previous(self) -> bool:
        """是否有上一页。"""
        return self.page > 1

    class Config:
        json_schema_extra = {
            "example": {
                "items": [{"id": "1", "name": "Item 1"}],
                "total": 100,
                "page": 1,
                "page_size": 20,
            }
        }


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str = Field(..., description="整体健康状态", examples=["healthy", "degraded", "unhealthy"])
    version: str = Field(..., description="应用版本号")
    checks: dict[str, bool] = Field(..., description="各依赖项的健康检查结果")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "version": "1.0.0",
                "checks": {
                    "database": True,
                    "redis": True,
                    "milvus": True,
                    "openai": True,
                    "anthropic": True,
                },
            }
        }
