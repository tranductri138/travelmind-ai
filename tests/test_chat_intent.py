"""Tests for rule-based intent classification."""

from __future__ import annotations

import pytest

from travelmind_ai.chat.intent import classify_intent_rules


# ---------------------------------------------------------------------------
# Search intent
# ---------------------------------------------------------------------------

class TestSearchIntent:
    def test_tim_khach_san_basic(self):
        assert classify_intent_rules("tìm khách sạn ở Đà Nẵng") == "search"

    def test_tim_hotel(self):
        assert classify_intent_rules("tìm hotel gần biển") == "search"

    def test_search_hotel_english(self):
        assert classify_intent_rules("search hotel in Hanoi") == "search"

    def test_resort(self):
        assert classify_intent_rules("resort ở Phú Quốc") == "search"

    def test_homestay(self):
        assert classify_intent_rules("homestay giá rẻ Đà Lạt") == "search"

    def test_nha_nghi(self):
        assert classify_intent_rules("nhà nghỉ nào tốt") == "search"

    def test_cho_o(self):
        assert classify_intent_rules("chỗ ở gần trung tâm") == "search"

    def test_goi_y_khach_san(self):
        assert classify_intent_rules("gợi ý khách sạn cho gia đình") == "search"

    def test_gioi_thieu_khach_san(self):
        assert classify_intent_rules("giới thiệu khách sạn 4 sao") == "search"

    def test_khach_san_co(self):
        assert classify_intent_rules("khách sạn có hồ bơi") == "search"

    def test_khach_san_gan(self):
        assert classify_intent_rules("khách sạn gần sân bay") == "search"

    def test_tim_phong(self):
        assert classify_intent_rules("tìm phòng ở Nha Trang") == "search"


# ---------------------------------------------------------------------------
# Popular intent
# ---------------------------------------------------------------------------

class TestPopularIntent:
    def test_top_khach_san(self):
        assert classify_intent_rules("top khách sạn Hà Nội") == "popular"

    def test_khach_san_tot_nhat(self):
        assert classify_intent_rules("khách sạn tốt nhất Đà Nẵng") == "popular"

    def test_khach_san_noi_tieng(self):
        assert classify_intent_rules("khách sạn nổi tiếng nhất") == "popular"

    def test_best_hotel(self):
        assert classify_intent_rules("best hotel in Vietnam") == "popular"

    def test_popular_hotel(self):
        assert classify_intent_rules("popular hotel near beach") == "popular"

    def test_danh_gia_cao_nhat(self):
        assert classify_intent_rules("đánh giá cao nhất") == "popular"

    def test_khach_san_pho_bien(self):
        assert classify_intent_rules("khách sạn phổ biến Sài Gòn") == "popular"

    def test_popular_takes_priority_over_search(self):
        """Popular patterns should match before search patterns."""
        assert classify_intent_rules("top khách sạn tốt nhất Đà Nẵng") == "popular"


# ---------------------------------------------------------------------------
# Details intent
# ---------------------------------------------------------------------------

class TestDetailsIntent:
    def test_chi_tiet_khach_san(self):
        assert classify_intent_rules("chi tiết khách sạn Grand Palace") == "details"

    def test_cho_xem_chi_tiet(self):
        assert classify_intent_rules("cho tôi xem chi tiết hotel đó") == "details"

    def test_thong_tin_khach_san(self):
        assert classify_intent_rules("thông tin khách sạn Sunrise") == "details"

    def test_uuid_in_message(self):
        assert classify_intent_rules(
            "xem hotel 550e8400-e29b-41d4-a716-446655440000"
        ) == "details"

    def test_biet_them(self):
        assert classify_intent_rules("tôi muốn biết thêm về nó") == "details"

    def test_review_khach_san(self):
        assert classify_intent_rules("review khách sạn đó thế nào") == "details"


# ---------------------------------------------------------------------------
# Availability intent
# ---------------------------------------------------------------------------

class TestAvailabilityIntent:
    def test_phong_trong(self):
        assert classify_intent_rules("còn phòng trống không") == "availability"

    def test_con_phong(self):
        assert classify_intent_rules("còn phòng ngày 5/3 không") == "availability"

    def test_checkin(self):
        assert classify_intent_rules("check-in ngày mai được không") == "availability"

    def test_checkout(self):
        assert classify_intent_rules("check out ngày 10/3") == "availability"

    def test_ngay_thang(self):
        assert classify_intent_rules("ngày 5 tháng 3 có phòng không") == "availability"

    def test_availability_english(self):
        assert classify_intent_rules("is there availability for March 5?") == "availability"

    def test_date_range_iso(self):
        assert classify_intent_rules("book from 2026-03-05 to 2026-03-10") == "availability"


# ---------------------------------------------------------------------------
# General / uncertain
# ---------------------------------------------------------------------------

class TestGeneralAndUncertain:
    def test_greeting(self):
        """Greetings don't match any specific pattern → None (uncertain)."""
        assert classify_intent_rules("xin chào") is None

    def test_thanks(self):
        assert classify_intent_rules("cảm ơn bạn") is None

    def test_trip_planning(self):
        assert classify_intent_rules("lên kế hoạch đi du lịch 3 ngày") is None

    def test_empty_string(self):
        assert classify_intent_rules("") == "general"

    def test_whitespace_only(self):
        assert classify_intent_rules("   ") == "general"

    def test_random_text(self):
        assert classify_intent_rules("abcdef xyz 123") is None

    def test_mixed_language_ambiguous(self):
        """Ambiguous mixed-language message → None."""
        assert classify_intent_rules("hello, tôi cần giúp đỡ") is None
