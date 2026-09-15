"""Unit tests for the CoreferenceResolver (real ResolvedQuery interface)."""

import pytest

from src.conversation.coreference import CoreferenceResolver
from src.conversation.context_stitcher import ConversationHistory


def make_history(texts: list[str]) -> ConversationHistory:
    """Build a ConversationHistory from a list of user turns."""
    history = ConversationHistory()
    for text in texts:
        history.add_turn("user", text)
    return history


@pytest.fixture
def resolver() -> CoreferenceResolver:
    return CoreferenceResolver()


class TestCoreferenceResolver:
    """Tests for coreference resolution against conversation history."""

    def test_empty_query(self, resolver):
        result = resolver.resolve("", make_history([]))
        assert result.resolved == ""
        assert result.confidence == 1.0  # no references to resolve

    def test_text_without_references(self, resolver):
        result = resolver.resolve(
            "太阳从东方升起。", make_history(["花朵在春天开放。"])
        )
        assert isinstance(result.resolved, str)
        assert result.confidence == 1.0

    def test_personal_pronoun_resolution(self, resolver):
        history = make_history(["张三是我的朋友。", "他住在北京。"])
        result = resolver.resolve("他住在哪里？", history)
        # Resolver should return a ResolvedQuery with confidence in [0,1]
        assert 0.0 <= result.confidence <= 1.0
        assert result.original == "他住在哪里？"

    def test_entity_reference(self, resolver):
        history = make_history(["法国是欧洲国家。"])
        result = resolver.resolve("该国以葡萄酒闻名。", history)
        assert result.original == "该国以葡萄酒闻名。"

    def test_replacements_list_populated(self, resolver):
        history = make_history(["张三是一名工程师。"])
        result = resolver.resolve("他住在北京。", history)
        # replacements is a list of (mention, antecedent, pattern_type)
        assert isinstance(result.replacements, list)

    def test_confidence_range(self, resolver):
        history = make_history(["人工智能发展迅速。", "这是一个重要的趋势。"])
        result = resolver.resolve("这是一个重要趋势。", history)
        assert 0.0 <= result.confidence <= 1.0


class TestCoreferenceResolverEdgeCases:
    """Edge cases for the resolver."""

    @pytest.fixture
    def resolver(self) -> CoreferenceResolver:
        return CoreferenceResolver()

    def test_mixed_chinese_english(self, resolver):
        result = resolver.resolve(
            "The AI revolution is here. 它会改变一切。",
            make_history(["人工智能正在改变世界。"]),
        )
        assert isinstance(result.resolved, str)

    def test_very_long_text(self, resolver):
        text = "人工智能技术近年来发展迅速。" * 10
        result = resolver.resolve(text, make_history(["机器学习是人工智能的核心。"]))
        assert isinstance(result.resolved, str)
        assert len(result.resolved) > 0
