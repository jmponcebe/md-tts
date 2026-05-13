"""Local TTS backend using :mod:`pyttsx4`.

The reader is intentionally minimal: it picks a single voice when constructed
and then speaks every utterance with it. Per-paragraph voice switching turned
out to be unreliable on Windows SAPI5 (the engine silently drops utterances
after a voice change), so this backend trades language switching for
stability.

We use ``pyttsx4`` (a maintained fork of ``pyttsx3``) because ``pyttsx3 2.99``
exhibits a long-standing SAPI5 bug where only the first ``runAndWait()`` call
produces audio; subsequent ones are silently dropped. ``pyttsx4`` fixes this
while keeping the exact same API surface, and still covers the three target
platforms (SAPI5 / NSSpeechSynthesizer / eSpeak).
"""

from __future__ import annotations

import contextlib
import threading
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
class LocalReader:
    """Speak text synchronously via the OS-provided TTS engine.

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
    _thread: threading.Thread | None = field(init=False, default=None, repr=False)
    _stopping: bool = field(init=False, default=False, repr=False)

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
        """Blocking convenience: :meth:`play` then :meth:`wait`."""
        self.play(text, lang=lang)
        self.wait()

    def play(self, text: str, *, lang: LangCode = "unknown") -> None:
        """Start an utterance in a background thread.

        ``lang`` is accepted for API compatibility but ignored: the active
        voice is fixed at construction time because per-utterance voice
        switching is unreliable on Windows SAPI5. We re-apply the voice on
        every utterance as a defensive measure.
        """
        del lang  # voice is fixed at construction time
        if not text.strip():
            return
        # Wait for any in-flight utterance to finish so we don't pile up.
        self.wait()
        self._stopping = False
        if self._active_voice:
            self._engine.setProperty("voice", self._active_voice)
        # Apply any pending rate change now (safe: worker thread is idle).
        with contextlib.suppress(Exception):
            self._engine.setProperty("rate", self.rate)
        self._engine.say(text)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        # ``runAndWait`` blocks until either all queued utterances are spoken
        # or ``engine.stop()`` is called from another thread.
        with contextlib.suppress(Exception):
            self._engine.runAndWait()

    def wait(self, timeout: float | None = None) -> bool:
        if self._thread is None:
            return True
        self._thread.join(timeout=timeout)
        finished = not self._thread.is_alive()
        if finished:
            self._thread = None
        return finished and not self._stopping

    def is_playing(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def pause(self) -> None:
        """Best-effort pause.

        ``pyttsx4`` doesn't expose a true pause primitive, and stopping the
        engine drops the rest of the utterance with no way to resume from
        the same position. We document this limitation rather than fake it.
        """
        return

    def resume(self) -> None:
        """No-op counterpart to :meth:`pause`."""
        return

    def set_rate(self, rate: int) -> None:
        """Update the rate. Applies to the next utterance (not the current).

        We deliberately defer the ``setProperty`` call until playback has
        finished: pyttsx4's underlying SAPI5/eSpeak driver may be running
        on the worker thread, and writing properties concurrently can race.
        The rate is stored eagerly so the CLI reflects the new value
        immediately; the engine picks it up before the next ``say()``.
        """
        self.rate = rate
        if not self.is_playing():
            with contextlib.suppress(Exception):
                self._engine.setProperty("rate", rate)

    def stop(self) -> None:
        """Stop any ongoing utterance (useful for SIGINT handlers)."""
        self._stopping = True
        with contextlib.suppress(Exception):
            self._engine.stop()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
