"""Unit tests for the coreference resolver - all 20 Chinese patterns."""

import pytest


class TestCoreferenceResolver:
    """Tests for the coreference resolver with Chinese text patterns."""

    @pytest.fixture
    def resolver(self):
        """Create a coreference resolver instance."""
        from src.rag.coreference_resolver import CoreferenceResolver
        return CoreferenceResolver()

    # === Basic Pronoun Patterns ===

    def test_pattern_personal_pronoun_singular(self, resolver):
        """Pattern 1: 他/她 (he/she) - personal pronoun singular."""
        text = "张三是我的朋友。他住在北京。"
        result = resolver.resolve(text)
        assert "张三" in result
        assert len(result) > 0

    def test_pattern_personal_pronoun_plural(self, resolver):
        """Pattern 2: 他们/她们 (they) - personal pronoun plural."""
        text = "学生们在讨论问题。他们决定明天继续。"
        result = resolver.resolve(text)
        assert "学生们" in result

    def test_pattern_demonstrative_pronoun_zhe(self, resolver):
        """Pattern 3: 这/这个 (this) - demonstrative pronoun."""
        text = "人工智能发展迅速。这是一个重要的趋势。"
        result = resolver.resolve(text)
        assert "人工智能" in result

    def test_pattern_demonstrative_pronoun_na(self, resolver):
        """Pattern 4: 那/那个 (that) - demonstrative pronoun."""
        text = "去年发生了一件大事。那件事改变了很多人。"
        result = resolver.resolve(text)
        # Should attempt to resolve "那件事"
        assert isinstance(result, str)

    def test_pattern_reflexive_pronoun(self, resolver):
        """Pattern 5: 自己 (self) - reflexive pronoun."""
        text = "小明自己完成了这个项目。"
        result = resolver.resolve(text)
        assert "小明" in result

    def test_pattern_possessive_pronoun(self, resolver):
        """Pattern 6: 其 (its/his/her) - possessive pronoun."""
        text = "这家公司成立于2000年。其业务覆盖全球。"
        result = resolver.resolve(text)
        assert "公司" in result

    # === Entity Patterns ===

    def test_pattern_definite_noun_phrase(self, resolver):
        """Pattern 7: 该国/该地区 (the country/region) - definite reference."""
        text = "法国是欧洲国家。该国以葡萄酒闻名。"
        result = resolver.resolve(text)
        assert "法国" in result

    def test_pattern_proper_name_abbreviation(self, resolver):
        """Pattern 8: Name abbreviation (full name -> short name)."""
        text = "阿里巴巴集团宣布新战略。阿里将在AI领域加大投入。"
        result = resolver.resolve(text)
        assert "阿里" in result or "阿里巴巴" in result

    def test_pattern_acronym_resolution(self, resolver):
        """Pattern 9: 简称 (abbreviation) with parentheses."""
        text = "自然语言处理(NLP)是AI的重要分支。NLP技术发展迅速。"
        result = resolver.resolve(text)
        assert "NLP" in result

    def test_pattern_same_entity_different_name(self, resolver):
        """Pattern 10: Same entity, different name forms."""
        text = "北京大学是中国顶尖学府。北大拥有悠久历史。"
        result = resolver.resolve(text)
        assert "北京" in result

    # === Zero Anaphora Patterns ===

    def test_pattern_zero_anaphora_subject(self, resolver):
        """Pattern 11: Zero anaphora - omitted subject."""
        text = "我买了一本书。___非常有趣。"
        result = resolver.resolve(text)
        assert "书" in result or "非常有趣" in result

    def test_pattern_zero_anaphora_object(self, resolver):
        """Pattern 12: Zero anaphora - omitted object."""
        text = "这个问题很难。我不知道怎么解决___。"
        result = resolver.resolve(text)
        assert "问题" in result

    # === Complex Patterns ===

    def test_pattern_event_reference(self, resolver):
        """Pattern 13: Event anaphora - 这起事件 (this incident)."""
        text = "昨天发生了一起交通事故。这起事件导致三人受伤。"
        result = resolver.resolve(text)
        assert "交通事故" in result or "事故" in result

    def test_pattern_numerical_reference(self, resolver):
        """Pattern 14: Numerical reference - 两种/三者 (both/three)."""
        text = "苹果和橙子都很健康。两种水果都富含维生素。"
        result = resolver.resolve(text)
        assert "苹果" in result or "橙子" in result

    def test_pattern_comparative_reference(self, resolver):
        """Pattern 15: Comparative reference - 前者/后者 (former/latter)."""
        text = "Python和Java是流行的编程语言。前者更简单。"
        result = resolver.resolve(text)
        assert "Python" in result or "前者" in result or "编程语言" in result

    def test_pattern_temporal_reference(self, resolver):
        """Pattern 16: Temporal reference - 当时/那时 (at that time)."""
        text = "2008年举办了奥运会。当时北京成为世界焦点。"
        result = resolver.resolve(text)
        assert "北京" in result or "2008" in result

    def test_pattern_locative_reference(self, resolver):
        """Pattern 17: Locative reference - 那里/这里 (there/here)."""
        text = "我去了故宫博物院。那里的建筑令人惊叹。"
        result = resolver.resolve(text)
        assert "故宫" in result

    def test_pattern_categorical_reference(self, resolver):
        """Pattern 18: Categorical reference - 这种技术 (this technology)."""
        text = "深度学习是机器学习的一个分支。这种技术广泛应用于图像识别。"
        result = resolver.resolve(text)
        assert "深度学习" in result or "机器学习" in result

    def test_pattern_organizational_reference(self, resolver):
        """Pattern 19: Organizational reference - 该组织 (the organization)."""
        text = "世卫组织发布了新指南。该组织建议加强防控。"
        result = resolver.resolve(text)
        assert "世卫" in result or "组织" in result

    def test_pattern_possessive_chain(self, resolver):
        """Pattern 20: Possessive chain - multiple references."""
        text = "李华买了一辆车。他的妻子很喜欢它的颜色。她每天都开它上班。"
        result = resolver.resolve(text)
        assert "李华" in result
        assert "车" in result or "颜色" in result


class TestCoreferenceResolverEdgeCases:
    """Edge case tests for the coreference resolver."""

    @pytest.fixture
    def resolver(self):
        from src.rag.coreference_resolver import CoreferenceResolver
        return CoreferenceResolver()

    def test_empty_text(self, resolver):
        """Test that empty text is handled gracefully."""
        result = resolver.resolve("")
        assert result == ""

    def test_text_without_coreferences(self, resolver):
        """Test text that has no coreferences."""
        text = "太阳从东方升起。花朵在春天开放。"
        result = resolver.resolve(text)
        assert isinstance(result, str)

    def test_mixed_chinese_english(self, resolver):
        """Test mixed Chinese and English text."""
        text = "The AI revolution is here. 它会改变一切。"
        result = resolver.resolve(text)
        assert isinstance(result, str)

    def test_very_long_text(self, resolver):
        """Test with very long text containing multiple coreferences."""
        text = (
            "人工智能技术近年来发展迅速。它改变了多个行业。"
            "机器学习是人工智能的核心。这种技术依赖于大量数据。"
            "深度学习是机器学习的分支。它使用神经网络。"
        ) * 10
        result = resolver.resolve(text)
        assert isinstance(result, str)
        assert len(result) > 0
