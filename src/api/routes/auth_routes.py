"""Auth 路由 — 简单登录（返回 demo API key）。

生产环境应使用 JWT + 密码哈希；这里是 MVP：任意用户名密码登录，
返回 demo 租户的 API key（llm-demo-key），前端用它访问后端。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.observability.logging_setup import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/auth", tags=["认证"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    api_key: str
    username: str
    role: str


@router.post("/login", response_model=LoginResponse)
async def login(request_body: LoginRequest):
    """登录（MVP：任意凭据，返回 demo API key）。"""
    # MVP 演示：任意账号密码都接受，返回 demo key（后端已 seed 的 llm-demo-key）
    if not request_body.username or not request_body.password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")

    return LoginResponse(
        access_token="demo-jwt-token",
        api_key="llm-demo-key",
        username=request_body.username,
        role="admin",
    )
