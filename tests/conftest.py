"""pytest 配置与共享 fixtures —— LLM Platform API 测试套件。

启动测试前请确保后端正在运行：
    cd src && uvicorn api.app:app --host 0.0.0.0 --port 8000

或通过环境变量指定后端地址：
    LLM_PLATFORM_BASE_URL=http://llm-platform-app:8000 pytest tests/test_api.py -v
"""

import asyncio
import os
import sys
import pytest
import pytest_asyncio
import httpx
from typing import AsyncGenerator

# 确保 src 在 path 上（供 conftest 内部使用，非必需）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# ---------------------------------------------------------------------------
# 后端地址 —— 可通过环境变量覆盖
# ---------------------------------------------------------------------------
DEFAULT_BASE_URL = os.environ.get("LLM_PLATFORM_BASE_URL", "http://localhost:8000")
DEFAULT_REQUEST_TIMEOUT = float(os.environ.get("LLM_PLATFORM_TIMEOUT", "30.0"))


@pytest.fixture(scope="session")
def base_url() -> str:
    """运行中的 LLM Platform 后端的基地址。"""
    return DEFAULT_BASE_URL


@pytest.fixture(scope="session")
def request_timeout() -> float:
    """HTTP 请求超时时间（秒）。"""
    return DEFAULT_REQUEST_TIMEOUT


# ---------------------------------------------------------------------------
# HTTP 客户端
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def async_client(
    base_url: str, request_timeout: float
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """创建 httpx AsyncClient 用于 API 测试。

    每个测试函数获得一个独立的客户端实例，测试结束后自动关闭。
    """
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(request_timeout),
    ) as client:
        yield client


@pytest.fixture
def sync_client(base_url: str, request_timeout: float):
    """创建 httpx Client（同步）用于简单的 API 测试。"""
    with httpx.Client(
        base_url=base_url,
        timeout=httpx.Timeout(request_timeout),
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# 认证头部
# ---------------------------------------------------------------------------

@pytest.fixture
def api_key_headers() -> dict[str, str]:
    """默认的 API Key 认证头部。

    可通过 LLM_PLATFORM_API_KEY 环境变量设置有效的 API Key；
    未设置时使用占位值，非健康检查接口可能返回 401/403。
    """
    test_api_key = os.environ.get("LLM_PLATFORM_API_KEY", "llm-test-key-placeholder")
    return {"X-API-Key": test_api_key}


# ---------------------------------------------------------------------------
# Pytest 标记注册
# ---------------------------------------------------------------------------

def pytest_configure(config):
    """注册项目中使用的自定义 pytest 标记。"""
    config.addinivalue_line("markers", "unit: 单元测试")
    config.addinivalue_line("markers", "integration: 集成测试")
    config.addinivalue_line("markers", "e2e: 端到端测试")
    config.addinivalue_line("markers", "slow: 耗时较长的测试")
    config.addinivalue_line("markers", "api: API 端点测试（需要运行中的后端）")


# ---------------------------------------------------------------------------
# 会话级事件循环
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop():
    """为测试会话创建默认事件循环。"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
