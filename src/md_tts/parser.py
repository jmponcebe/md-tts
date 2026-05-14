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
class Span:
    """A sub-segment of a :class:`Block` with an optional explicit language.

    Spans let the Edge backend swap voices mid-paragraph: e.g. when a
    Spanish sentence quotes an English technical term in backticks, the
    parser emits a ``Span(text="FastAPI", lang="en")`` sandwiched between
    Spanish-tagged spans. A ``lang`` of ``None`` means "inherit the block's
    detected language"; the consumer is responsible for resolving it.

    Attributes:
        text: The literal text to speak (already emoji-cleaned).
        lang: ``"es"`` / ``"en"`` to force a voice, or ``None`` to inherit.
    """

    text: str
    lang: LangCode | None = None


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
        spans: Ordered sub-segments of ``content`` annotated with per-span
            language. Empty for ``code`` / ``table`` blocks. Consumers that
            do not support per-span language switching can ignore this and
            fall back to ``content``.
        extra_spans: Same as :attr:`spans` but for ``card``'s ``extra``
            (the answer text).
    """

    kind: BlockKind
    content: str
    raw_preview: str
    info: str = ""
    extra: str = ""
    spans: list[Span] = field(default_factory=list)
    extra_spans: list[Span] = field(default_factory=list)


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


def _coalesce_spans(spans: list[Span]) -> list[Span]:
    """Merge adjacent spans that share the same language tag.

    Adjacent ``Span(text="a", lang=None)`` + ``Span(text="b", lang=None)``
    becomes ``Span(text="ab", lang=None)``. Empty spans are dropped. This
    keeps the span list compact so the Edge backend issues one HTTP request
    per actual language boundary, not per markdown-it token.
    """
    out: list[Span] = []
    for s in spans:
        if not s.text:
            continue
        if out and out[-1].lang == s.lang:
            out[-1] = Span(text=out[-1].text + s.text, lang=s.lang)
        else:
            out.append(s)
    return out


def _flatten_inline_pieces(
    token: Token, *, inline_code_lang: LangCode | None = "en"
) -> tuple[str, list[Span]]:
    """Flatten an ``inline`` token to both a flat string and a span list.

    The flat string mirrors the legacy :func:`_flatten_inline` output (with
    inline code wrapped in single quotes for audible separation on the local
    backend). The span list carries the same content split by language
    boundaries: ``code_inline`` children are tagged with ``inline_code_lang``
    (default ``"en"``); everything else is tagged ``None`` so the consumer
    inherits the block's detected language. Pass ``inline_code_lang=None``
    to preserve the pre-0.5 single-voice behavior.
    """
    text_parts: list[str] = []
    spans: list[Span] = []

    def emit(flat_text: str, span_text: str, lang: LangCode | None) -> None:
        text_parts.append(flat_text)
        clean = _EMOJI_RE.sub("", span_text)
        if clean:
            spans.append(Span(text=clean, lang=lang))

    for child in token.children or []:
        if child.type == "text":
            emit(child.content, child.content, None)
        elif child.type == "code_inline":
            # Flat string keeps the quotes so the local backend (single voice)
            # still hears a snippet boundary; the span list drops them since
            # the voice switch itself signals "this is code".
            emit(f"'{child.content}'", child.content, inline_code_lang)
        elif child.type == "softbreak":
            emit(" ", " ", None)
        elif child.type == "hardbreak":
            emit(". ", ". ", None)
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
            placeholder = f"[imagen: {alt or 'sin descripción'}]"
            emit(placeholder, placeholder, None)
        elif child.type == "html_inline":
            cleaned = re.sub(r"<[^>]+>", "", child.content)
            if cleaned.strip():
                emit(cleaned, cleaned, None)
        else:
            if child.content:
                emit(child.content, child.content, None)

    flat = re.sub(r"\s+", " ", "".join(text_parts)).strip()
    return flat, _coalesce_spans(spans)


def _flatten_inline(token: Token) -> str:
    """Backward-compatible wrapper that returns only the flat string."""
    return _flatten_inline_pieces(token)[0]


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


def _strip_emoji_spans(spans: list[Span]) -> list[Span]:
    """Drop spans that become empty after emoji stripping. Idempotent.

    ``_flatten_inline_pieces`` already strips emojis at emit time, so this
    is mostly a no-op for inline content. It exists for paths that build
    spans from already-flattened text (e.g. list items, where the legacy
    ``_strip_emojis`` is applied to a joined string).
    """
    return _coalesce_spans([Span(text=s.text, lang=s.lang) for s in spans if s.text])


def parse_markdown(md_text: str, *, inline_code_lang: LangCode | None = "en") -> Iterator[Block]:
    """Parse a Markdown document and yield :class:`Block` instances.

    The block kinds are designed to drive an interactive TTS reader:

    - ``text``: prose to read aloud (headings, paragraphs, list items, quotes).
    - ``code`` / ``table`` / ``image`` / ``math``: interactive pause points.
    - ``card``: a flashcard extracted from ``<details><summary>Q</summary>A``.

    Args:
        md_text: The raw Markdown source.
        inline_code_lang: Language tag to assign to inline ``code_inline`` spans
            (e.g. content between single backticks). Defaults to ``"en"`` since
            inline code in technical notes is almost always English. Pass
            ``None`` to preserve the pre-0.5 behavior (one voice for the whole
            paragraph).
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
            raw_text, body_spans = _flatten_inline_pieces(inline, inline_code_lang=inline_code_lang)
            text = _strip_emojis(raw_text)
            lang = detect_lang(text)
            if lang == "en":
                prefix = {1: "Chapter: ", 2: "Section: ", 3: "Subsection: "}.get(level, "")
            else:
                prefix = {1: "Capítulo: ", 2: "Sección: ", 3: "Subsección: "}.get(level, "")
            needs_period = text and not text.endswith((".", "!", "?", ":"))
            spoken = f"{text}." if needs_period else text
            spans: list[Span] = []
            if prefix:
                spans.append(Span(text=prefix, lang=None))
            spans.extend(body_spans)
            if needs_period:
                spans.append(Span(text=".", lang=None))
            yield Block(
                kind="text",
                content=f"{prefix}{spoken}",
                raw_preview=f"{'#' * level} {raw_text}",
                spans=_coalesce_spans(spans),
            )
            i += 3
            continue

        if tok.type == "paragraph_open":
            inline = tokens[i + 1]
            raw_text, body_spans = _flatten_inline_pieces(inline, inline_code_lang=inline_code_lang)
            text = _strip_emojis(raw_text)
            if text:
                if text.strip() in placeholders:
                    q, a = placeholders[text.strip()]
                    q_clean = _strip_emojis(q)
                    a_clean = _strip_emojis(a)
                    yield Block(
                        kind="card",
                        content=q_clean,
                        raw_preview=f"❓ {q}",
                        extra=a_clean,
                        spans=[Span(text=q_clean, lang=None)] if q_clean else [],
                        extra_spans=[Span(text=a_clean, lang=None)] if a_clean else [],
                    )
                else:
                    prefix = "Cita: " if state.in_blockquote else ""
                    spans = []
                    if prefix:
                        spans.append(Span(text=prefix, lang=None))
                    spans.extend(body_spans)
                    yield Block(
                        kind="text",
                        content=f"{prefix}{text}",
                        raw_preview=raw_text,
                        spans=_coalesce_spans(spans),
                    )
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
            # We keep the raw text (for preview), the emoji-stripped text
            # (for the legacy ``content`` field) and the span list (for the
            # Edge backend's per-span voice switching).
            items: list[tuple[int, str, str, list[Span]]] = []
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
                    raw, item_spans = _flatten_inline_pieces(t, inline_code_lang=inline_code_lang)
                    items.append((item_depth, raw, _strip_emojis(raw), item_spans))
                j += 1
            if items:
                top_n = 0
                sub_n = 0
                spoken_parts: list[str] = []
                preview_parts: list[str] = []
                combined_spans: list[Span] = []
                for idx, (level, raw_txt, spoken_txt, item_spans) in enumerate(items):
                    if level <= 1:
                        top_n += 1
                        sub_n = 0
                        item_prefix = f"Punto {top_n}: "
                        spoken_parts.append(f"{item_prefix}{spoken_txt}")
                        preview_parts.append(f"- {raw_txt}")
                    else:
                        sub_n += 1
                        item_prefix = f"Subpunto {sub_n}: "
                        spoken_parts.append(f"{item_prefix}{spoken_txt}")
                        preview_parts.append(f"{'  ' * (level - 1)}- {raw_txt}")
                    if idx > 0:
                        combined_spans.append(Span(text=". ", lang=None))
                    combined_spans.append(Span(text=item_prefix, lang=None))
                    combined_spans.extend(item_spans)
                yield Block(
                    kind="text",
                    content=". ".join(spoken_parts),
                    raw_preview="\n".join(preview_parts),
                    spans=_coalesce_spans(combined_spans),
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
            yield Block(
                kind="text",
                content="Separador.",
                raw_preview="---",
                spans=[Span(text="Separador.", lang=None)],
            )
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
                yield Block(
                    kind="text",
                    content=spoken,
                    raw_preview=tok.content.strip(),
                    spans=[Span(text=spoken, lang=None)],
                )
            i += 1
            continue

        i += 1
