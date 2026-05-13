"""Markdown parser that yields blocks for TTS rendering.

This module converts a Markdown document into a stream of ``Block`` objects.
Each block represents either content to be spoken (``text``) or content that
should trigger an interactive pause when read aloud (``code``, ``table``,
``image``, ``math``, ``card``).

The ``card`` kind represents an HTML ``<details><summary>Q</summary>A</details>``
block, which we treat as a flashcard: the question is spoken, the user is
prompted to continue, then the answer is spoken.

Also exposes ``detect_lang``, a fast stop-word based heuristic to pick a TTS
voice per paragraph (Spanish vs English).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

from markdown_it import MarkdownIt
from markdown_it.token import Token

BlockKind = Literal["text", "code", "table", "image", "math", "card"]


@dataclass
class Block:
    """A single unit of content yielded by :func:`parse_markdown`.

    Attributes:
        kind: One of ``text``, ``code``, ``table``, ``image``, ``math``, ``card``.
        content: Text to be spoken. Empty for non-text kinds except ``card``,
            where it holds the question.
        raw_preview: Original text shown in the console when an interactive
            pause is triggered.
        info: Auxiliary metadata (e.g. language tag of a code block, ``"N rows"``
            for tables, ``"math"``).
        extra: Used by ``card`` to hold the answer text.
    """

    kind: BlockKind
    content: str
    raw_preview: str
    info: str = ""
    extra: str = ""


# --- Language detection -----------------------------------------------------

_ES_HINTS: frozenset[str] = frozenset(
    {
        "el",
        "la",
        "los",
        "las",
        "de",
        "del",
        "que",
        "para",
        "por",
        "con",
        "sin",
        "una",
        "uno",
        "es",
        "son",
        "está",
        "están",
        "más",
        "como",
        "pero",
        "porque",
        "cuando",
        "donde",
        "qué",
        "cuál",
        "según",
        "también",
        "muy",
        "mucho",
    }
)
_EN_HINTS: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "without",
        "that",
        "this",
        "these",
        "those",
        "from",
        "into",
        "about",
        "which",
        "what",
        "when",
        "where",
        "because",
        "very",
        "much",
        "more",
        "than",
        "also",
    }
)

LangCode = Literal["es", "en", "unknown"]


def detect_lang(text: str) -> LangCode:
    """Detect the dominant language of a text snippet.

    Uses a simple stop-word counting heuristic. Returns ``"unknown"`` when
    neither language has a clear majority (within 20% margin).
    """
    words = re.findall(r"[a-záéíóúñü]+", text.lower())
    if not words:
        return "unknown"
    es = sum(1 for w in words if w in _ES_HINTS)
    en = sum(1 for w in words if w in _EN_HINTS)
    if es == 0 and en == 0:
        return "unknown"
    if es >= en * 1.2:
        return "es"
    if en >= es * 1.2:
        return "en"
    return "unknown"


# --- Helpers ----------------------------------------------------------------


def _flatten_inline(token: Token) -> str:
    """Flatten a ``markdown-it`` ``inline`` token into a plain TTS-readable string."""
    parts: list[str] = []
    for child in token.children or []:
        if child.type == "text":
            parts.append(child.content)
        elif child.type == "code_inline":
            # Inline code: mark it audibly so the listener notices.
            parts.append(f"código {child.content}")
        elif child.type == "softbreak":
            parts.append(" ")
        elif child.type == "hardbreak":
            parts.append(". ")
        elif child.type in {
            "link_open",
            "link_close",
            "em_open",
            "em_close",
            "strong_open",
            "strong_close",
        }:
            continue
        elif child.type == "image":
            alt = child.attrs.get("alt", "imagen") if child.attrs else "imagen"
            parts.append(f"[imagen: {alt}]")
        elif child.type == "html_inline":
            cleaned = re.sub(r"<[^>]+>", "", child.content)
            if cleaned.strip():
                parts.append(cleaned)
        else:
            if child.content:
                parts.append(child.content)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


# --- Public parser ----------------------------------------------------------


@dataclass
class _ParseState:
    """Mutable parsing state shared across helper methods."""

    in_table: bool = False
    in_blockquote: bool = False
    table_rows: list[str] = field(default_factory=list)
    current_row: list[str] = field(default_factory=list)


_DETAILS_RE = re.compile(
    r"<details>\s*<summary>(?P<q>.*?)</summary>\s*(?P<a>.*?)</details>",
    re.DOTALL | re.IGNORECASE,
)


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def _extract_flashcards(md_text: str) -> tuple[str, dict[str, tuple[str, str]]]:
    """Replace ``<details><summary>Q</summary>A</details>`` blocks with placeholders.

    Returns the rewritten markdown and a mapping ``placeholder -> (question, answer)``.
    ``markdown-it`` treats HTML blocks as opaque tokens; by substituting unique
    paragraph-shaped placeholders we can detect them later as flashcards.
    """
    placeholders: dict[str, tuple[str, str]] = {}
    counter = 0

    def _sub(match: re.Match[str]) -> str:
        nonlocal counter
        counter += 1
        key = f"MDTTS_CARD_{counter}"
        placeholders[key] = (_strip_html(match.group("q")), _strip_html(match.group("a")))
        return f"\n\n{key}\n\n"

    return _DETAILS_RE.sub(_sub, md_text), placeholders


def parse_markdown(md_text: str) -> Iterator[Block]:
    """Parse a Markdown document and yield :class:`Block` instances.

    The block kinds are designed to drive an interactive TTS reader:

    - ``text``: prose to read aloud (headings, paragraphs, list items, quotes).
    - ``code`` / ``table`` / ``image`` / ``math``: interactive pause points.
    - ``card``: a flashcard extracted from ``<details><summary>Q</summary>A``.
    """
    pre_processed, placeholders = _extract_flashcards(md_text)

    md = MarkdownIt("commonmark", {"breaks": False, "html": True})
    md.enable(["table"])
    tokens = md.parse(pre_processed)

    state = _ParseState()
    i = 0
    while i < len(tokens):
        tok = tokens[i]

        if tok.type == "heading_open":
            level = int(tok.tag[1])
            inline = tokens[i + 1]
            text = _flatten_inline(inline)
            lang = detect_lang(text)
            if lang == "en":
                prefix = {1: "Chapter: ", 2: "Section: ", 3: "Subsection: "}.get(level, "")
            else:
                prefix = {1: "Capítulo: ", 2: "Sección: ", 3: "Subsección: "}.get(level, "")
            yield Block(
                kind="text",
                content=f"{prefix}{text}.",
                raw_preview=f"{'#' * level} {text}",
            )
            i += 3
            continue

        if tok.type == "paragraph_open":
            inline = tokens[i + 1]
            text = _flatten_inline(inline)
            if text:
                if text.strip() in placeholders:
                    q, a = placeholders[text.strip()]
                    yield Block(kind="card", content=q, raw_preview=f"❓ {q}", extra=a)
                else:
                    prefix = "Cita: " if state.in_blockquote else ""
                    yield Block(kind="text", content=f"{prefix}{text}", raw_preview=text)
            i += 3
            continue

        if tok.type in {"fence", "code_block"}:
            lang = (tok.info or "").strip() or "texto"
            yield Block(
                kind="code",
                content="",
                raw_preview=tok.content.rstrip(),
                info=lang,
            )
            i += 1
            continue

        if tok.type in {"bullet_list_open", "ordered_list_open"}:
            depth = 1
            j = i + 1
            items: list[str] = []
            while j < len(tokens) and depth > 0:
                t = tokens[j]
                if t.type in {"bullet_list_open", "ordered_list_open"}:
                    depth += 1
                elif t.type in {"bullet_list_close", "ordered_list_close"}:
                    depth -= 1
                elif t.type == "inline" and depth >= 1:
                    items.append(_flatten_inline(t))
                j += 1
            if items:
                spoken = ". ".join(f"Punto {n}: {txt}" for n, txt in enumerate(items, 1))
                yield Block(
                    kind="text",
                    content=spoken,
                    raw_preview="\n".join(f"- {it}" for it in items),
                )
            i = j
            continue

        if tok.type == "blockquote_open":
            state.in_blockquote = True
            i += 1
            continue
        if tok.type == "blockquote_close":
            state.in_blockquote = False
            i += 1
            continue

        if tok.type == "hr":
            yield Block(kind="text", content="Separador.", raw_preview="---")
            i += 1
            continue

        if tok.type == "table_open":
            state.in_table = True
            state.table_rows = []
            state.current_row = []
            i += 1
            continue
        if tok.type == "table_close":
            state.in_table = False
            preview = "\n".join(state.table_rows)
            yield Block(
                kind="table",
                content="",
                raw_preview=preview,
                info=f"{len(state.table_rows)} filas",
            )
            i += 1
            continue
        if state.in_table:
            if tok.type == "tr_open":
                state.current_row = []
            elif tok.type == "tr_close":
                state.table_rows.append(" | ".join(state.current_row))
            elif tok.type == "inline":
                state.current_row.append(_flatten_inline(tok))
            i += 1
            continue

        if tok.type == "html_block":
            cleaned = re.sub(r"<[^>]+>", " ", tok.content)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if cleaned:
                yield Block(kind="text", content=cleaned, raw_preview=tok.content.strip())
            i += 1
            continue

        if tok.type == "math_block":
            yield Block(kind="math", content="", raw_preview=tok.content.rstrip(), info="math")
            i += 1
            continue

        i += 1
