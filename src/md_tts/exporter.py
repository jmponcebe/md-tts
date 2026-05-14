"""Render a parsed Markdown document to a single MP3 file.

Only the Edge backend is supported for export: it produces MP3 audio natively,
and concatenating MP3 frames byte-by-byte is well-defined (no re-encoding).

For each block we synthesize one MP3 segment and append it to the output:

- ``text`` / ``card`` Q&A: the actual content.
- ``code`` / ``table``: a localized "skipping <kind>" announcement, so the
    listener knows something was omitted when listening offline.
- Between a card's question and answer we insert a short silence (~3 s)
    so the listener has a moment to recall the answer before it plays.

The silence is generated once per call by asking Edge to synthesize a short
inaudible phrase wrapped in heavy padding; we fall back to a tiny built-in
silent MP3 frame if synthesis fails. MP3 silence is small (a few KB) and
doesn't bloat the final file.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Iterable
from pathlib import Path

from ._edge_reader import (
    DEFAULT_EN_VOICE,
    DEFAULT_ES_VOICE,
    DEFAULT_VOICE,
    _rate_to_edge,
)
from .parser import Block, LangCode, Span

# 3 s of silence approximated by edge-tts itself (see ``_synthesize_silence``).
# This constant is the fallback when synthesis fails: a single empty MP3 frame
# repeated to roughly match the requested duration.
_EMPTY_MP3_FRAME = b"\xff\xfb\x10\xc4" + b"\x00" * 415


def _voice_for(
    lang: LangCode | None,
    forced: str | None,
    *,
    voice_es: str | None = None,
    voice_en: str | None = None,
) -> str:
    if forced:
        return forced
    if lang == "es":
        return voice_es or DEFAULT_ES_VOICE
    if lang == "en":
        return voice_en or DEFAULT_EN_VOICE
    return voice_en or DEFAULT_VOICE


def _skip_announcement(kind: str, info: str, lang: LangCode) -> str:
    """Localized announcement for a skipped non-text block."""
    if lang == "es":
        if kind == "code":
            return "Omitiendo bloque de código."
        return "Omitiendo tabla."
    if kind == "code":
        return f"Skipping code block ({info})." if info else "Skipping code block."
    return "Skipping table."


async def _synthesize(text: str, voice: str, rate: str) -> bytes:
    """Stream an Edge TTS utterance into bytes (MP3 frames)."""
    import edge_tts

    communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
    chunks: list[bytes] = []
    async for ev in communicate.stream():
        if ev.get("type") == "audio":
            chunks.append(ev["data"])
    return b"".join(chunks)


async def _synthesize_silence(voice: str, rate: str, seconds: float = 3.0) -> bytes:
    """Approximate ``seconds`` of silence by synthesizing a comma-padded prompt.

    Edge TTS doesn't expose raw silence generation, but a sentence built from
    commas produces a natural prosodic pause. We tune the length to roughly
    match ``seconds``; small drift is acceptable for the "recall the answer"
    gap between a card's question and answer.
    """
    # A comma adds ~250-300 ms of silence depending on the voice. Twelve
    # commas yields ~3 s. Voice is irrelevant since nothing is voiced.
    text = ", , , , , , , , , , , ,"
    try:
        return await _synthesize(text, voice, rate)
    except Exception:
        # Fall back to a single silent MP3 frame repeated until we approximate
        # ``seconds`` of audio. Each frame is ~26 ms at 48 kbps.
        frames = max(1, int(seconds / 0.026))
        return _EMPTY_MP3_FRAME * frames


def _resolve_lang_for_block(block: Block, override: str, fallback: LangCode) -> LangCode:
    """Pick the language for a block's text.

    Mirrors ``cli._resolve_lang`` but kept local to avoid the CLI ↔ exporter
    dependency cycle.
    """
    from .parser import detect_lang

    if override == "es":
        return "es"
    if override == "en":
        return "en"
    if not block.content:
        return fallback
    detected = detect_lang(block.content)
    return detected if detected in {"es", "en"} else fallback


async def _export_async(
    blocks: Iterable[Block],
    output: Path,
    *,
    lang_override: str,
    session_lang: LangCode,
    rate: int,
    forced_voice: str | None,
    voice_es: str | None = None,
    voice_en: str | None = None,
) -> int:
    """Write all blocks as concatenated MP3 to ``output``. Returns segment count.

    We write to a sibling temp file and atomically rename on success so that
    a partial/failed run never overwrites a previously valid MP3.
    """
    rate_str = _rate_to_edge(rate)
    output.parent.mkdir(parents=True, exist_ok=True)
    segments = 0

    # Cache silence bytes per (voice, rate) so a deck-style document with many
    # cards only pays one Edge round-trip for the Q/A gap.
    silence_cache: dict[tuple[str, str], bytes] = {}

    async def _get_silence(voice: str) -> bytes:
        key = (voice, rate_str)
        if key not in silence_cache:
            silence_cache[key] = await _synthesize_silence(voice, rate_str)
        return silence_cache[key]

    def _voice(lang: LangCode | None) -> str:
        return _voice_for(lang, forced_voice, voice_es=voice_es, voice_en=voice_en)

    async def _synth_block(text: str, spans: list[Span], block_lang: LangCode) -> bytes:
        """Synthesize a text block, honoring spans when they require multi-voice.

        Falls back to single-voice synthesis when spans is empty or every
        span resolves to the same voice (cheaper, fewer HTTPS round-trips).
        """
        if not text.strip():
            return b""
        block_voice = _voice(block_lang)
        if not spans or forced_voice:
            return await _synthesize(text, block_voice, rate_str)
        voices = {_voice(s.lang if s.lang else block_lang) for s in spans}
        if len(voices) <= 1 and next(iter(voices), block_voice) == block_voice:
            return await _synthesize(text, block_voice, rate_str)
        chunks: list[bytes] = []
        for s in spans:
            if not s.text.strip():
                continue
            chunks.append(
                await _synthesize(
                    s.text,
                    _voice(s.lang if s.lang else block_lang),
                    rate_str,
                )
            )
        return b"".join(chunks)

    tmp_path = output.with_name(output.name + ".part")
    try:
        with tmp_path.open("wb") as out:
            for block in blocks:
                if block.kind == "text":
                    if not block.content.strip():
                        continue
                    lang = _resolve_lang_for_block(block, lang_override, session_lang)
                    audio = await _synth_block(block.content, block.spans, lang)
                    if audio:
                        out.write(audio)
                        segments += 1
                    continue

                if block.kind == "card":
                    q_lang = _resolve_lang_for_block(block, lang_override, session_lang)
                    # The answer's language is detected on ``extra``, not ``content``.
                    a_block = Block(kind="text", content=block.extra, raw_preview=block.extra)
                    a_lang = _resolve_lang_for_block(a_block, lang_override, session_lang)

                    if block.content.strip():
                        audio = await _synth_block(block.content, block.spans, q_lang)
                        if audio:
                            out.write(audio)
                            segments += 1
                    out.write(await _get_silence(_voice(q_lang)))
                    if block.extra.strip():
                        audio = await _synth_block(block.extra, block.extra_spans, a_lang)
                        if audio:
                            out.write(audio)
                            segments += 1
                    continue

                # code / table — announce the skip in the session language.
                if lang_override == "es":
                    announce_lang: LangCode = "es"
                elif lang_override == "en":
                    announce_lang = "en"
                else:
                    announce_lang = "es" if session_lang == "es" else "en"
                text = _skip_announcement(block.kind, block.info, announce_lang)
                out.write(await _synthesize(text, _voice(announce_lang), rate_str))
                segments += 1
    except BaseException:
        # Best-effort cleanup; leaving a stray .part is preferable to clobbering
        # an existing valid output file.
        with contextlib.suppress(OSError):
            tmp_path.unlink()
        raise

    # Atomic replace on POSIX; on Windows os.replace also overwrites atomically.
    import os

    os.replace(tmp_path, output)
    return segments


def export_to_mp3(
    blocks: Iterable[Block],
    output: Path,
    *,
    lang_override: str = "auto",
    session_lang: LangCode = "unknown",
    rate: int = 185,
    forced_voice: str | None = None,
    voice_es: str | None = None,
    voice_en: str | None = None,
) -> int:
    """Synchronous entry point. Returns the number of segments written."""
    return asyncio.run(
        _export_async(
            blocks,
            output,
            lang_override=lang_override,
            session_lang=session_lang,
            rate=rate,
            forced_voice=forced_voice,
            voice_es=voice_es,
            voice_en=voice_en,
        )
    )
