"""Entity tracking with abbreviation expansion and cross-turn entity accumulation.

Extracts entities from text using regex patterns, resolves Chinese/English
abbreviations, and maintains a cross-turn entity index with relationship tracking.
"""

from __future__ import annotations

import re
from typing import Any


class EntityTracker:
    """Track and accumulate entities across conversation turns.

    Features:
    - Regex-based entity extraction for Chinese and English text
    - Configurable abbreviation expansion dictionary
    - Cross-turn entity index with first-mention tracking
    - Related entity inference via co-occurrence
    """

    # ------------------------------------------------------------------
    # Configurable abbreviation dictionary
    # ------------------------------------------------------------------
    ABBREVIATIONS: dict[str, str] = {
        # Chinese business & government
        "国网": "国家电网",
        "央行": "中国人民银行",
        "工行": "中国工商银行",
        "建行": "中国建设银行",
        "农行": "中国农业银行",
        "中行": "中国银行",
        "招行": "招商银行",
        "交行": "交通银行",
        "证监会": "中国证券监督管理委员会",
        "银保监会": "中国银行保险监督管理委员会",
        "发改委": "国家发展和改革委员会",
        "工信部": "工业和信息化部",
        "科技部": "科学技术部",
        "外交部": "中华人民共和国外交部",
        "商务部": "中华人民共和国商务部",
        "人社部": "人力资源和社会保障部",
        "国税总局": "国家税务总局",
        "国资委": "国务院国有资产监督管理委员会",
        # Chinese tech
        "阿里": "阿里巴巴集团",
        "腾讯": "腾讯控股有限公司",
        "百度": "百度公司",
        "华为": "华为技术有限公司",
        "小米": "小米集团",
        "字节": "字节跳动有限公司",
        "美团": "美团点评",
        "京东": "京东集团",
        "拼多多": "拼多多",
        "滴滴": "滴滴出行",
        # Chinese common
        "AI": "人工智能",
        "ML": "机器学习",
        "NLP": "自然语言处理",
        "CV": "计算机视觉",
        "IoT": "物联网",
        "5G": "第五代移动通信技术",
        "SaaS": "软件即服务",
        "PaaS": "平台即服务",
        "IaaS": "基础设施即服务",
        # English common
        "API": "Application Programming Interface",
        "SDK": "Software Development Kit",
        "UI": "User Interface",
        "UX": "User Experience",
        "DB": "Database",
        "K8s": "Kubernetes",
        "AWS": "Amazon Web Services",
        "GCP": "Google Cloud Platform",
        "LLM": "Large Language Model",
        "RAG": "Retrieval-Augmented Generation",
        "GPU": "Graphics Processing Unit",
        "CPU": "Central Processing Unit",
        "HTTP": "Hypertext Transfer Protocol",
        "HTTPS": "Hypertext Transfer Protocol Secure",
        "DNS": "Domain Name System",
        "CDN": "Content Delivery Network",
        "SQL": "Structured Query Language",
        "NoSQL": "Not Only SQL",
        "JSON": "JavaScript Object Notation",
        "YAML": "YAML Ain't Markup Language",
        "CSV": "Comma-Separated Values",
        "PDF": "Portable Document Format",
        "OCR": "Optical Character Recognition",
        "TTS": "Text-to-Speech",
        "ASR": "Automatic Speech Recognition",
    }

    # ------------------------------------------------------------------
    # Entity extraction patterns
    # ------------------------------------------------------------------
    _CN_ENTITY_PATTERNS: list[tuple[str, str]] = [
        # Chinese company/organization names
        ("company", r"(?:[一-鿿]{2,8}(?:公司|集团|有限|科技|技术|股份|控股|银行|保险|证券|基金|信托|医院|大学|学院|研究所|研究院|中心))"),
        # Chinese person names (2-4 characters, surname + given name pattern)
        ("person", r"(?:[李王张刘陈杨赵黄周吴徐孙马胡朱郭何罗高林郑梁谢唐许冯宋韩邓彭曹曾田萧潘袁蔡蒋余杜叶程苏魏吕丁任卢姚钟姜崔谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤][一-鿿]{1,2})"),
        # Product/model names
        ("product", r"(?:[A-Za-z0-9]+[- ]?(?:系列|型号|版本|V\d+\.?\d*|\d+\.\d+))"),
        # Dates
        ("date", r"(?:\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日号]?)"),
        # Percentages
        ("percentage", r"(?:\d+\.?\d*\s*%)"),
        # Monetary amounts
        ("money", r"(?:[¥$€£]\s*\d+\.?\d*(?:万|亿|k|m|b)?)"),
        # Chinese place names (province/city patterns)
        ("location", r"(?:[一-鿿]{2,4}(?:省|市|区|县|镇|村|街道|路|大厦|广场|园区|开发区|新区))"),
        # English named entities (capitalized multi-word)
        ("en_entity", r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b"),
        # URLs
        ("url", r"(?:https?://[^\s]+|www\.[^\s]+)"),
        # Email addresses
        ("en_email_entity", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
        # Version numbers
        ("version", r"\bv?\d+\.\d+(?:\.\d+)?(?:-[a-zA-Z0-9]+)?\b"),
        # Hashtags
        ("hashtag", r"#[^\s#]+"),
    ]

    def __init__(self, abbreviations: dict[str, str] | None = None) -> None:
        """Initialize the entity tracker.

        Args:
            abbreviations: Optional custom abbreviation dictionary to merge with defaults.
        """
        self._abbreviations = dict(self.ABBREVIATIONS)
        if abbreviations:
            self._abbreviations.update(abbreviations)

        # Entity index: entity_name -> metadata
        self._entities: dict[str, dict[str, Any]] = {}
        # Co-occurrence tracking: entity -> set of entities that appeared together
        self._co_occurrence: dict[str, set[str]] = {}
        self._turn_count: int = 0

    def extract_entities(self, text: str) -> list[str]:
        """Extract entities from text using regex-based patterns.

        Args:
            text: The input text to extract entities from.

        Returns:
            A list of extracted entity strings (resolved abbreviations).
        """
        entities: list[str] = []
        seen: set[str] = set()

        # First, resolve all abbreviations in the text
        resolved_text = self.resolve_abbreviation(text)

        for entity_type, pattern in self._CN_ENTITY_PATTERNS:
            for match in re.finditer(pattern, resolved_text):
                entity = match.group(0).strip()
                # Skip if too short, too long, or already seen
                if len(entity) < 2 or len(entity) > 100:
                    continue
                # Skip pure numbers
                if re.match(r'^[\d.,%¥$€£\s]+$', entity):
                    if entity_type not in ("percentage", "money", "date", "version"):
                        continue
                if entity.lower() not in seen:
                    entities.append(entity)
                    seen.add(entity.lower())

        # Also extract abbreviations themselves
        for abbr in self._abbreviations:
            if abbr in text and abbr not in seen:
                entities.append(abbr)
                seen.add(abbr.lower())

        # Update internal index
        self._turn_count += 1
        for entity in entities:
            if entity not in self._entities:
                self._entities[entity] = {
                    "first_mentioned": self._turn_count,
                    "mention_count": 1,
                    "type": self._guess_entity_type(entity),
                }
            else:
                self._entities[entity]["mention_count"] += 1

        # Update co-occurrence
        for i, e1 in enumerate(entities):
            if e1 not in self._co_occurrence:
                self._co_occurrence[e1] = set()
            for e2 in entities[i + 1:]:
                self._co_occurrence[e1].add(e2)
                if e2 not in self._co_occurrence:
                    self._co_occurrence[e2] = set()
                self._co_occurrence[e2].add(e1)

        return entities

    def _guess_entity_type(self, entity: str) -> str:
        """Guess the type of an entity based on its content."""
        if any(suffix in entity for suffix in ["公司", "集团", "有限", "银行", "保险", "证券"]):
            return "organization"
        if any(suffix in entity for suffix in ["省", "市", "区", "县", "镇", "村", "路", "大厦"]):
            return "location"
        if re.match(r'\d{4}[-/年]', entity):
            return "date"
        if '%' in entity:
            return "percentage"
        if any(c in entity for c in '¥$€£'):
            return "money"
        if re.match(r'^https?://', entity):
            return "url"
        if '@' in entity:
            return "email"
        if re.match(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+$', entity):
            return "en_name"
        return "unknown"

    def resolve_abbreviation(self, text: str) -> str:
        """Expand known abbreviations in the text.

        Args:
            text: Input text potentially containing abbreviations.

        Returns:
            Text with abbreviations expanded.
        """
        result = text
        # Sort by length (longest first) to avoid partial replacements
        sorted_abbrs = sorted(self._abbreviations.keys(), key=len, reverse=True)
        for abbr in sorted_abbrs:
            full = self._abbreviations[abbr]
            # Replace only if abbreviation appears as a standalone term
            # (surrounded by non-word boundaries or Chinese characters)
            result = re.sub(
                rf'(?<=[一-鿿\s。,，、；;：:！!？?"\'\"()（）【】\[\]{{}}])?{re.escape(abbr)}(?=[一-鿿\s。,，、；;：:！!？?"\'\"()（）【】\[\]{{}}])?',
                lambda m: full if m.group(0) == abbr else m.group(0),
                result,
            )
        return result

    def get_entity_context(self, entity_name: str) -> dict[str, Any]:
        """Get context information for a specific entity.

        Args:
            entity_name: The entity to look up.

        Returns:
            A dictionary with first_mentioned turn, mention_count,
            type, and related_entities (via co-occurrence).
        """
        entity_info = self._entities.get(entity_name, {})
        related = list(self._co_occurrence.get(entity_name, set()))

        return {
            "entity": entity_name,
            "first_mentioned": entity_info.get("first_mentioned", 0),
            "mention_count": entity_info.get("mention_count", 0),
            "type": entity_info.get("type", "unknown"),
            "related_entities": related,
        }

    def get_all_entities_sorted(self) -> list[dict[str, Any]]:
        """Get all tracked entities sorted by first mention order."""
        sorted_items = sorted(self._entities.items(),
                              key=lambda x: x[1].get("first_mentioned", 0))
        return [
            {
                "entity": name,
                "first_mentioned": info.get("first_mentioned", 0),
                "mention_count": info.get("mention_count", 0),
                "type": info.get("type", "unknown"),
            }
            for name, info in sorted_items
        ]

    def add_abbreviation(self, abbr: str, full: str) -> None:
        """Add a custom abbreviation to the resolver."""
        self._abbreviations[abbr] = full

    def reset(self) -> None:
        """Reset all tracked state."""
        self._entities.clear()
        self._co_occurrence.clear()
        self._turn_count = 0
