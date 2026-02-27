from travelmind_ai.shared.text_utils import build_hotel_text, chunk_text, count_tokens


def test_count_tokens():
    assert count_tokens("hello world") > 0


def test_chunk_text_short():
    text = "This is a short sentence."
    chunks = chunk_text(text, max_tokens=500)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_text_long():
    text = "word " * 1000  # ~1000 tokens
    chunks = chunk_text(text, max_tokens=200, overlap=20)
    assert len(chunks) > 1
    # Each chunk should be non-empty
    for chunk in chunks:
        assert len(chunk) > 0


def test_build_hotel_text():
    result = build_hotel_text(
        name="Grand Hotel",
        city="Paris",
        country="France",
        description="A lovely hotel",
        amenities=["Pool", "Spa"],
        stars=5,
        rating=4.8,
    )
    assert "Grand Hotel" in result
    assert "Paris" in result
    assert "5-star" in result
    assert "Pool" in result
    assert "4.8" in result


def test_build_hotel_text_no_description():
    result = build_hotel_text(
        name="Simple Inn",
        city="London",
        country="UK",
        description=None,
        amenities=[],
        stars=3,
        rating=3.5,
    )
    assert "Simple Inn" in result
    assert "Amenities" not in result
