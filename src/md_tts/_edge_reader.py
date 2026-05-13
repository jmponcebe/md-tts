"""Edge TTS backend.

Uses Microsoft Edge's neural voices via :mod:`edge_tts`. Synthesis happens
over HTTPS (no Microsoft account required, no API key), and the resulting
MP3 is played back locally with :mod:`pygame.mixer.music`.

Why pygame for playback:
    ``playsound3`` and most lightweight alternatives only support
    fire-and-forget playback on Windows (the default ``wmplayer`` backend
    doesn't expose pause / unpause). ``pygame.mixer.music`` ships with a
    real SDL_mixer pipeline that supports ``pause()`` / ``unpause()``
    cross-platform, which is what makes SPACE truly toggle playback during
    a paragraph.

Trade-offs:
    Requires internet for synthesis. Adds ~200-500 ms latency per utterance
    (HTTPS round-trip + decode). Audio is written to a temporary MP3 file
    because pygame's music stream wants a file path; we delete the file
    when the next utterance starts (or on stop).
"""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .parser import LangCode

DEFAULT_ES_VOICE = "es-ES-ElviraNeural"
DEFAULT_EN_VOICE = "en-US-AriaNeural"
DEFAULT_VOICE = DEFAULT_EN_VOICE

# Module-level guard: pygame.mixer must be initialised exactly once per
# process. We do it lazily on first ``play`` so importing this module on a
# headless test machine doesn't fail when no audio device is available.
_MIXER_READY = False


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


def _ensure_mixer() -> None:
    """Initialise ``pygame.mixer`` on demand (idempotent)."""
    global _MIXER_READY
    if _MIXER_READY:
        return
    # Hide pygame's welcome banner before the import so it never reaches
    # the terminal. The env var is the only public way to silence it.
    import os

    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame

    pygame.mixer.init()
    _MIXER_READY = True


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
    _tmp_path: Path | None = field(init=False, default=None, repr=False)
    _paused: bool = field(init=False, default=False, repr=False)
    _stopped: bool = field(init=False, default=False, repr=False)

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
        """Blocking convenience: :meth:`play` then :meth:`wait`."""
        self.play(text, lang=lang)
        self.wait()

    def play(self, text: str, *, lang: LangCode = "unknown") -> None:
        """Synthesize ``text`` and start playback in the background."""
        if not text.strip():
            return
        self._cleanup_previous()
        self._stopped = False
        voice = self._voice_for(lang)
        self._tmp_path = asyncio.run(self._synthesize(text, voice))
        self._start_playback(self._tmp_path)

    async def _synthesize(self, text: str, voice: str) -> Path:
        import edge_tts

        communicate = edge_tts.Communicate(text, voice=voice, rate=self._rate_str)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as fh:
            tmp_path = Path(fh.name)
        await communicate.save(str(tmp_path))
        return tmp_path

    def _start_playback(self, path: Path) -> None:
        _ensure_mixer()
        import pygame

        pygame.mixer.music.load(str(path))
        pygame.mixer.music.play()
        self._paused = False

    def _cleanup_previous(self) -> None:
        if _MIXER_READY:
            import pygame

            with contextlib.suppress(Exception):
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
        if self._tmp_path is not None:
            with contextlib.suppress(OSError):
                self._tmp_path.unlink()
            self._tmp_path = None
        self._paused = False

    def is_playing(self) -> bool:
        if not _MIXER_READY or self._tmp_path is None:
            return False
        import pygame

        # ``get_busy`` returns False while paused; treat paused as still active
        # so the dispatch loop keeps polling for SPACE/q instead of advancing.
        return bool(pygame.mixer.music.get_busy()) or self._paused

    def wait(self, timeout: float | None = None) -> bool:
        if not self.is_playing():
            return not self._stopped
        deadline = None if timeout is None else time.monotonic() + timeout
        while self.is_playing():
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(0.05)
        self._cleanup_previous()
        return not self._stopped

    def pause(self) -> None:
        if not _MIXER_READY or self._paused:
            return
        import pygame

        pygame.mixer.music.pause()
        self._paused = True

    def resume(self) -> None:
        if not _MIXER_READY or not self._paused:
            return
        import pygame

        pygame.mixer.music.unpause()
        self._paused = False

    def set_rate(self, rate: int) -> None:
        """Update the rate. Applies to the next utterance, not the current one."""
        self.rate = rate
        self._rate_str = _rate_to_edge(rate)

    def stop(self) -> None:
        """Stop current playback and delete the temp file."""
        self._stopped = True
        self._cleanup_previous()

    def list_voices(self) -> list[tuple[str, str]]:
        """Return ``(id, label)`` for every Edge voice (one HTTPS call)."""
        voices: list[dict[str, Any]] = asyncio.run(self._fetch_voices())
        return [(v["ShortName"], f"{v['ShortName']} ({v.get('Gender', '?')})") for v in voices]

    async def _fetch_voices(self) -> list[dict[str, Any]]:
        import edge_tts

        return await edge_tts.list_voices()
