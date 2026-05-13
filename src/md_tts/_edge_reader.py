"""Edge TTS backend.

Uses Microsoft Edge's neural voices via :mod:`edge_tts`. Synthesis happens
over HTTPS (no Microsoft account required, no API key), and the resulting
MP3 is played back locally with :mod:`playsound3`.

Why this exists:
    The local ``pyttsx4`` backend is robust but sounds robotic. Edge's
    neural voices are dramatically more natural and can be picked per
    utterance, which makes per-paragraph language switching trivial: each
    utterance is an independent HTTP request, so there is no shared engine
    state to corrupt the way SAPI5 sometimes does.

Trade-offs:
    Requires internet. Adds ~200-500 ms latency per utterance (HTTPS
    round-trip + decode). Audio is written to a temporary MP3 file because
    :mod:`playsound3` does not accept in-memory buffers reliably across
    platforms; we delete the file once playback finishes.
"""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .parser import LangCode

# Sensible default voices. Picked for naturalness; users can override via
# ``--voice``. Other locales (es-MX, en-GB, etc.) work too if requested.
DEFAULT_ES_VOICE = "es-ES-ElviraNeural"
DEFAULT_EN_VOICE = "en-US-AriaNeural"
DEFAULT_VOICE = DEFAULT_EN_VOICE


def _rate_to_edge(rate_wpm: int) -> str:
    """Translate words-per-minute to Edge's percentage rate.

    Edge accepts strings like ``"+10%"`` or ``"-5%"``. Treat 185 wpm
    (pyttsx4's default) as 0 % and scale linearly; clamp to ±50 % so users
    can't accidentally produce unintelligible speech.
    """
    delta = round((rate_wpm - 185) / 185 * 100)
    delta = max(-50, min(50, delta))
    sign = "+" if delta >= 0 else "-"
    return f"{sign}{abs(delta)}%"


@dataclass
class EdgeReader:
    """Speak text using Microsoft Edge neural voices.

    Attributes:
        rate: Words per minute. Translated to Edge's ``+N%``/``-N%`` rate.
        forced_voice: If set, use this voice for every utterance regardless
            of ``lang``. Use voice names like ``"es-ES-ElviraNeural"``.
    """

    rate: int = 185
    forced_voice: str | None = None
    _rate_str: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rate_str = _rate_to_edge(self.rate)

    def _voice_for(self, lang: LangCode) -> str:
        if self.forced_voice:
            return self.forced_voice
        if lang == "es":
            return DEFAULT_ES_VOICE
        if lang == "en":
            return DEFAULT_EN_VOICE
        return DEFAULT_VOICE

    def say(self, text: str, *, lang: LangCode = "unknown") -> None:
        """Synthesize ``text`` via Edge and play it back synchronously."""
        if not text.strip():
            return
        voice = self._voice_for(lang)
        asyncio.run(self._speak(text, voice))

    async def _speak(self, text: str, voice: str) -> None:
        import edge_tts

        communicate = edge_tts.Communicate(text, voice=voice, rate=self._rate_str)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as fh:
            tmp_path = Path(fh.name)
        try:
            await communicate.save(str(tmp_path))
            self._play(tmp_path)
        finally:
            with contextlib.suppress(OSError):
                tmp_path.unlink()

    def _play(self, path: Path) -> None:
        # Imported here so test environments without an audio backend can
        # still import this module.
        import playsound3

        playsound3.playsound(str(path), block=True)

    def stop(self) -> None:
        """Stop playback if a backend supports it.

        ``playsound3`` is fire-and-forget when ``block=True``, so this is a
        best-effort no-op: the current utterance finishes before SIGINT
        propagates. Future work: switch to a non-blocking player.
        """
        return

    def list_voices(self) -> list[tuple[str, str]]:
        """Return ``(id, label)`` for every Edge voice (one HTTPS call)."""
        voices: list[dict[str, Any]] = asyncio.run(self._fetch_voices())
        return [(v["ShortName"], f"{v['ShortName']} ({v.get('Gender', '?')})") for v in voices]

    async def _fetch_voices(self) -> list[dict[str, Any]]:
        import edge_tts

        return await edge_tts.list_voices()
