"""Unit tests for the Skill repository."""

import pytest

from src.services.skill_store import SkillStore, SkillDefinition


@pytest.fixture
def store():
    return SkillStore()


class TestSkillStore:
    """Tests for skill CRUD + search + install."""

    def test_create_and_get(self, store):
        skill = SkillDefinition(name="代码审查", description="审查代码", instructions="你是代码审查专家")
        store.create(skill)
        assert store.get("代码审查") is skill

    def test_list_all(self, store):
        store.create(SkillDefinition(name="a"))
        store.create(SkillDefinition(name="b"))
        assert len(store) == 2

    def test_search_by_name(self, store):
        store.create(SkillDefinition(name="周报生成", description="自动生成周报"))
        store.create(SkillDefinition(name="数据分析", description="分析数据"))
        results = store.search("周报")
        assert len(results) == 1
        assert results[0].name == "周报生成"

    def test_delete(self, store):
        store.create(SkillDefinition(name="临时"))
        assert store.delete("临时") is True
        assert store.get("临时") is None

    def test_build_instructions(self, store):
        store.create(SkillDefinition(name="a", instructions="指令A"))
        store.create(SkillDefinition(name="b", instructions="指令B"))
        instructions = store.build_instructions(["a", "b"])
        assert "指令A" in instructions
        assert "指令B" in instructions

    def test_upsert_same_name(self, store):
        store.create(SkillDefinition(name="x", description="v1"))
        store.create(SkillDefinition(name="x", description="v2"))
        assert len(store) == 1
        assert store.get("x").description == "v2"
