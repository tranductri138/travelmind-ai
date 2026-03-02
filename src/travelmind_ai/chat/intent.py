"""Rule-based intent classification for chat messages.

Classifies user messages into 5 intents:
- search: semantic search for hotels (e.g. "tìm khách sạn ở Đà Nẵng")
- popular: top/best/popular hotels (e.g. "khách sạn tốt nhất Hà Nội")
- details: specific hotel details (e.g. "cho xem chi tiết hotel X")
- availability: room availability check (e.g. "phòng trống ngày 5-10/3")
- general: chitchat, trip planning, multi-tool queries

Rule-based classification handles ~80% of queries. Returns None when uncertain,
triggering LLM fallback in classify_and_route node.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Intent patterns (Vietnamese + English)
# ---------------------------------------------------------------------------

_SEARCH_PATTERNS = [
    r"\btìm\b.*\bkhách sạn\b",
    r"\btìm\b.*\bhotel\b",
    r"\bsearch\b.*\bhotel",
    r"\bkhách sạn\b.*\bgần\b",
    r"\bkhách sạn\b.*\bcó\b",
    r"\bhotel\b.*\bnear\b",
    r"\bhotel\b.*\bwith\b",
    r"\bresort\b",
    r"\bhomestay\b",
    r"\bnhà nghỉ\b",
    r"\bchỗ ở\b",
    r"\bchỗ nghỉ\b",
    r"\btìm chỗ\b",
    r"\btìm phòng\b",
    r"\bgợi ý\b.*\bkhách sạn\b",
    r"\bgiới thiệu\b.*\bkhách sạn\b",
    r"\bđề xuất\b.*\bkhách sạn\b",
]

_POPULAR_PATTERNS = [
    r"\btop\b.*\bkhách sạn\b",
    r"\btop\b.*\bhotel\b",
    r"\bkhách sạn\b.*\btốt nhất\b",
    r"\bkhách sạn\b.*\bnổi tiếng\b",
    r"\bkhách sạn\b.*\bphổ biến\b",
    r"\bkhách sạn\b.*\bhot\b",
    r"\bbest\b.*\bhotel",
    r"\bpopular\b.*\bhotel",
    r"\bhot nhất\b",
    r"\bđược đánh giá cao\b",
    r"\bđánh giá cao nhất\b",
    r"\bkhách sạn\b.*\bxếp hạng\b",
]

_DETAILS_PATTERNS = [
    r"\bchi tiết\b.*\bkhách sạn\b",
    r"\bchi tiết\b.*\bhotel\b",
    r"\bcho\b.*\bxem\b.*\bchi tiết\b",
    r"\bthông tin\b.*\bkhách sạn\b",
    r"\bdetail\b",
    r"\bthêm về\b",
    r"\bbiết thêm\b",
    r"\bcho tôi biết về\b",
    r"\breview\b.*\bkhách sạn\b",
    r"\bđánh giá\b.*\bkhách sạn\b",
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
]

_AVAILABILITY_PATTERNS = [
    r"\bphòng trống\b",
    r"\bcòn phòng\b",
    r"\bcheck.?in\b",
    r"\bcheck.?out\b",
    r"\bngày\b.*\btháng\b",
    r"\bavailab",
    r"\bđặt phòng\b.*\bngày\b",
    r"\btừ\b.*\bđến\b.*\b\d{1,2}[/\-]\d{1,2}\b",
    r"\b\d{4}-\d{2}-\d{2}\b.*\b\d{4}-\d{2}-\d{2}\b",
]


def _match_any(text: str, patterns: list[str]) -> bool:
    """Check if text matches any pattern (case-insensitive)."""
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def classify_intent_rules(message: str) -> str | None:
    """Classify user message intent using rule-based patterns.

    Returns one of: "search", "popular", "details", "availability", "general".
    Returns None if the message is ambiguous and needs LLM classification.
    """
    if not message or not message.strip():
        return "general"

    text = message.strip().lower()

    # Check popular BEFORE search (popular patterns are more specific)
    if _match_any(text, _POPULAR_PATTERNS):
        return "popular"

    # Check availability (date-related queries)
    if _match_any(text, _AVAILABILITY_PATTERNS):
        return "availability"

    # Check details (specific hotel info)
    if _match_any(text, _DETAILS_PATTERNS):
        return "details"

    # Check search (general hotel discovery)
    if _match_any(text, _SEARCH_PATTERNS):
        return "search"

    # If no pattern matched, return None → LLM fallback
    return None


# ---------------------------------------------------------------------------
# LLM fallback prompt
# ---------------------------------------------------------------------------

INTENT_CLASSIFICATION_PROMPT = """\
Phân loại tin nhắn của người dùng vào đúng một intent. Chỉ trả lời tên intent, không giải thích.

Các intent:
- search: Người dùng muốn tìm/khám phá khách sạn (vd: "tìm khách sạn gần biển")
- popular: Người dùng muốn xem khách sạn tốt nhất/nổi tiếng (vd: "khách sạn tốt nhất Đà Nẵng")
- details: Người dùng hỏi chi tiết/đánh giá về một khách sạn cụ thể (vd: "cho xem chi tiết khách sạn đó")
- availability: Người dùng hỏi về phòng trống hoặc ngày cụ thể (vd: "còn phòng ngày 5/3 không")
- general: Chào hỏi, trò chuyện, lên kế hoạch du lịch, hoặc bất kỳ điều gì khác

Tin nhắn: {message}

Intent:"""
