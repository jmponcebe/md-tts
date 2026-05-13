"""Thin wrapper around :mod:`pyttsx3` with per-utterance voice switching.

The reader picks a Spanish or English voice on each ``say()`` call based on
the language tag computed by :func:`md_tts.parser.detect_lang`. This is cheap
on Windows SAPI5 and acceptable on macOS/Linux backends; it lets a single
document mix languages without sounding robotic.

We deliberately avoid abstracting the engine behind an interface. ``pyttsx3``
already covers the three target platforms (SAPI5 / NSSpeechSynthesizer /
eSpeak) and keeping the wrapper minimal makes the dependency easy to swap
later if a cloud TTS option is added.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import pyttsx3

if TYPE_CHECKING:
    from pyttsx3.engine import Engine

LangCode = Literal["es", "en", "unknown"]

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
_EN_VOICE_HINTS: tuple[str, ...] = ("english", "en-", "en_", "zira", "david", "hazel", "samantha")


@dataclass
class TTSReader:
    """Speak text with rate / voice selection driven by language detection.

    Attributes:
        rate: Words per minute hint passed to the underlying engine.
        forced_voice: If set, overrides automatic voice selection.
    """

    rate: int = 185
    forced_voice: str | None = None
    _engine: Engine = field(init=False, repr=False)
    _voice_cache: dict[str, str | None] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self._engine = pyttsx3.init()
        self._engine.setProperty("rate", self.rate)
        if self.forced_voice:
            self._engine.setProperty("voice", self.forced_voice)

    # ----- voice selection -------------------------------------------------

    def _pick_voice(self, lang: LangCode) -> str | None:
        if lang in self._voice_cache:
            return self._voice_cache[lang]

        voices = self._engine.getProperty("voices") or []
        hints: tuple[str, ...]
        if lang == "es":
            hints = _ES_VOICE_HINTS
        elif lang == "en":
            hints = _EN_VOICE_HINTS
        else:
            hints = ()

        chosen: str | None = None
        for v in voices:
            haystack = f"{getattr(v, 'id', '')} {getattr(v, 'name', '')}".lower()
            if any(h in haystack for h in hints):
                chosen = v.id
                break

        self._voice_cache[lang] = chosen
        return chosen

    # ----- public API ------------------------------------------------------

    def list_voices(self) -> list[tuple[str, str]]:
        """Return ``(id, name)`` for every voice the engine exposes."""
        voices = self._engine.getProperty("voices") or []
        return [(getattr(v, "id", ""), getattr(v, "name", "")) for v in voices]

    def say(self, text: str, *, lang: LangCode = "unknown") -> None:
        """Speak ``text`` synchronously, switching voice when possible."""
        if not text.strip():
            return
        if not self.forced_voice:
            voice_id = self._pick_voice(lang)
            if voice_id is not None:
                self._engine.setProperty("voice", voice_id)
        self._engine.say(text)
        self._engine.runAndWait()

    def stop(self) -> None:
        """Stop any ongoing utterance (useful for SIGINT handlers)."""
        with contextlib.suppress(Exception):
            self._engine.stop()
