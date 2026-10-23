"""Chunking: mỗi chunk <= giới hạn (~400 token xấp xỉ theo ký tự), không mất chữ, ưu tiên ranh giới đoạn/câu."""
import re

import pytest

from app.kb.chunking import MAX_CHUNK_CHARS, chunk_text
from app.kb.documents import PolicyNumbers, build_kb_documents


def _words(text: str) -> list[str]:
    return text.split()


def test_short_text_is_a_single_chunk():
    assert chunk_text("Một đoạn ngắn.") == ["Một đoạn ngắn."]


def test_empty_or_blank_text_has_no_chunks():
    assert chunk_text("") == [] and chunk_text("  \n\n \n") == []


def test_paragraphs_are_packed_up_to_limit_without_splitting_them():
    paragraphs = [f"Đoạn {i}. " + "chữ " * 60 for i in range(10)]  # mỗi đoạn ~250 ký tự
    chunks = chunk_text("\n\n".join(paragraphs), max_chars=600)
    assert all(len(c) <= 600 for c in chunks)
    assert len(chunks) > 1
    for p in paragraphs:
        assert sum(p.strip() in c for c in chunks) == 1, "đoạn văn phải nằm trọn trong đúng một chunk"


def test_oversized_paragraph_is_split_on_sentences_then_words():
    sentence = "Câu thử nghiệm có độ dài vừa phải để kiểm tra việc cắt. "
    text = sentence * 80
    chunks = chunk_text(text, max_chars=300)
    assert all(0 < len(c) <= 300 for c in chunks)
    assert _words(" ".join(chunks)) == _words(text)
    assert all(c.endswith(".") for c in chunks), "cắt ở ranh giới câu khi có thể"

    no_punctuation = "từ " * 500
    chunks = chunk_text(no_punctuation, max_chars=100)
    assert all(len(c) <= 100 for c in chunks)
    assert _words(" ".join(chunks)) == _words(no_punctuation)


def test_single_giant_token_is_truncated_to_the_limit():
    chunks = chunk_text("x" * 5000, max_chars=100)
    assert all(len(c) <= 100 for c in chunks)


def test_default_limit_is_about_400_tokens_at_three_chars_per_token():
    assert MAX_CHUNK_CHARS == 400 * 3


@pytest.mark.parametrize("lang", ["vi", "en"])
def test_every_seed_document_chunks_within_limit_and_keeps_content(lang):
    for doc in build_kb_documents(PolicyNumbers(7, 30000, 500000)):
        if doc["lang"] != lang:
            continue
        chunks = chunk_text(doc["body"])
        assert chunks and all(len(c) <= MAX_CHUNK_CHARS for c in chunks)
        assert re.sub(r"\s+", " ", " ".join(chunks)) == re.sub(r"\s+", " ", doc["body"])
