"""Chia văn bản KB thành các đoạn (chunk) vừa với giới hạn của model embedding.

Mục tiêu <= ~400 token mỗi chunk. Không có tokenizer ở đây nên xấp xỉ theo ký tự: tiếng Việt có dấu tốn
khoảng 3 ký tự/token với tokenizer của Qwen3, nên MAX_CHUNK_CHARS = 400 * 3 = 1200 (thiên về an toàn; giới hạn
cứng của model là 2048 token). Ưu tiên cắt ở ranh giới đoạn văn, rồi câu, cuối cùng mới cắt theo từ.
"""
import re

MAX_CHUNK_CHARS = 1200
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")


def _split_oversized(text: str, limit: int) -> list[str]:
    """Cắt một đoạn dài hơn `limit` theo câu rồi theo từ; mỗi mảnh <= limit."""
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_BREAK.split(text):
        for word_run in _split_words(sentence, limit):
            if current and len(current) + 1 + len(word_run) > limit:
                pieces.append(current)
                current = word_run
            else:
                current = f"{current} {word_run}" if current else word_run
    if current:
        pieces.append(current)
    return pieces


def _split_words(sentence: str, limit: int) -> list[str]:
    if len(sentence) <= limit:
        return [sentence]
    runs: list[str] = []
    current = ""
    for word in sentence.split():
        word = word[:limit]  # từ dài bất thường (URL...) không được vượt giới hạn
        if current and len(current) + 1 + len(word) > limit:
            runs.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        runs.append(current)
    return runs


def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Gộp các đoạn văn liên tiếp cho tới sát `max_chars`; kết quả không có chunk rỗng và mỗi chunk <= max_chars."""
    chunks: list[str] = []
    current = ""
    for paragraph in (p.strip() for p in _PARAGRAPH_BREAK.split(text)):
        if not paragraph:
            continue
        pieces = [paragraph] if len(paragraph) <= max_chars else _split_oversized(paragraph, max_chars)
        for piece in pieces:
            if current and len(current) + 2 + len(piece) > max_chars:
                chunks.append(current)
                current = piece
            else:
                current = f"{current}\n\n{piece}" if current else piece
    if current:
        chunks.append(current)
    return chunks
