"""Skill 仓库路由 — 技能的创建/上传、列表/搜索、拉取安装、删除。"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.api.dependencies import get_current_tenant
from src.api.dependencies import TenantContext
from src.observability.logging_setup import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/skills", tags=["技能仓库"])


class SkillCreateRequest(BaseModel):
    """创建/上传一个技能。"""

    name: str = Field(..., min_length=1, max_length=100, description="技能名（唯一）")
    description: str = Field("", description="技能说明")
    instructions: str = Field("", description="技能提示词/指令")
    tools: list[str] = Field(default_factory=list, description="绑定的工具名列表")
    author: str = Field("user", description="作者")
    version: str = Field("1.0.0", description="版本号")


class SkillInstallRequest(BaseModel):
    """安装技能（返回注入的 instructions）。"""

    skills: list[str] = Field(..., description="要安装的技能名列表")


@router.get("", response_model=dict)
async def list_skills(
    request: Request,
    search: str = "",
    tenant: TenantContext = Depends(get_current_tenant),
):
    """列出/搜索技能（仓库浏览、拉取）。"""
    store = request.app.state.skill_store
    skills = store.search(search)
    return {"items": [s.to_dict() for s in skills], "total": len(skills)}


@router.post("", response_model=dict)
async def create_skill(
    request_body: SkillCreateRequest,
    request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """创建/上传一个技能到仓库。"""
    from src.services.skill_store import SkillDefinition

    store = request.app.state.skill_store
    skill = SkillDefinition(
        name=request_body.name,
        description=request_body.description,
        instructions=request_body.instructions,
        tools=request_body.tools,
        author=request_body.author,
        version=request_body.version,
    )
    store.create(skill)
    return {"status": "created", "skill": skill.to_dict()}


@router.get("/{name}", response_model=dict)
async def get_skill(
    name: str,
    request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """获取单个技能详情。"""
    store = request.app.state.skill_store
    skill = store.get(name)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"技能 '{name}' 不存在")
    return skill.to_dict()


@router.delete("/{name}", response_model=dict)
async def delete_skill(
    name: str,
    request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """删除一个技能。"""
    store = request.app.state.skill_store
    if not store.delete(name):
        raise HTTPException(status_code=404, detail=f"技能 '{name}' 不存在")
    return {"status": "deleted", "name": name}


@router.post("/install", response_model=dict)
async def install_skills(
    request_body: SkillInstallRequest,
    request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """安装技能，返回注入到系统提示词的 instructions。"""
    store = request.app.state.skill_store
    instructions = store.build_instructions(request_body.skills)
    return {"skills": request_body.skills, "instructions": instructions}
