"""Tests for :mod:`md_tts.parser`."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from md_tts.parser import Block, parse_markdown

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_blocks() -> list[Block]:
    text = (FIXTURES / "sample.md").read_text(encoding="utf-8")
    return list(parse_markdown(text))


def test_sample_yields_expected_block_kinds(sample_blocks: list[Block]) -> None:
    counts = Counter(b.kind for b in sample_blocks)
    assert counts["code"] == 1
    assert counts["table"] == 1
    assert counts["card"] == 2
    assert counts["text"] >= 6  # heading + paragraphs + quote + list + hr + closing


def test_heading_is_prefixed(sample_blocks: list[Block]) -> None:
    heading = next(b for b in sample_blocks if b.raw_preview.startswith("# "))
    # Capítulo o Chapter — depende del idioma detectado
    assert heading.content.endswith(".")
    assert any(heading.content.startswith(p) for p in ("Capítulo: ", "Chapter: "))


def test_code_block_preserves_content(sample_blocks: list[Block]) -> None:
    code = next(b for b in sample_blocks if b.kind == "code")
    assert "def hello" in code.raw_preview
    assert code.info == "python"
    assert code.content == ""  # not spoken


def test_table_summarizes_rows(sample_blocks: list[Block]) -> None:
    table = next(b for b in sample_blocks if b.kind == "table")
    assert "filas" in table.info
    assert "Col A | Col B" in table.raw_preview


def test_flashcards_capture_question_and_answer(sample_blocks: list[Block]) -> None:
    cards = [b for b in sample_blocks if b.kind == "card"]
    assert len(cards) == 2

    # Spanish card
    es_card = next(c for c in cards if "knowledge graph" in c.content)
    assert "nodos" in es_card.extra

    # English card
    en_card = next(c for c in cards if "vector database" in c.content)
    assert "similarity search" in en_card.extra


def test_list_yields_numbered_speech(sample_blocks: list[Block]) -> None:
    text_blocks = [b for b in sample_blocks if b.kind == "text"]
    list_block = next(b for b in text_blocks if "Punto 1" in b.content)
    assert "Punto 2" in list_block.content
    assert "Punto 3" in list_block.content


def test_blockquote_gets_quote_prefix(sample_blocks: list[Block]) -> None:
    quoted = next(b for b in sample_blocks if "cita relevante" in b.content)
    assert quoted.content.startswith("Cita: ")


def test_hr_yields_separator() -> None:
    text = "Antes\n\n---\n\nDespués\n"
    blocks = list(parse_markdown(text))
    assert any(b.content == "Separador." for b in blocks)


def test_inline_code_is_marked_audibly() -> None:
    text = "Usa el comando `git status` ahora."
    [block] = list(parse_markdown(text))
    assert "código git status" in block.content


def test_empty_input_yields_no_blocks() -> None:
    assert list(parse_markdown("")) == []
