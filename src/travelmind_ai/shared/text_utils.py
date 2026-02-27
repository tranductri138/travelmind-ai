from __future__ import annotations

import tiktoken

_encoder: tiktoken.Encoding | None = None


def _get_encoder() -> tiktoken.Encoding:
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.encoding_for_model("gpt-4o-mini")
    return _encoder


def count_tokens(text: str) -> int:
    return len(_get_encoder().encode(text))


def chunk_text(text: str, max_tokens: int = 500, overlap: int = 50) -> list[str]:
    """Split text into chunks of roughly max_tokens size with overlap."""
    encoder = _get_encoder()
    tokens = encoder.encode(text)

    if len(tokens) <= max_tokens:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        chunks.append(encoder.decode(chunk_tokens))
        if end >= len(tokens):
            break
        start += max_tokens - overlap

    return chunks


def build_hotel_text(
    name: str,
    city: str,
    country: str,
    description: str | None,
    amenities: list[str],
    stars: int,
    rating: float,
) -> str:
    """Build a searchable text representation of a hotel for embedding."""
    parts = [
        f"{name} — {stars}-star hotel in {city}, {country}",
        f"Rating: {rating}/5",
    ]
    if description:
        parts.append(description)
    if amenities:
        parts.append(f"Amenities: {', '.join(amenities)}")
    return "\n".join(parts)
