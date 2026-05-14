"""TTS reader interface and backend factory.

The CLI talks to TTS engines through the :class:`TTSReader` protocol. There
are two concrete backends:

- ``local`` (default): uses :mod:`pyttsx4` on top of the OS-provided engine
  (SAPI5 on Windows, NSSpeech on macOS, eSpeak on Linux). Picks one voice
  per session and ignores per-utterance ``lang`` (per-paragraph voice
  switching proved unstable on SAPI5).
- ``edge``: uses Microsoft Edge's neural voices via the ``edge_tts`` package.
  Requires internet but sounds dramatically better and supports per-utterance
  language switching cleanly (each utterance is an independent HTTP request).

Use :func:`build_reader` to instantiate the right backend at runtime.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from .parser import LangCode, Span

BackendName = Literal["local", "edge"]


@runtime_checkable
class TTSReader(Protocol):
    """Minimal interface every TTS backend must implement.

    Both backends expose a non-blocking API (``play`` + ``wait``) so the
    CLI can poll the keyboard while audio plays. The legacy :meth:`say` is
    preserved as a convenience wrapper that simply plays and waits.
    """

    rate: int

    def play(
        self,
        text: str,
        *,
        lang: LangCode = "unknown",
        spans: list[Span] | None = None,
    ) -> None:
        """Start playback of ``text``, returning immediately.

        ``spans`` is an optional list of sub-segments with per-segment
        language overrides. Backends that support per-utterance voice
        switching (edge) will honor it; backends that don't (local) ignore
        it and speak ``text`` with their single fixed voice.
        """
        ...

    def wait(self, timeout: float | None = None) -> bool:
        """Block until current playback finishes or ``timeout`` elapses.

        Returns ``True`` if playback finished naturally, ``False`` if it
        was interrupted (by :meth:`stop`) or the timeout fired while still
        playing.
        """
        ...

    def is_playing(self) -> bool: ...

    def pause(self) -> None:
        """Pause current playback if the backend supports it.

        Backends without real pause support (e.g. ``local``) should treat
        this as a best-effort no-op rather than raising.
        """
        ...

    def resume(self) -> None:
        """Resume playback paused via :meth:`pause`."""
        ...

    def stop(self) -> None:
        """Stop current playback immediately."""
        ...

    def set_rate(self, rate: int) -> None:
        """Update rate; applies to subsequent utterances."""
        ...

    def say(
        self,
        text: str,
        *,
        lang: LangCode = "unknown",
        spans: list[Span] | None = None,
    ) -> None:
        """Blocking convenience: :meth:`play` followed by :meth:`wait`."""
        ...

    def list_voices(self) -> list[tuple[str, str]]: ...


def build_reader(
    backend: BackendName = "local",
    *,
    rate: int = 185,
    forced_voice: str | None = None,
    lang: LangCode = "unknown",
    voice_es: str | None = None,
    voice_en: str | None = None,
) -> TTSReader:
    """Construct the requested TTS backend.

    Args:
        backend: ``"local"`` (pyttsx4, offline) or ``"edge"`` (Microsoft Edge
            neural voices, requires internet).
        rate: Words per minute. Applied differently by each backend.
        forced_voice: Voice id override. For ``local`` this is the SAPI/etc.
            voice id; for ``edge`` this is the Edge voice name (e.g.
            ``"es-ES-ElviraNeural"``).
        lang: Initial language used by the local backend to pick a voice
            automatically. The edge backend instead picks a voice per
            utterance based on the ``lang`` passed to :meth:`say`.
        voice_es: Edge-only override for the Spanish voice (defaults to
            ``es-ES-ElviraNeural``). Ignored by the local backend.
        voice_en: Edge-only override for the English voice (defaults to
            ``en-US-AriaNeural``). Ignored by the local backend.
    """
    if backend == "local":
        from ._local_reader import LocalReader

        return LocalReader(rate=rate, forced_voice=forced_voice, lang=lang)
    if backend == "edge":
        # Imported lazily so users on offline boxes (and anyone who didn't
        # install the ``edge`` extra) never pay for the import.
        try:
            from ._edge_reader import EdgeReader
        except ImportError as exc:  # pragma: no cover - install-time path
            raise ImportError(
                "The 'edge' backend requires the optional dependencies. "
                "Install them with: pip install 'md-tts[edge]'"
            ) from exc

        return EdgeReader(
            rate=rate,
            forced_voice=forced_voice,
            voice_es=voice_es,
            voice_en=voice_en,
        )
    raise ValueError(f"Unknown TTS backend: {backend!r}")
