"""Tone adaptation: mood detection and response tone adjustment.

Detects user emotional state from text and adapts response tone
accordingly, including situational empathy phrases.
"""

from __future__ import annotations

import re
from typing import Any


class ToneAdapter:
    """Detect user mood and adapt response tone dynamically.

    Features:
    - Multi-mood detection (frustrated, satisfied, anxious, neutral, excited, confused)
    - Response tone adaptation (soften, energize, clarify, etc.)
    - Situational empathy phrase generation
    - Combined mood scoring with keyword and pattern analysis
    """

    # ------------------------------------------------------------------
    # Mood keyword dictionaries (Chinese + English)
    # ------------------------------------------------------------------
    _MOOD_KEYWORDS: dict[str, dict[str, list[str]]] = {
        "frustrated": {
            "cn": [
                "烦死了", "无语", "搞什么", "怎么回事", "太差了", "不行", "气死",
                "浪费", "白费", "受不了", "真烦", "糟糕", "崩溃", "抓狂",
                "算了", "随便", "不管了", "放弃", "没用", "根本不行",
                "又出问题了", "还是不行", "一直这样", "老是", "总是",
                "垃圾", "坑爹", "差劲", "坑人", "骗人", "坑", "烂",
                "能不能行", "到底行不行", "怎么又", "还不行",
            ],
            "en": [
                "frustrated", "annoying", "ridiculous", "unbelievable",
                "doesn't work", "not working", "broken", "useless",
                "waste of time", "fed up", "sick of", "tired of",
                "again?", "still not", "why won't", "this is bad",
                "terrible", "awful", "horrible", "furious", "angry",
                "fix this", "what the", "so bad", "so slow",
                "not helping", "pointless", "whatever",
            ],
        },
        "anxious": {
            "cn": [
                "担心", "着急", "紧急", "怎么办", "来不及", "快点", "赶紧",
                "害怕", "紧张", "焦虑", "不安", "急急", "救命", "求救",
                "快快快", "马上", "立刻", "迫不及", "等不了", "不能等",
                "会不会", "万一", "如果", "要是", "怕", "忧心",
                "赶时间", "时限", "截止", "逾期", "过期",
            ],
            "en": [
                "worried", "urgent", "emergency", "hurry", "quick",
                "asap", "anxious", "nervous", "scared", "afraid",
                "what if", "running out of time", "deadline",
                "panic", "stressed", "pressure", "hurry up",
                "can't wait", "right now", "immediately",
                "help me", "please help", "need help",
            ],
        },
        "excited": {
            "cn": [
                "太好了", "太棒了", "厉害", "牛", "赞", "完美", "超棒",
                "开心", "高兴", "激动", "兴奋", "惊喜", "惊喜",
                "哇", "哈哈", "嘿嘿", "nice", "cool", "awesome",
                "牛逼", "给力", "绝了", "无敌", "强", "顶",
                "非常好", "很不错", "很满意", "满意", "好评",
            ],
            "en": [
                "awesome", "great", "amazing", "excellent", "wonderful",
                "fantastic", "love it", "perfect", "brilliant",
                "so good", "so happy", "excited", "thrilled",
                "wow", "nice", "cool", "super", "best",
                "incredible", "outstanding", "impressive",
                "love this", "so cool", "so great",
            ],
        },
        "confused": {
            "cn": [
                "不懂", "不明白", "什么意思", "没看懂", "不理解", "搞不懂",
                "疑惑", "奇怪", "费解", "迷糊", "懵", "糊涂",
                "什么意思", "啥意思", "什么情况", "这是什么",
                "怎么用", "不会用", "不清楚", "不确定", "不知道",
                "我试试", "可能", "大概", "也许", "或许",
            ],
            "en": [
                "confused", "don't understand", "what do you mean",
                "unclear", "not sure", "don't know", "how does",
                "what is", "explain", "clarify", "puzzled",
                "lost", "don't get it", "doesn't make sense",
                "what's that", "how to", "i'm not sure",
                "not following", "i'm lost", "can you explain",
            ],
        },
        "satisfied": {
            "cn": [
                "好的", "可以", "行", "没问题", "不错", "挺好",
                "满意", "认可", "接受", "赞同", "同意", "ok",
                "行的", "了解了", "明白了", "知道了", "懂了",
                "收到", "好的谢谢", "感谢", "多谢", "谢谢",
            ],
            "en": [
                "ok", "okay", "good", "fine", "alright", "sure",
                "thank you", "thanks", "got it", "understood",
                "that works", "sounds good", "perfect", "will do",
                "i see", "makes sense", "agreed", "correct",
                "satisfied", "happy with", "pleased",
            ],
        },
    }

    # ------------------------------------------------------------------
    # Empathy phrases by mood
    # ------------------------------------------------------------------
    _EMPATHY_PHRASES: dict[str, dict[str, list[str]]] = {
        "frustrated": {
            "cn": [
                "我理解您的 frustration，让我帮您尽快解决这个问题。",
                "很抱歉给您带来不便，我们马上来解决。",
                "我明白这让您很困扰，让我来帮您处理。",
                "不着急，我们一起来看看问题出在哪里。",
                "感谢您的耐心，我会尽最大努力帮您解决。",
            ],
            "en": [
                "I understand your frustration — let me help resolve this for you.",
                "I'm sorry for the inconvenience. Let's get this sorted out.",
                "I can see this has been frustrating. Let me take care of it.",
                "Thank you for your patience — I'll make this right.",
                "I hear you. Let me work on a solution right away.",
            ],
        },
        "anxious": {
            "cn": [
                "请放心，我会尽快帮您处理。",
                "别着急，我们一步一步来解决。",
                "我明白时间紧迫，我们马上就办。",
                "您别担心，这件事交给我来处理。",
                "我在这里帮您，请放心。",
            ],
            "en": [
                "Don't worry — I'll help you get this sorted quickly.",
                "I understand the urgency. Let's handle this step by step.",
                "You're in good hands. Let me take care of this for you.",
                "I know this is time-sensitive. Let's address it right now.",
                "Rest assured, I'm on it.",
            ],
        },
        "excited": {
            "cn": [
                "很高兴您这么满意！有什么我可以继续帮您的吗？",
                "太好了！很高兴能帮到您。",
                "感谢您的肯定！我们会继续努力。",
                "您的满意就是我们最大的动力！",
            ],
            "en": [
                "I'm glad you're excited! What else can I help with?",
                "That's wonderful to hear! Happy to help.",
                "Thank you for the enthusiasm! Let me know if you need anything else.",
                "So glad you're happy with the result!",
            ],
        },
        "confused": {
            "cn": [
                "让我换个方式解释一下，可能会更清楚。",
                "抱歉没说清楚，让我重新说明一下。",
                "没关系，我来帮您理清思路。",
                "让我一步步来解释，您看是否更好理解。",
            ],
            "en": [
                "Let me explain that differently — it might be clearer.",
                "Sorry for the confusion. Let me rephrase that.",
                "No problem — let me break this down more simply.",
                "Let me walk through this step by step.",
            ],
        },
        "neutral": {
            "cn": [
                "有什么我可以帮您的吗？",
                "请随时告诉我您的需求。",
                "我在这里为您服务。",
            ],
            "en": [
                "How can I help you today?",
                "I'm here to assist — just let me know what you need.",
                "What can I do for you?",
            ],
        },
    }

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Mood detection
    # ------------------------------------------------------------------

    def detect_mood(self, text: str) -> str:
        """Detect the user's emotional mood from text.

        Uses a multi-signal approach:
        1. Keyword scoring per mood category
        2. Punctuation intensity (exclamation marks, question marks)
        3. Capitalization patterns (for English)
        4. Sentence length and structure

        Args:
            text: The user's message text.

        Returns:
            One of: "frustrated", "satisfied", "anxious", "neutral",
            "excited", "confused"
        """
        text_lower = text.lower()

        # Score each mood
        scores: dict[str, float] = {}
        for mood, keyword_dict in self._MOOD_KEYWORDS.items():
            score = 0.0
            # Chinese keywords
            for kw in keyword_dict.get("cn", []):
                if kw in text:
                    score += 1.0
            # English keywords
            for kw in keyword_dict.get("en", []):
                pattern = re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
                score += len(pattern.findall(text)) * 1.0
            scores[mood] = score

        # Apply punctuation intensity modifiers
        excl_count = text.count("!") + text.count("！")
        ques_count = text.count("?") + text.count("？")

        # Multiple exclamation marks suggest strong emotion
        if excl_count >= 2:
            scores["frustrated"] += excl_count * 0.5
            scores["excited"] += excl_count * 0.5
        elif excl_count == 1:
            scores["excited"] += 0.3
            scores["frustrated"] += 0.1

        # Multiple question marks suggest confusion or frustration
        if ques_count >= 2:
            scores["confused"] += ques_count * 0.5
            scores["frustrated"] += ques_count * 0.3
        elif ques_count == 1:
            scores["confused"] += 0.2

        # ALL CAPS words suggest frustration or urgency (English)
        caps_words = re.findall(r'\b[A-Z]{2,}\b', text)
        if caps_words:
            scores["frustrated"] += len(caps_words) * 0.3
            scores["anxious"] += len(caps_words) * 0.1

        # Very short messages with question marks -> confused
        if len(text.strip()) < 20 and ques_count >= 1:
            scores["confused"] += 0.5

        # Determine the dominant mood
        max_score = max(scores.values()) if scores else 0.0

        if max_score == 0.0:
            return "neutral"
        if max_score < 1.5:
            return "neutral"

        # In case of tie, prefer the more actionable mood
        max_moods = [m for m, s in scores.items() if s == max_score]
        if len(max_moods) > 1:
            priority = ["confused", "frustrated", "anxious", "excited", "satisfied", "neutral"]
            for p in priority:
                if p in max_moods:
                    return p

        return max_moods[0]

    # ------------------------------------------------------------------
    # Response adaptation
    # ------------------------------------------------------------------

    def adapt_response(self, response: str, target_tone: str) -> str:
        """Adapt a response to match the target tone.

        Applies text-level transformations to adjust formality, empathy,
        and energy level of the response.

        Args:
            response: The original response text.
            target_tone: The target mood/tone to adapt toward.

        Returns:
            The adapted response text.
        """
        if target_tone == "neutral":
            return response

        adaptations: dict[str, Any] = {
            "frustrated": {
                "prefix_cn": "我理解您的 frustration。",
                "prefix_en": "I understand your frustration. ",
                "soften": True,
                "add_help_offer": True,
            },
            "anxious": {
                "prefix_cn": "请放心，",
                "prefix_en": "Rest assured, ",
                "soften": True,
                "add_help_offer": True,
            },
            "excited": {
                "prefix_cn": "太好了！",
                "prefix_en": "Great! ",
                "soften": False,
                "add_help_offer": False,
            },
            "confused": {
                "prefix_cn": "让我详细说明一下：",
                "prefix_en": "Let me explain in detail: ",
                "soften": True,
                "add_help_offer": True,
            },
            "satisfied": {
                "prefix_cn": "",
                "prefix_en": "",
                "soften": False,
                "add_help_offer": True,
            },
        }

        config = adaptations.get(target_tone, adaptations["neutral"])
        prefix = config.get("prefix_cn", "") if self._is_chinese_text(response) else config.get("prefix_en", "")

        adapted = response

        # Add empathetic prefix
        if prefix and not adapted.startswith(prefix):
            adapted = prefix + adapted

        # Soften harsh language (remove overly blunt phrasing)
        if config.get("soften"):
            adapted = self._soften_language(adapted)

        # Add help offer at the end
        if config.get("add_help_offer"):
            if self._is_chinese_text(response):
                if not adapted.rstrip().endswith(("？", "?", "。", ".")):
                    adapted += "。"
                if "还有什么" not in adapted and "其他" not in adapted and "还有什么" not in adapted:
                    adapted += "还有什么我可以帮您的吗？"
            else:
                if "else" not in adapted.lower() and "other" not in adapted.lower():
                    if not adapted.rstrip().endswith(("?", ".", "!")):
                        adapted += ". "
                    adapted += "Is there anything else I can help with?"

        return adapted

    # ------------------------------------------------------------------
    # Empathy phrases
    # ------------------------------------------------------------------

    def get_empathy_phrase(self, mood: str, language: str = "auto") -> str:
        """Get a situational empathy phrase for the detected mood.

        Args:
            mood: The detected mood (frustrated, satisfied, anxious, etc.).
            language: "cn", "en", or "auto" (detects from mood context).

        Returns:
            An appropriate empathy phrase string.
        """
        phrases = self._EMPATHY_PHRASES.get(mood, self._EMPATHY_PHRASES["neutral"])

        if language == "auto":
            language = "cn"  # Default to Chinese

        lang_phrases = phrases.get(language, phrases.get("en", ["How can I help?"]))

        import random
        return random.choice(lang_phrases)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_chinese_text(text: str) -> bool:
        """Heuristic: does the text contain Chinese characters?"""
        return bool(re.search(r'[一-鿿]', text))

    @staticmethod
    def _soften_language(text: str) -> str:
        """Soften overly direct or blunt language.

        Replaces urgent/demanding expressions with softer alternatives.
        """
        if ToneAdapter._is_chinese_text(text):
            replacements = {
                "你必须": "请您",
                "你应该": "建议您",
                "你不能": "建议您不要",
                "不行": "可能不太合适",
                "不可以": "不建议",
                "马上做": "尽快处理",
                "立刻": "尽快",
                "不准": "请勿",
                "禁止": "请避免",
                "强制": "需要",
            }
            for harsh, soft in replacements.items():
                text = text.replace(harsh, soft)
        else:
            replacements_en = {
                "You must": "Please",
                "you must": "please",
                "You have to": "I recommend you",
                "you have to": "I recommend you",
                "You cannot": "I would suggest avoiding",
                "you cannot": "I would suggest avoiding",
                "You should not": "It may be better to avoid",
                "Do not": "Please avoid",
                "Don't": "Please don't",
                "Immediately": "As soon as possible",
                "immediately": "as soon as possible",
                "Right now": "At your earliest convenience",
                "You need to": "I recommend you",
                "you need to": "I recommend you",
            }
            for harsh, soft in replacements_en.items():
                pattern = re.compile(r'\b' + re.escape(harsh) + r'\b')
                text = pattern.sub(soft, text)

        return text
