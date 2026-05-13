"""Markdown parser that yields blocks for TTS rendering.

This module converts a Markdown document into a stream of ``Block`` objects.
Each block represents either content to be spoken (``text``) or content that
should trigger an interactive pause when read aloud (``code``, ``table``,
``card``).

The ``card`` kind represents an HTML ``<details><summary>Q</summary>A</details>``
block, which we treat as a flashcard: the question is spoken, the user is
prompted to continue, then the answer is spoken.

Inline images are flattened into the surrounding paragraph (e.g. ``[image: alt]``)
rather than emitted as standalone blocks. Math blocks are not detected unless a
dedicated ``markdown-it-py`` plugin is registered; for now they fall through as
text.

Also exposes ``detect_lang``, a fast stop-word based heuristic for language
detection. The CLI currently uses this to pick a single voice for the whole
session (based on the dominant language of the document) rather than swapping
voices per paragraph, which proved unstable on SAPI5.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

from markdown_it import MarkdownIt
from markdown_it.token import Token

BlockKind = Literal["text", "code", "table", "card"]
LangCode = Literal["es", "en", "unknown"]


@dataclass
class Block:
    """A single unit of content yielded by :func:`parse_markdown`.

    Attributes:
        kind: One of ``text``, ``code``, ``table``, ``card``.
        content: Text to be spoken. Empty for non-text kinds except ``card``,
            where it holds the question.
        raw_preview: Original text shown in the console when an interactive
            pause is triggered.
        info: Auxiliary metadata (e.g. language tag of a code block, ``"N rows"``
            for tables).
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


# Match emoji and pictographic symbols across the Unicode planes most likely
# to appear in technical Markdown: emoticons, symbols/pictographs, transport,
# misc symbols, dingbats, enclosed alphanumerics and the supplemental block.
_EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001f6ff"
    "\U0001f900-\U0001f9ff"
    "\U0001fa70-\U0001faff"
    "\U00002600-\U000026ff"
    "\U00002700-\U000027bf"
    "\U0001f1e6-\U0001f1ff"
    "\U0000fe0f"
    "]+",
    flags=re.UNICODE,
)


def _strip_emojis(text: str) -> str:
    """Remove emoji characters and collapse whitespace.

    Emojis tend to be read aloud as their Unicode name ("collision symbol"…)
    which is noisy and confusing. We strip them from the spoken text while
    leaving them in the printed ``raw_preview``.
    """
    return re.sub(r"\s+", " ", _EMOJI_RE.sub("", text)).strip()


def _flatten_inline(token: Token) -> str:
    """Flatten a ``markdown-it`` ``inline`` token into a plain TTS-readable string."""
    parts: list[str] = []
    for child in token.children or []:
        if child.type == "text":
            parts.append(child.content)
        elif child.type == "code_inline":
            # Quote the inline code so it reads as a snippet, without the
            # noisy "código X" repetition when the content itself contains
            # the word "código".
            parts.append(f"'{child.content}'")
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
            "s_open",
            "s_close",
        }:
            continue
        elif child.type == "image":
            # markdown-it-py 3.x stores attrs as list[tuple] OR dict depending on
            # the token type. Normalise both into a plain dict before lookup.
            attrs = child.attrs
            alt = ""
            if isinstance(attrs, dict):
                alt = attrs.get("alt", "") or ""
            elif attrs:
                alt = dict(attrs).get("alt", "") or ""
            # Fall back to the alt text held in child.content (markdown-it
            # populates this with the rendered alt for image tokens).
            if not alt:
                alt = (child.content or "").strip()
            parts.append(f"[imagen: {alt or 'sin descripción'}]")
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
            raw_text = _flatten_inline(inline)
            text = _strip_emojis(raw_text)
            lang = detect_lang(text)
            if lang == "en":
                prefix = {1: "Chapter: ", 2: "Section: ", 3: "Subsection: "}.get(level, "")
            else:
                prefix = {1: "Capítulo: ", 2: "Sección: ", 3: "Subsección: "}.get(level, "")
            spoken = text if text.endswith((".", "!", "?", ":")) else f"{text}."
            yield Block(
                kind="text",
                content=f"{prefix}{spoken}",
                raw_preview=f"{'#' * level} {raw_text}",
            )
            i += 3
            continue

        if tok.type == "paragraph_open":
            inline = tokens[i + 1]
            raw_text = _flatten_inline(inline)
            text = _strip_emojis(raw_text)
            if text:
                if text.strip() in placeholders:
                    q, a = placeholders[text.strip()]
                    yield Block(
                        kind="card",
                        content=_strip_emojis(q),
                        raw_preview=f"❓ {q}",
                        extra=_strip_emojis(a),
                    )
                else:
                    prefix = "Cita: " if state.in_blockquote else ""
                    yield Block(kind="text", content=f"{prefix}{text}", raw_preview=raw_text)
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
            # Track each item with its nesting depth so sub-items get a
            # sub-point prefix ("Subpunto") instead of being flattened.
            # We keep both the raw text (for the on-screen preview) and the
            # emoji-stripped version (for what the engine actually speaks).
            items: list[tuple[int, str, str]] = []
            item_depth = 1
            while j < len(tokens) and depth > 0:
                t = tokens[j]
                if t.type in {"bullet_list_open", "ordered_list_open"}:
                    depth += 1
                    item_depth = depth
                elif t.type in {"bullet_list_close", "ordered_list_close"}:
                    depth -= 1
                    item_depth = max(depth, 1)
                elif t.type == "inline" and depth >= 1:
                    raw = _flatten_inline(t)
                    items.append((item_depth, raw, _strip_emojis(raw)))
                j += 1
            if items:
                top_n = 0
                sub_n = 0
                spoken_parts: list[str] = []
                preview_parts: list[str] = []
                for level, raw_txt, spoken_txt in items:
                    if level <= 1:
                        top_n += 1
                        sub_n = 0
                        spoken_parts.append(f"Punto {top_n}: {spoken_txt}")
                        preview_parts.append(f"- {raw_txt}")
                    else:
                        sub_n += 1
                        spoken_parts.append(f"Subpunto {sub_n}: {spoken_txt}")
                        preview_parts.append(f"{'  ' * (level - 1)}- {raw_txt}")
                yield Block(
                    kind="text",
                    content=". ".join(spoken_parts),
                    raw_preview="\n".join(preview_parts),
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
            spoken = _strip_emojis(cleaned)
            if spoken:
                yield Block(kind="text", content=spoken, raw_preview=tok.content.strip())
            i += 1
            continue

        i += 1
