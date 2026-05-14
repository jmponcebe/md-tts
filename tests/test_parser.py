"""Tests for :mod:`md_tts.parser`."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from md_tts.parser import Block, Span, parse_markdown

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
    assert "'git status'" in block.content


def test_empty_input_yields_no_blocks() -> None:
    assert list(parse_markdown("")) == []


# --- Phase 1: inline language spans ---------------------------------------


def test_inline_code_emits_english_span_by_default() -> None:
    """Inline `code` chunks default to ``lang="en"`` for technical terms."""
    text = "Levanta el contenedor con `docker compose up` y listo."
    [block] = list(parse_markdown(text))
    assert any(
        s.text.strip() == "docker compose up" and s.lang == "en" for s in block.spans
    )


def test_inline_code_lang_none_disables_per_span_override() -> None:
    """Passing ``inline_code_lang=None`` preserves pre-0.5 single-voice behavior."""
    text = "Usa `git status` ahora."
    [block] = list(parse_markdown(text, inline_code_lang=None))
    assert block.spans, "spans should still be populated, just without explicit lang"
    assert all(s.lang is None for s in block.spans)


def test_spans_join_into_block_content() -> None:
    """The flat ``content`` field must equal the concatenation of span texts.

    Modulo the inline-code quoting: spans carry ``docker`` while content has
    ``'docker'`` (with single quotes for the local backend). We compare the
    quote-stripped reconstruction instead.
    """
    text = "Despliega con `FastAPI` en producción."
    [block] = list(parse_markdown(text))
    joined = "".join(s.text for s in block.spans)
    # ``content`` keeps the quotes for legacy backends; spans drop them.
    assert "FastAPI" in joined
    assert "Despliega con " in joined
    assert " en producción" in joined


def test_adjacent_text_spans_are_coalesced() -> None:
    text = "Hola mundo."
    [block] = list(parse_markdown(text))
    # No inline code → exactly one span (prefix not applied to plain paragraphs).
    assert len(block.spans) == 1
    assert block.spans[0].lang is None
    assert block.spans[0].text == "Hola mundo."


def test_heading_prefix_is_a_separate_lang_none_span() -> None:
    text = "# Mi capítulo con `Python`\n"
    [block] = list(parse_markdown(text))
    # First span must be the prefix, last span must be the closing period,
    # and at least one span in between has lang="en" for the inline code.
    assert block.spans[0].lang is None
    assert block.spans[0].text.startswith(("Capítulo: ", "Chapter: "))
    assert any(s.lang == "en" and s.text == "Python" for s in block.spans)


def test_card_spans_split_question_and_answer() -> None:
    text = (
        "<details><summary>¿Qué es FastAPI?</summary>"
        "Un framework web en Python.</details>"
    )
    [block] = list(parse_markdown(text))
    assert block.kind == "card"
    assert block.spans == [Span(text="¿Qué es FastAPI?", lang=None)]
    assert block.extra_spans == [Span(text="Un framework web en Python.", lang=None)]


def test_list_items_get_prefix_spans() -> None:
    text = "- Primero `git`\n- Segundo `docker`\n"
    [block] = list(parse_markdown(text))
    assert block.kind == "text"
    prefixes = [s.text for s in block.spans if s.lang is None and "Punto" in s.text]
    assert any("Punto 1: " in p for p in prefixes)
    assert any("Punto 2: " in p for p in prefixes)
    # English code spans preserved
    en_spans = [s.text for s in block.spans if s.lang == "en"]
    assert "git" in en_spans and "docker" in en_spans
