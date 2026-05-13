"""Thin wrapper around :mod:`pyttsx4`.

The reader is intentionally minimal: it picks a single voice when constructed
and then speaks every utterance with it. Per-paragraph voice switching turned
out to be unreliable on Windows SAPI5 (the engine silently drops utterances
after a voice change), so we trade language switching for stability.

We use ``pyttsx4`` (a maintained fork of ``pyttsx3``) because ``pyttsx3 2.99``
exhibits a long-standing SAPI5 bug where only the first ``runAndWait()`` call
produces audio; subsequent ones are silently dropped. ``pyttsx4`` fixes this
while keeping the exact same API surface, and still covers the three target
platforms (SAPI5 / NSSpeechSynthesizer / eSpeak).
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pyttsx4

from .parser import LangCode

if TYPE_CHECKING:
    from pyttsx4.engine import Engine

# Hints used to pick a voice from the OS-provided list. Matched against the
# voice ``id`` and ``name`` in a case-insensitive contains check.
_ES_VOICE_HINTS: tuple[str, ...] = (
    "spanish",
    "español",
    "espanol",
    "es-",
    "es_",
    "helena",
    "sabina",
    "pablo",
)
_EN_VOICE_HINTS: tuple[str, ...] = (
    "english",
    "en-",
    "en_",
    "zira",
    "david",
    "hazel",
    "samantha",
)


@dataclass
class TTSReader:
    """Speak text synchronously with a single, pre-selected voice.

    Attributes:
        rate: Words per minute hint passed to the underlying engine.
        forced_voice: If set, overrides automatic voice selection.
        lang: Optional language used to pick a voice automatically.
    """

    rate: int = 185
    forced_voice: str | None = None
    lang: LangCode = "unknown"
    _engine: Engine = field(init=False, repr=False)
    _active_voice: str | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        self._engine = pyttsx4.init()
        self._engine.setProperty("rate", self.rate)
        default_voice = self._engine.getProperty("voice")
        voice_id = self.forced_voice or self._pick_voice(self.lang) or default_voice
        self._active_voice = voice_id
        if voice_id:
            self._engine.setProperty("voice", voice_id)

    def _pick_voice(self, lang: LangCode) -> str | None:
        voices = self._engine.getProperty("voices") or []
        if lang == "es":
            hints: tuple[str, ...] = _ES_VOICE_HINTS
        elif lang == "en":
            hints = _EN_VOICE_HINTS
        else:
            return None
        for v in voices:
            haystack = f"{getattr(v, 'id', '')} {getattr(v, 'name', '')}".lower()
            if any(h in haystack for h in hints):
                return v.id
        return None

    def list_voices(self) -> list[tuple[str, str]]:
        """Return ``(id, name)`` for every voice the engine exposes."""
        voices = self._engine.getProperty("voices") or []
        return [(getattr(v, "id", ""), getattr(v, "name", "")) for v in voices]

    def say(self, text: str, *, lang: LangCode = "unknown") -> None:
        """Speak ``text`` synchronously.

        The ``lang`` argument is accepted for API compatibility but is
        currently ignored: the active voice is fixed at construction time.

        Switching to ``pyttsx4`` resolved the main SAPI5 issue (audio being
        dropped after the first ``runAndWait()``). We still re-apply the
        voice on every utterance as a defensive measure against unrelated
        SAPI5 quirks observed when the engine is reused for long sessions.
        """
        del lang  # voice is fixed at construction time
        if not text.strip():
            return
        if self._active_voice:
            self._engine.setProperty("voice", self._active_voice)
        self._engine.say(text)
        self._engine.runAndWait()

    def stop(self) -> None:
        """Stop any ongoing utterance (useful for SIGINT handlers)."""
        with contextlib.suppress(Exception):
            self._engine.stop()
